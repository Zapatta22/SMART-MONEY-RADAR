import unittest

from smart_money_radar.data_sources.geyser_account_updates import normalize_account_update
from smart_money_radar.data_sources.geyser_bank_lineage import (
    BankKey,
    BankLineageTracker,
    normalize_block_meta,
    normalize_entry_update_parent,
    normalize_slot_update,
)


def _slot(slot, status, bank_id=None, parent=None, sequence=1):
    return normalize_slot_update(
        {"slot": slot, "status": status, "bank_id": bank_id, "parent": parent},
        source_id="yellowstone",
        stream_id="conn-1",
        stream_sequence=sequence,
    )


def _block(slot, bank_id, blockhash, parent_slot, parent_blockhash, sequence=1):
    return normalize_block_meta(
        {
            "slot": slot, "bank_id": bank_id, "blockhash": blockhash,
            "parent_slot": parent_slot, "parent_blockhash": parent_blockhash,
        },
        source_id="yellowstone",
        stream_id="conn-1",
        stream_sequence=sequence,
    )


class NormalizeBankEventsTests(unittest.TestCase):
    def test_normalizes_created_bank_with_parent_slot(self):
        event = _slot(101, "SLOT_CREATED_BANK", bank_id=9001, parent=100)
        self.assertEqual(event.bank_id, 9001)
        self.assertEqual(event.parent_slot, 100)

    def test_created_bank_requires_bank_id(self):
        with self.assertRaisesRegex(ValueError, "bank_id"):
            _slot(101, "SLOT_CREATED_BANK", parent=100)

    def test_startup_and_completed_slot_may_have_no_bank_id(self):
        first = _slot(101, "SLOT_FIRST_SHRED_RECEIVED")
        completed = _slot(101, "SLOT_COMPLETED", sequence=2)
        self.assertIsNone(first.bank_id)
        self.assertIsNone(completed.bank_id)

    def test_rejects_unknown_slot_status(self):
        with self.assertRaisesRegex(ValueError, "status"):
            _slot(101, "SLOT_NOT_REAL")

    def test_parent_update_preserves_opaque_bytes(self):
        event = normalize_entry_update_parent(
            {
                "slot": 101, "cleared_bank_id": 9001,
                "parent_slot": 100, "parent_block_id": b"opaque-parent-id",
            },
            source_id="yellowstone", stream_id="conn-1", stream_sequence=8,
        )
        self.assertEqual(event.parent_block_id, b"opaque-parent-id")


class BankLineageTrackerTests(unittest.TestCase):
    def test_slot_number_alone_does_not_select_parent_fork(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(100, "SLOT_CREATED_BANK", bank_id=10, parent=99))
        tracker.add_slot_update(_slot(100, "SLOT_PROCESSED", bank_id=10, parent=99, sequence=2))
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=11, parent=100, sequence=3))
        child = next(node for node in tracker.banks if node.key == BankKey("yellowstone", 101, 11))
        self.assertIsNone(child.parent_key)
        self.assertIsNone(tracker.is_ancestor(BankKey("yellowstone", 100, 10), child.key))

    def test_exact_blockhash_and_parent_slot_link_banks(self):
        tracker = BankLineageTracker()
        tracker.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash"))
        tracker.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash", sequence=2))
        parent = BankKey("yellowstone", 100, 10)
        child = BankKey("yellowstone", 101, 11)
        self.assertTrue(tracker.is_ancestor(parent, child))

    def test_conflicting_blockhash_invalidates_bank_and_ancestor_proof(self):
        tracker = BankLineageTracker()
        tracker.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        tracker.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash", sequence=2))
        parent = BankKey("yellowstone", 100, 10)
        child = BankKey("yellowstone", 101, 11)
        self.assertTrue(tracker.is_ancestor(parent, child))

        conflict = tracker.add_block_meta(
            _block(101, 11, "contradictory-child-hash", 100, "parent-hash", sequence=3)
        )
        self.assertEqual(conflict.status, "conflict")
        self.assertFalse(tracker.is_bank_usable(child))
        self.assertIsNone(tracker.is_ancestor(parent, child))
        node = next(item for item in tracker.banks if item.key == child)
        self.assertTrue(node.invalidated)

    def test_same_slot_distinct_bank_ids_remain_distinct_forks(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(100, "SLOT_CREATED_BANK", bank_id=10, parent=99))
        tracker.add_slot_update(_slot(100, "SLOT_CREATED_BANK", bank_id=20, parent=99, sequence=2))
        self.assertEqual(
            {node.key.bank_id for node in tracker.banks if node.key.slot == 100},
            {10, 20},
        )

    def test_entry_update_parent_invalidates_cleared_bank_and_links_replacement(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=9001, parent=100))
        parent_update = normalize_entry_update_parent(
            {
                "slot": 101, "cleared_bank_id": 9001,
                "parent_slot": 100, "parent_block_id": b"opaque-id",
            },
            source_id="yellowstone", stream_id="conn-1", stream_sequence=2,
        )
        tracker.add_entry_update_parent(parent_update)
        replacement = _slot(101, "SLOT_CREATED_BANK", bank_id=9002, parent=100, sequence=3)
        tracker.add_slot_update(replacement)
        old = next(n for n in tracker.banks if n.key.bank_id == 9001)
        new = next(n for n in tracker.banks if n.key.bank_id == 9002)
        self.assertTrue(old.invalidated)
        self.assertEqual(new.replaces_bank, old.key)
        self.assertEqual(old.parent_block_id, b"opaque-id")

    def test_ambiguous_multiple_cleared_banks_do_not_guess_replacement(self):
        tracker = BankLineageTracker()
        for bank_id, seq in ((1, 1), (2, 2)):
            tracker.add_entry_update_parent(
                normalize_entry_update_parent(
                    {
                        "slot": 101, "cleared_bank_id": bank_id,
                        "parent_slot": 100, "parent_block_id": b"parent",
                    },
                    source_id="yellowstone", stream_id="conn-1", stream_sequence=seq,
                )
            )
        result = tracker.add_slot_update(
            _slot(101, "SLOT_CREATED_BANK", bank_id=3, parent=100, sequence=3)
        )
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict.reason, "ambiguous_replacement")
        self.assertNotIn(BankKey("yellowstone", 101, 3), {node.key for node in tracker.banks})

    def test_slot_dead_without_bank_id_invalidates_known_and_future_banks(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=1, parent=100))
        tracker.add_slot_update(_slot(101, "SLOT_DEAD", sequence=2))
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=2, parent=100, sequence=3))
        self.assertTrue(all(node.dead for node in tracker.banks))

    def test_slot_dead_with_bank_id_only_invalidates_that_bank(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=1, parent=100))
        tracker.add_slot_update(_slot(101, "SLOT_CREATED_BANK", bank_id=2, parent=100, sequence=2))
        tracker.add_slot_update(_slot(101, "SLOT_DEAD", bank_id=1, sequence=3))
        nodes = {node.key.bank_id: node for node in tracker.banks}
        self.assertTrue(nodes[1].dead)
        self.assertFalse(nodes[2].dead)

    def test_account_update_bank_status_never_promotes_startup(self):
        tracker = BankLineageTracker()
        startup = normalize_account_update(
            {
                "slot": 101, "is_startup": True,
                "account": {
                    "pubkey": "acct", "lamports": 1, "owner": "owner",
                    "executable": False, "rent_epoch": 0, "data": b"x",
                    "write_version": 1, "txn_signature": None,
                },
            },
            stream_id="conn-1", stream_sequence=1,
        )
        self.assertEqual(tracker.account_bank_status(startup), "startup_unassigned")
        from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
        timeline = AccountUpdateTimeline()
        timeline.add(startup)
        self.assertIsNone(timeline.current_state("acct"))

    def test_account_status_resolves_exact_source_slot_and_bank_id(self):
        tracker = BankLineageTracker()
        tracker.add_slot_update(_slot(101, "SLOT_FINALIZED", bank_id=77, parent=100))
        account = normalize_account_update(
            {
                "slot": 101, "bank_id": 77,
                "account": {
                    "pubkey": "acct", "lamports": 1, "owner": "owner",
                    "executable": False, "rent_epoch": 0, "data": b"x",
                    "write_version": 1, "txn_signature": "sig",
                },
            },
            stream_id="conn-1", stream_sequence=1,
        )
        self.assertEqual(tracker.account_bank_status(account), "bank_observed_finalized")
    def test_bank_scoped_updates_are_not_paired_by_linear_timeline(self):
        from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
        timeline = AccountUpdateTimeline()
        def account_update(slot, bank_id, signature, seq):
            return normalize_account_update(
                {
                    "slot": slot, "bank_id": bank_id,
                    "account": {
                        "pubkey": "acct", "lamports": seq, "owner": "owner",
                        "executable": False, "rent_epoch": 0, "data": bytes([seq]),
                        "write_version": seq, "txn_signature": signature,
                    },
                },
                stream_id="conn-1", stream_sequence=seq,
            )
        timeline.add(account_update(100, 10, "old", 1))
        timeline.add(account_update(101, 11, "new", 2))
        self.assertEqual(timeline.transition_for("new"), ())


if __name__ == "__main__":
    unittest.main()
