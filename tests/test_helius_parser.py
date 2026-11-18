import unittest
from datetime import datetime, timezone
from decimal import Decimal

from smart_money_radar.data_sources.transaction_parser import (
    SOL_MINT,
    parse_transaction,
)


class TransactionParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wallet = "wallet-public-address"
        self.signature = "simulated-signature"
        self.transaction = {
            "blockTime": 1_730_000_000,
            "meta": {
                "err": None,
                "preTokenBalances": [
                    {
                        "owner": self.wallet,
                        "mint": "mint-usdc",
                        "uiTokenAmount": {"amount": "1500000", "decimals": 6},
                    },
                    {
                        "owner": "another-wallet",
                        "mint": "mint-ignored",
                        "uiTokenAmount": {"amount": "900", "decimals": 2},
                    },
                ],
                "postTokenBalances": [
                    {
                        "owner": self.wallet,
                        "mint": "mint-usdc",
                        "uiTokenAmount": {"amount": "2500000", "decimals": 6},
                    }
                ],
                "innerInstructions": [],
            },
            "transaction": {
                "message": {
                    "accountKeys": [{"pubkey": self.wallet}],
                    "instructions": [
                        {
                            "program": "system",
                            "parsed": {
                                "type": "transfer",
                                "info": {
                                    "source": self.wallet,
                                    "destination": "recipient-wallet",
                                    "lamports": 2_500_000_000,
                                },
                            },
                        }
                    ],
                }
            },
        }

    def test_extracts_token_and_sol_direction_amount_signature_and_time(self) -> None:
        events = parse_transaction(self.transaction, self.wallet, self.signature)

        by_mint = {event.token_mint: event for event in events}
        self.assertEqual(set(by_mint), {"mint-usdc", SOL_MINT})
        self.assertEqual(by_mint["mint-usdc"].direction, "in")
        self.assertEqual(by_mint["mint-usdc"].amount, Decimal("1"))
        self.assertEqual(by_mint[SOL_MINT].direction, "out")
        self.assertEqual(by_mint[SOL_MINT].amount, Decimal("2.5"))
        self.assertEqual(by_mint["mint-usdc"].signature, self.signature)
        self.assertEqual(
            by_mint["mint-usdc"].occurred_at,
            datetime.fromtimestamp(1_730_000_000, tz=timezone.utc),
        )

    def test_uses_none_when_rpc_does_not_supply_block_time(self) -> None:
        transaction = dict(self.transaction)
        transaction.pop("blockTime")

        events = parse_transaction(transaction, self.wallet, self.signature)

        self.assertTrue(events)
        self.assertTrue(all(event.occurred_at is None for event in events))

    def test_ignores_failed_transaction(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {**self.transaction["meta"], "err": {"InstructionError": []}}

        self.assertEqual(
            parse_transaction(transaction, self.wallet, self.signature),
            [],
        )

    def test_ignores_ambiguous_token_owner(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "postTokenBalances": [
                {
                    "mint": "mint-without-owner",
                    "uiTokenAmount": {"amount": "100", "decimals": 2},
                }
            ],
            "preTokenBalances": [],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        self.assertEqual(
            parse_transaction(transaction, self.wallet, self.signature),
            [],
        )

    def test_aggregates_multiple_token_accounts_for_same_mint(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-usdc",
                    "uiTokenAmount": {"amount": "1000000", "decimals": 6},
                },
                {
                    "owner": self.wallet,
                    "mint": "mint-usdc",
                    "uiTokenAmount": {"amount": "500000", "decimals": 6},
                },
            ],
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-usdc",
                    "uiTokenAmount": {"amount": "2000000", "decimals": 6},
                },
                {
                    "owner": self.wallet,
                    "mint": "mint-usdc",
                    "uiTokenAmount": {"amount": "500000", "decimals": 6},
                },
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        events = parse_transaction(transaction, self.wallet, self.signature)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].token_mint, "mint-usdc")
        self.assertEqual(events[0].amount, Decimal("1"))

    def test_does_not_infer_zero_balance_when_pre_balances_are_missing(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": None,
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-false-positive",
                    "uiTokenAmount": {"amount": "100", "decimals": 2},
                }
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        self.assertEqual(
            parse_transaction(transaction, self.wallet, self.signature),
            [],
        )

    def test_rejects_conflicting_decimal_scales_for_same_mint(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-conflicting-scale",
                    "uiTokenAmount": {"amount": "1000000", "decimals": 6},
                },
                {
                    "owner": self.wallet,
                    "mint": "mint-conflicting-scale",
                    "uiTokenAmount": {"amount": "100", "decimals": 2},
                },
            ],
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-conflicting-scale",
                    "uiTokenAmount": {"amount": "2000000", "decimals": 6},
                },
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        events = parse_transaction(transaction, self.wallet, self.signature)

        self.assertEqual(events, [])

    def test_rejects_decimal_scale_change_between_pre_and_post_balances(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-scale-change",
                    "uiTokenAmount": {"amount": "1000000", "decimals": 6},
                },
            ],
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-scale-change",
                    "uiTokenAmount": {"amount": "200", "decimals": 2},
                },
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        events = parse_transaction(transaction, self.wallet, self.signature)

        self.assertEqual(events, [])

    def test_rejects_invalid_spl_decimal_scale(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": [],
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-invalid-decimals",
                    "uiTokenAmount": {"amount": "100", "decimals": 256},
                }
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        self.assertEqual(
            parse_transaction(transaction, self.wallet, self.signature),
            [],
        )

    def test_rejects_boolean_decimal_scale(self) -> None:
        transaction = dict(self.transaction)
        transaction["meta"] = {
            **self.transaction["meta"],
            "preTokenBalances": [],
            "postTokenBalances": [
                {
                    "owner": self.wallet,
                    "mint": "mint-invalid-decimals",
                    "uiTokenAmount": {"amount": "100", "decimals": True},
                }
            ],
        }
        transaction["transaction"] = {"message": {"instructions": []}}

        self.assertEqual(
            parse_transaction(transaction, self.wallet, self.signature),
            [],
        )

    def test_rejects_non_integer_spl_decimal_scale(self) -> None:
        for invalid_decimals in (6.9, "6"):
            with self.subTest(decimals=invalid_decimals):
                transaction = dict(self.transaction)
                transaction["meta"] = {
                    **self.transaction["meta"],
                    "preTokenBalances": [],
                    "postTokenBalances": [{
                        "owner": self.wallet,
                        "mint": "mint-invalid-scale",
                        "uiTokenAmount": {"amount": "100", "decimals": invalid_decimals},
                    }],
                }
                transaction["transaction"] = {"message": {"instructions": []}}
                self.assertEqual(parse_transaction(transaction, self.wallet, self.signature), [])

    def test_ignores_non_integer_lamports(self) -> None:
        for invalid_lamports in (1.5, "1500000000", True):
            with self.subTest(lamports=invalid_lamports):
                transaction = {
                    "meta": {"err": None, "preTokenBalances": [], "postTokenBalances": []},
                    "transaction": {"message": {"instructions": [{
                        "program": "system",
                        "parsed": {"type": "transfer", "info": {
                            "source": self.wallet,
                            "destination": "recipient-wallet",
                            "lamports": invalid_lamports,
                        }},
                    }] }},
                }
                self.assertEqual(parse_transaction(transaction, self.wallet, self.signature), [])

    def test_timestamp_requires_integer_block_time(self) -> None:
        transaction = dict(self.transaction)
        transaction["blockTime"] = 1_730_000_000.5
        events = parse_transaction(transaction, self.wallet, self.signature)
        self.assertTrue(events)
        self.assertTrue(all(event.occurred_at is None for event in events))

    def test_extracts_system_transfer_from_inner_instruction(self) -> None:
        transaction = {
            "meta": {
                "err": None,
                "preTokenBalances": [],
                "postTokenBalances": [],
                "innerInstructions": [
                    {
                        "index": 0,
                        "instructions": [
                            {
                                "program": "system",
                                "parsed": {
                                    "type": "transfer",
                                    "info": {
                                        "source": "sender-wallet",
                                        "destination": self.wallet,
                                        "lamports": 750_000_000,
                                    },
                                },
                            }
                        ],
                    }
                ],
            },
            "transaction": {"message": {"instructions": []}},
        }

        events = parse_transaction(transaction, self.wallet, self.signature)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].token_mint, SOL_MINT)
        self.assertEqual(events[0].direction, "in")
        self.assertEqual(events[0].amount, Decimal("0.75"))


if __name__ == "__main__":
    unittest.main()