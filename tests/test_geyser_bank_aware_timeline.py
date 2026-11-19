import unittest

from smart_money_radar.data_sources.geyser_account_updates import normalize_account_update
from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline
from smart_money_radar.data_sources.geyser_bank_lineage import (
    normalize_block_meta,
    normalize_entry_update_parent,
    normalize_slot_update,
)


def _account(slot, bank_id, signature, sequence, *, stream="stream-1", write_version=1):
    return normalize_account_update(
        {
            "slot": slot,
            "bank_id": bank_id,
            "account": {
                "pubkey": "wallet-account",
                "lamports": sequence,
                "owner": "token-program",
                "executable": False,
                "rent_epoch": 0,
                "data": f"state-{sequence}".encode(),
                "write_version": write_version,
                "txn_signature": signature,
            },
        },
        stream_id=stream,
        stream_sequence=sequence,
        source="validator-A",
    )


def _slot(slot, status, bank_id=None, parent=None, sequence=1):
    return normalize_slot_update(
        {"slot": slot, "status": status, "bank_id": bank_id, "parent": parent},
        source_id="validator-A", stream_id="stream-1", stream_sequence=sequence,
    )


def _block(slot, bank_id, blockhash, parent_slot, parent_blockhash, sequence=1):
    return normalize_block_meta(
        {
            "slot": slot, "bank_id": bank_id, "blockhash": blockhash,
            "parent_slot": parent_slot, "parent_blockhash": parent_blockhash,
        },
        source_id="validator-A", stream_id="stream-1", stream_sequence=sequence,
    )


class BankAwareAccountTimelineTests(unittest.TestCase):
    def test_same_bank_pre_post_pair_is_allowed_when_bank_is_observed(self):
        timeline = AccountUpdateTimeline()
        timeline.add_slot_update(_slot(100, "SLOT_CREATED_BANK", 10, 99))
        timeline.add(_account(100, 10, "before", 1, write_version=10))
        timeline.add(_account(100, 10, "target", 2, write_version=11))
        result = timeline.transition_for("target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_state.txn_signature, "before")

    def test_cross_bank_pair_requires_exact_parent_blockhash_chain(self):
        timeline = AccountUpdateTimeline()
        timeline.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        timeline.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash", 2))
        timeline.add(_account(100, 10, "before", 1, write_version=10))
        timeline.add(_account(101, 11, "target", 2, write_version=11))
        result = timeline.transition_for("target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_state.txn_signature, "before")

    def test_sibling_forks_are_never_paired(self):
        timeline = AccountUpdateTimeline()
        timeline.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        timeline.add_block_meta(_block(101, 11, "fork-a", 100, "parent-hash", 2))
        timeline.add_block_meta(_block(101, 12, "fork-b", 100, "parent-hash", 3))
        timeline.add(_account(101, 11, "fork-a-write", 1, write_version=10))
        timeline.add(_account(101, 12, "target", 2, write_version=11))
        self.assertEqual(timeline.transition_for("target"), ())

    def test_parent_slot_without_parent_blockhash_proof_is_not_enough(self):
        timeline = AccountUpdateTimeline()
        timeline.add_slot_update(_slot(100, "SLOT_CREATED_BANK", 10, 99))
        timeline.add_slot_update(_slot(101, "SLOT_CREATED_BANK", 11, 100, 2))
        timeline.add(_account(100, 10, "before", 1))
        timeline.add(_account(101, 11, "target", 2))
        self.assertEqual(timeline.transition_for("target"), ())

    def test_entry_update_parent_invalidates_old_bank_prestate(self):
        timeline = AccountUpdateTimeline()
        timeline.add_slot_update(_slot(101, "SLOT_CREATED_BANK", 10, 100))
        timeline.add(_account(101, 10, "old-fork", 1, write_version=10))
        event = normalize_entry_update_parent(
            {
                "slot": 101, "cleared_bank_id": 10,
                "parent_slot": 100, "parent_block_id": b"opaque-parent",
            },
            source_id="validator-A", stream_id="stream-1", stream_sequence=2,
        )
        timeline.add_entry_update_parent(event)
        timeline.add_slot_update(_slot(101, "SLOT_CREATED_BANK", 11, 100, 3))
        timeline.add(_account(101, 11, "target", 3, write_version=11))
        self.assertEqual(timeline.transition_for("target"), ())

    def test_dead_ancestor_blocks_cross_bank_transition(self):
        timeline = AccountUpdateTimeline()
        timeline.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        timeline.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash", 2))
        timeline.add(_account(100, 10, "before", 1, write_version=10))
        timeline.add(_account(101, 11, "target", 2, write_version=11))
        timeline.add_slot_update(_slot(100, "SLOT_DEAD", 10, sequence=3))
        self.assertEqual(timeline.transition_for("target"), ())

    def test_metadata_arriving_after_account_updates_can_resolve_pair(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_account(100, 10, "before", 1, write_version=10))
        timeline.add(_account(101, 11, "target", 2, write_version=11))
        self.assertEqual(timeline.transition_for("target"), ())
        timeline.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        timeline.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash", 2))
        self.assertEqual(len(timeline.transition_for("target")), 1)

    def test_reconnect_creates_new_baseline_before_pairing_resumes(self):
        timeline = AccountUpdateTimeline()
        timeline.add_slot_update(_slot(100, "SLOT_CREATED_BANK", 10, 99))
        timeline.add(_account(100, 10, "before-reconnect", 1))
        gap = timeline.add(_account(100, 10, "after-reconnect", 1, stream="stream-2", write_version=2))
        self.assertIsNotNone(gap.gap)
        self.assertEqual(timeline.transition_for("after-reconnect"), ())
        timeline.add(_account(100, 10, "continuous", 2, stream="stream-2", write_version=3))
        result = timeline.transition_for("continuous")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_state.txn_signature, "after-reconnect")

    def test_exact_replay_is_idempotent_in_bank_aware_timeline(self):
        timeline = AccountUpdateTimeline()
        timeline.add_slot_update(_slot(100, "SLOT_CREATED_BANK", 10, 99))
        first = _account(100, 10, "same", 1)
        from dataclasses import replace
        replay = replace(first, stream_sequence=2)
        self.assertEqual(timeline.add(first).status, "inserted")
        self.assertEqual(timeline.add(replay).status, "duplicate")
        self.assertEqual(len(timeline.events_for("wallet-account")), 1)

    def test_legacy_unscoped_pair_does_not_skip_intervening_bank_scoped_write(self):
        timeline = AccountUpdateTimeline()
        before = normalize_account_update(
            {
                "slot": 100,
                "account": {
                    "pubkey": "wallet-account", "lamports": 1, "owner": "token-program",
                    "executable": False, "rent_epoch": 0, "data": b"legacy",
                    "write_version": 1, "txn_signature": "legacy-before",
                },
            },
            stream_id="stream-1", stream_sequence=1, source="validator-A",
        )
        fork_scoped = _account(101, 10, "fork-write", 2, write_version=2)
        target = normalize_account_update(
            {
                "slot": 102,
                "account": {
                    "pubkey": "wallet-account", "lamports": 3, "owner": "token-program",
                    "executable": False, "rent_epoch": 0, "data": b"legacy-target",
                    "write_version": 3, "txn_signature": "legacy-target",
                },
            },
            stream_id="stream-1", stream_sequence=3, source="validator-A",
        )
        timeline.add(before)
        timeline.add(fork_scoped)
        timeline.add(target)
        self.assertEqual(timeline.transition_for("legacy-target"), ())

    def test_account_updates_arriving_out_of_ledger_order_reconcile_after_sorting(self):
        timeline = AccountUpdateTimeline()
        timeline.add_block_meta(_block(100, 10, "parent-hash", 99, "grandparent-hash"))
        timeline.add_block_meta(_block(101, 11, "child-hash", 100, "parent-hash", 2))
        # The child/post-state arrives first. Its baseline flag must not prevent
        # pairing once an earlier ancestor write arrives in the same continuity epoch.
        timeline.add(_account(101, 11, "target", 1, write_version=11))
        self.assertEqual(timeline.transition_for("target"), ())
        timeline.add(_account(100, 10, "before", 2, write_version=10))
        result = timeline.transition_for("target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pre_state.txn_signature, "before")


if __name__ == "__main__":
    unittest.main()
