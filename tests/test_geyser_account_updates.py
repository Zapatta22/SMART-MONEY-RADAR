import unittest

from smart_money_radar.data_sources.geyser_account_updates import (
    NormalizedAccountUpdate,
    normalize_account_update,
)


def _payload(**account_overrides):
    account = {
        "pubkey": "token-account",
        "lamports": 2_039_280,
        "owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        "executable": False,
        "rent_epoch": 0,
        "data": b"raw-account-bytes",
        "write_version": 77,
        "txn_signature": "signature-1",
    }
    account.update(account_overrides)
    return {"slot": 123_456, "account": account}


class NormalizeAccountUpdateTests(unittest.TestCase):
    def test_normalizes_complete_account_update_and_preserves_bytes(self):
        result = normalize_account_update(
            _payload(), stream_id="connection-1", stream_sequence=9
        )
        self.assertIsInstance(result, NormalizedAccountUpdate)
        self.assertEqual(result.pubkey, "token-account")
        self.assertEqual(result.slot, 123_456)
        self.assertEqual(result.write_version, 77)
        self.assertEqual(result.txn_signature, "signature-1")
        self.assertEqual(result.data, b"raw-account-bytes")
        self.assertEqual(result.ordering_key, (123_456, 77, 9))
        self.assertEqual(result.stream_id, "connection-1")
        self.assertEqual(result.stream_sequence, 9)

    def test_missing_transaction_signature_is_preserved_as_none(self):
        result = normalize_account_update(
            _payload(txn_signature=None),
            stream_id="connection-1",
            stream_sequence=1,
        )
        self.assertIsNone(result.txn_signature)

    def test_empty_transaction_signature_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "txn_signature"):
            normalize_account_update(
                _payload(txn_signature=""),
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_non_mapping_payload(self):
        with self.assertRaises(TypeError):
            normalize_account_update(
                [], stream_id="connection-1", stream_sequence=1
            )

    def test_rejects_missing_account_envelope(self):
        with self.assertRaisesRegex(ValueError, "account"):
            normalize_account_update(
                {"slot": 1}, stream_id="connection-1", stream_sequence=1
            )

    def test_rejects_boolean_as_u64(self):
        with self.assertRaisesRegex(ValueError, "slot"):
            normalize_account_update(
                {"slot": True, "account": _payload()["account"]},
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_negative_write_version(self):
        with self.assertRaisesRegex(ValueError, "write_version"):
            normalize_account_update(
                _payload(write_version=-1),
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_missing_write_version(self):
        account = _payload()["account"]
        account.pop("write_version")
        with self.assertRaisesRegex(ValueError, "write_version"):
            normalize_account_update(
                {"slot": 1, "account": account},
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_non_boolean_executable(self):
        with self.assertRaisesRegex(ValueError, "executable"):
            normalize_account_update(
                _payload(executable=0),
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_encoded_string_instead_of_raw_bytes(self):
        with self.assertRaisesRegex(ValueError, "bytes"):
            normalize_account_update(
                _payload(data="cmF3"),
                stream_id="connection-1",
                stream_sequence=1,
            )

    def test_rejects_invalid_stream_metadata(self):
        with self.assertRaisesRegex(ValueError, "stream_id"):
            normalize_account_update(
                _payload(), stream_id=" ", stream_sequence=1
            )
        with self.assertRaisesRegex(ValueError, "stream_sequence"):
            normalize_account_update(
                _payload(), stream_id="connection-1", stream_sequence=True
            )

    def test_state_hash_is_stable_and_changes_with_account_bytes(self):
        first = normalize_account_update(
            _payload(), stream_id="connection-1", stream_sequence=1
        )
        same_state = normalize_account_update(
            _payload(), stream_id="connection-2", stream_sequence=99
        )
        changed_state = normalize_account_update(
            _payload(data=b"different"), stream_id="connection-1", stream_sequence=1
        )
        self.assertEqual(first.state_hash, same_state.state_hash)
        self.assertNotEqual(first.state_hash, changed_state.state_hash)

    def test_event_fingerprint_binds_transaction_and_write_identity(self):
        first = normalize_account_update(
            _payload(), stream_id="connection-1", stream_sequence=1
        )
        other_signature = normalize_account_update(
            _payload(txn_signature="signature-2"),
            stream_id="connection-1",
            stream_sequence=1,
        )
        other_write = normalize_account_update(
            _payload(write_version=78),
            stream_id="connection-1",
            stream_sequence=1,
        )
        self.assertNotEqual(first.event_fingerprint, other_signature.event_fingerprint)
        self.assertNotEqual(first.event_fingerprint, other_write.event_fingerprint)


if __name__ == "__main__":
    unittest.main()
