import unittest
from types import SimpleNamespace

from smart_money_radar.data_sources.damm_v2_delta_coverage_audit import (
    summarize_four_account_delta_coverage,
)


def _accounts():
    return SimpleNamespace(
        input_token_account="user-in",
        input_vault="vault-in",
        output_vault="vault-out",
        output_token_account="user-out",
        input_mint="mint-in",
        output_mint="mint-out",
    )


def _delta(account, mint, amount):
    return SimpleNamespace(token_account=account, mint=mint, delta_raw=amount)


def _result(deltas, complete=True):
    return SimpleNamespace(deltas=tuple(deltas), complete=complete)


class DammV2DeltaCoverageAuditTests(unittest.TestCase):
    def test_requires_all_four_distinct_account_deltas_with_expected_signs(self):
        result = _result([
            _delta("user-in", "mint-in", -100),
            _delta("vault-in", "mint-in", 100),
            _delta("vault-out", "mint-out", -90),
            _delta("user-out", "mint-out", 90),
        ])
        self.assertEqual(
            summarize_four_account_delta_coverage(_accounts(), result),
            "FOUR_ACCOUNT_DELTAS_PRESENT",
        )

    def test_missing_any_required_delta_is_not_treated_as_zero(self):
        result = _result([
            _delta("user-in", "mint-in", -100),
            _delta("vault-in", "mint-in", 100),
            _delta("vault-out", "mint-out", -90),
        ])
        self.assertEqual(
            summarize_four_account_delta_coverage(_accounts(), result),
            "FOUR_ACCOUNT_DELTA_MISSING",
        )

    def test_incomplete_global_snapshot_set_fails_closed(self):
        result = _result([
            _delta("user-in", "mint-in", -100),
            _delta("vault-in", "mint-in", 100),
            _delta("vault-out", "mint-out", -90),
            _delta("user-out", "mint-out", 90),
        ], complete=False)
        self.assertEqual(
            summarize_four_account_delta_coverage(_accounts(), result),
            "SNAPSHOT_SET_INCOMPLETE",
        )

    def test_rejects_account_role_collision(self):
        accounts = _accounts()
        accounts = SimpleNamespace(**{
            **accounts.__dict__,
            "output_token_account": "user-in",
        })
        self.assertEqual(
            summarize_four_account_delta_coverage(accounts, _result([])),
            "ACCOUNT_ROLE_COLLISION",
        )

    def test_rejects_mint_role_mismatch(self):
        result = _result([
            _delta("user-in", "wrong-mint", -100),
            _delta("vault-in", "mint-in", 100),
            _delta("vault-out", "mint-out", -90),
            _delta("user-out", "mint-out", 90),
        ])
        self.assertEqual(
            summarize_four_account_delta_coverage(_accounts(), result),
            "MINT_ROLE_MISMATCH",
        )

    def test_rejects_inconsistent_delta_signs(self):
        result = _result([
            _delta("user-in", "mint-in", 100),
            _delta("vault-in", "mint-in", -100),
            _delta("vault-out", "mint-out", -90),
            _delta("user-out", "mint-out", 90),
        ])
        self.assertEqual(
            summarize_four_account_delta_coverage(_accounts(), result),
            "DELTA_SIGN_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
