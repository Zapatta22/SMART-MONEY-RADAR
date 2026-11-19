import unittest

from smart_money_radar.data_sources.geyser_account_updates import normalize_account_update
from smart_money_radar.data_sources.geyser_account_timeline import AccountUpdateTimeline


def _update(
    *,
    pubkey="account-A",
    slot=100,
    write_version=1,
    signature="sig-1",
    sequence=1,
    stream="stream-1",
    data=b"state",
):
    return normalize_account_update(
        {
            "slot": slot,
            "account": {
                "pubkey": pubkey,
                "lamports": 1_000,
                "owner": "owner-program",
                "executable": False,
                "rent_epoch": 0,
                "data": data,
                "write_version": write_version,
                "txn_signature": signature,
            },
        },
        stream_id=stream,
        stream_sequence=sequence,
    )


class AccountUpdateTimelineTests(unittest.TestCase):
    def test_first_write_is_baseline_and_next_write_has_exact_pre_post(self):
        timeline = AccountUpdateTimeline()
        first = _update(slot=100, write_version=10, signature="prior", sequence=1, data=b"pre")
        second = _update(slot=101, write_version=11, signature="target", sequence=2, data=b"post")
        self.assertEqual(timeline.add(first).status, "inserted")
        self.assertEqual(timeline.transition_for("prior"), ())
        self.assertEqual(timeline.add(second).status, "inserted")
        transitions = timeline.transition_for("target")
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].pre_state.data, b"pre")
        self.assertEqual(transitions[0].post_state.data, b"post")

    def test_ledger_order_is_slot_then_write_version_not_delivery_order(self):
        timeline = AccountUpdateTimeline()
        later = _update(slot=102, write_version=20, signature="later", sequence=1)
        earlier = _update(slot=101, write_version=19, signature="earlier", sequence=2)
        timeline.add(later)
        timeline.add(earlier)
        self.assertEqual(
            [(item.slot, item.write_version) for item in timeline.events_for("account-A")],
            [(101, 19), (102, 20)],
        )
        self.assertEqual(timeline.current_state("account-A").slot, 102)

    def test_exact_replay_is_idempotent_even_with_new_delivery_sequence(self):
        timeline = AccountUpdateTimeline()
        first = _update(sequence=1)
        replay = _update(sequence=2)
        self.assertEqual(timeline.add(first).status, "inserted")
        self.assertEqual(timeline.add(replay).status, "duplicate")
        self.assertEqual(len(timeline.events_for("account-A")), 1)

    def test_same_ledger_write_identity_with_different_state_is_conflict(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(sequence=1, data=b"original"))
        result = timeline.add(_update(sequence=2, data=b"mutated"))
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict.reason, "ledger_write_identity_collision")
        self.assertEqual(len(timeline.events_for("account-A")), 1)

    def test_stream_sequence_gap_blocks_pair_for_first_update_after_gap(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(slot=100, write_version=1, signature="before", sequence=10))
        result = timeline.add(
            _update(slot=101, write_version=2, signature="after-gap", sequence=12)
        )
        self.assertIsNotNone(result.gap)
        self.assertEqual(result.gap.expected_sequence, 11)
        self.assertEqual(timeline.transition_for("after-gap"), ())
        timeline.add(_update(slot=102, write_version=3, signature="continuous", sequence=13))
        transition = timeline.transition_for("continuous")
        self.assertEqual(len(transition), 1)
        self.assertEqual(transition[0].pre_state.txn_signature, "after-gap")

    def test_stream_change_is_a_reconnect_boundary(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(slot=100, write_version=1, signature="old", sequence=50))
        result = timeline.add(
            _update(slot=101, write_version=2, signature="new-stream", sequence=1, stream="stream-2")
        )
        self.assertEqual(result.gap.reason, "stream_changed_or_reconnected")
        self.assertEqual(timeline.transition_for("new-stream"), ())
        timeline.add(
            _update(slot=102, write_version=3, signature="next", sequence=2, stream="stream-2")
        )
        self.assertEqual(len(timeline.transition_for("next")), 1)

    def test_missing_transaction_signature_is_never_targeted(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(slot=100, write_version=1, signature="prior", sequence=1))
        timeline.add(_update(slot=101, write_version=2, signature=None, sequence=2))
        self.assertEqual(timeline.transition_for("prior"), ())
        with self.assertRaises(ValueError):
            timeline.transition_for(" ")

    def test_reused_stream_sequence_with_different_event_is_conflict(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(sequence=1, data=b"one"))
        result = timeline.add(_update(sequence=1, data=b"two"))
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict.reason, "stream_sequence_reused_for_different_event")

    def test_unrecognized_out_of_order_stream_sequence_is_conflict(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(sequence=5))
        result = timeline.add(_update(slot=101, write_version=2, signature="older-seq", sequence=4))
        self.assertEqual(result.status, "conflict")
        self.assertEqual(result.conflict.reason, "unrecognized_out_of_order_stream_sequence")

    def test_rollback_preserves_orphaned_updates_and_invalidates_next_prestate(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(slot=100, write_version=1, signature="canonical", sequence=1))
        timeline.add(_update(slot=101, write_version=2, signature="orphan", sequence=2))
        removed = timeline.rollback_from_slot(101)
        self.assertEqual([item.txn_signature for item in removed], ["orphan"])
        self.assertEqual([item.txn_signature for item in timeline.orphaned_updates], ["orphan"])
        self.assertEqual(timeline.current_state("account-A").txn_signature, "canonical")
        timeline.add(_update(slot=102, write_version=3, signature="after-rollback", sequence=3))
        self.assertEqual(timeline.transition_for("after-rollback"), ())
        timeline.add(_update(slot=103, write_version=4, signature="stable-again", sequence=4))
        self.assertEqual(len(timeline.transition_for("stable-again")), 1)

    def test_rollback_rejects_invalid_slot(self):
        timeline = AccountUpdateTimeline()
        with self.assertRaises(ValueError):
            timeline.rollback_from_slot(True)

    def test_current_state_is_hidden_when_history_contains_bank_scoped_forks(self):
        timeline = AccountUpdateTimeline()
        update = normalize_account_update(
            {
                "slot": 100, "bank_id": 7,
                "account": {
                    "pubkey": "account-A", "lamports": 1, "owner": "owner-program",
                    "executable": False, "rent_epoch": 0, "data": b"state",
                    "write_version": 1, "txn_signature": "sig",
                },
            },
            stream_id="stream-1", stream_sequence=1,
        )
        timeline.add(update)
        self.assertIsNone(timeline.current_state("account-A"))
    def test_accounts_are_tracked_independently(self):
        timeline = AccountUpdateTimeline()
        timeline.add(_update(pubkey="A", slot=100, write_version=1, signature="a1", sequence=1))
        timeline.add(_update(pubkey="B", slot=100, write_version=1, signature="b1", sequence=2))
        timeline.add(_update(pubkey="A", slot=101, write_version=2, signature="a2", sequence=3))
        self.assertEqual(len(timeline.transition_for("a2")), 1)
        self.assertEqual(timeline.transition_for("b1"), ())
        self.assertIsNone(timeline.current_state("C"))


if __name__ == "__main__":
    unittest.main()
