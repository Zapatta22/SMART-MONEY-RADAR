import unittest

from smart_money_radar.data_sources.raydium_cpmm_accounts import RaydiumCpmmAccounts
from smart_money_radar.data_sources.raydium_cpmm_decoder import RaydiumCpmmSwapBaseInput
from smart_money_radar.data_sources.raydium_cpmm_analyzer import RaydiumCpmmDecodedSwap
from smart_money_radar.data_sources.raydium_cpmm_transfer_reconciliation import (
    reconcile_raydium_cpmm_swaps,
)
from smart_money_radar.data_sources.solana_token_balance_deltas import (
    TokenAccountBalanceDelta,
)
from smart_money_radar.data_sources.solana_token_transfer_decoder import (
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    SolanaTokenTransfer,
)


WALLET = "wallet-1"
INPUT_ACCOUNT = "user-input"
OUTPUT_ACCOUNT = "user-output"
INPUT_VAULT = "pool-input-vault"
OUTPUT_VAULT = "pool-output-vault"
INPUT_MINT = "mint-input"
OUTPUT_MINT = "mint-output"


def _accounts(input_account=INPUT_ACCOUNT, output_account=OUTPUT_ACCOUNT, input_program=SPL_TOKEN_PROGRAM_ID, output_program=SPL_TOKEN_PROGRAM_ID):
    return RaydiumCpmmAccounts(
        payer="fee-payer",
        authority="pool-authority",
        amm_config="amm-config",
        pool_state="pool",
        input_token_account=input_account,
        output_token_account=output_account,
        input_vault=INPUT_VAULT,
        output_vault=OUTPUT_VAULT,
        input_token_program=input_program,
        output_token_program=output_program,
        input_token_mint=INPUT_MINT,
        output_token_mint=OUTPUT_MINT,
        observation_state="observation",
    )


def _swap(path=(), inner_index=None, stack_height=1, input_account=INPUT_ACCOUNT, output_account=OUTPUT_ACCOUNT, input_program=SPL_TOKEN_PROGRAM_ID, output_program=SPL_TOKEN_PROGRAM_ID):
    return RaydiumCpmmDecodedSwap(
        instruction_index=0,
        instruction=RaydiumCpmmSwapBaseInput(
            amount_in=999999, minimum_amount_out=1
        ),
        accounts=_accounts(input_account, output_account, input_program, output_program),
        cpi_path=path,
        stack_height=stack_height,
        inner_instruction_index=inner_index,
    )


def _transfer(source, destination, amount, inner_index, path, stack_height, program_id=SPL_TOKEN_PROGRAM_ID):
    return SolanaTokenTransfer(
        program_id=program_id,
        program_name="Token-2022" if program_id == TOKEN_2022_PROGRAM_ID else "SPL Token",
        instruction_type="TRANSFER_CHECKED",
        instruction_index=0,
        inner_instruction_index=inner_index,
        stack_height=stack_height,
        cpi_path=path,
        source_account=source,
        destination_account=destination,
        authority="token-authority",
        mint=INPUT_MINT if source == INPUT_ACCOUNT else OUTPUT_MINT,
        amount_raw=amount,
        decimals=6,
        execution_status="EXECUTED",
        source_format="compiled",
    )


def _deltas(input_delta=-100, output_delta=90, input_owner=WALLET, output_owner=WALLET, input_vault_delta=100, output_vault_delta=-90):
    return [
        TokenAccountBalanceDelta(
            account_index=0,
            token_account=INPUT_ACCOUNT,
            mint=INPUT_MINT,
            owner=input_owner,
            pre_amount_raw=1000,
            post_amount_raw=1000 + input_delta,
            delta_raw=input_delta,
            decimals=6,
        ),
        TokenAccountBalanceDelta(
            account_index=1,
            token_account=OUTPUT_ACCOUNT,
            mint=OUTPUT_MINT,
            owner=output_owner,
            pre_amount_raw=2000,
            post_amount_raw=2000 + output_delta,
            delta_raw=output_delta,
            decimals=6,
        ),
        TokenAccountBalanceDelta(
            account_index=2,
            token_account=INPUT_VAULT,
            mint=INPUT_MINT,
            owner="pool-authority",
            pre_amount_raw=10000,
            post_amount_raw=10000 + input_vault_delta,
            delta_raw=input_vault_delta,
            decimals=6,
        ),
        TokenAccountBalanceDelta(
            account_index=3,
            token_account=OUTPUT_VAULT,
            mint=OUTPUT_MINT,
            owner="pool-authority",
            pre_amount_raw=20000,
            post_amount_raw=20000 + output_vault_delta,
            delta_raw=output_vault_delta,
            decimals=6,
        ),
    ]


def _pair(input_amount=100, output_amount=90, path=(), first_index=0, height=2, input_program=SPL_TOKEN_PROGRAM_ID, output_program=SPL_TOKEN_PROGRAM_ID):
    return [
        _transfer(INPUT_ACCOUNT, INPUT_VAULT, input_amount, first_index, path, height, input_program),
        _transfer(OUTPUT_VAULT, OUTPUT_ACCOUNT, output_amount, first_index + 1, path, height, output_program),
    ]


class RaydiumCpmmTransferReconciliationTests(unittest.TestCase):
    def test_matches_outer_swap_using_exact_transfers_and_account_deltas(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(), _deltas(), monitored_wallet=WALLET
        )[0]
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.wallet_address, WALLET)
        self.assertEqual(result.input_amount_raw, 100)
        self.assertEqual(result.output_amount_raw, 90)
        # Instruction arguments are deliberately different and are not used.
        self.assertNotEqual(result.input_amount_raw, result.swap.instruction.amount_in)

    def test_matches_inner_swap_only_with_proven_descendant_cpi_paths(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap(path=(2,), inner_index=3, stack_height=3)],
            _pair(path=(2, 0), height=4),
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "MATCHED")

    def test_does_not_attribute_sibling_cpi_transfers_to_inner_swap(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap(path=(2,), inner_index=3, stack_height=3)],
            _pair(path=(3,), height=3),
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("exatamente uma", result.reason)

    def test_inner_swap_rejects_transfer_with_untrusted_cpi_path(self):
        transfers = _pair(path=(2, 0), height=4)
        transfers[0] = SolanaTokenTransfer(
            **{**transfers[0].__dict__, "cpi_path_valid": False}
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap(path=(2,), inner_index=3, stack_height=3)],
            transfers,
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")

    def test_outer_swap_remains_scoped_to_its_inner_instruction_group(self):
        transfers = _pair(path=(2, 0), height=4)
        transfers[0] = SolanaTokenTransfer(
            **{**transfers[0].__dict__, "cpi_path_valid": False}
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap()],
            transfers,
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "MATCHED")

    def test_inner_swap_without_stack_height_is_not_reconciled(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap(path=(2,), inner_index=3, stack_height=None)],
            _pair(path=(2, 0), height=None),
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")

    def test_requires_exactly_one_transfer_per_side(self):
        transfers = _pair() + [
            _transfer(INPUT_ACCOUNT, INPUT_VAULT, 100, 2, (2,), 2)
        ]
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], transfers, _deltas(), monitored_wallet=WALLET
        )[0]
        self.assertEqual(result.status, "AMBIGUOUS")

    def test_rejects_mismatched_token_program(self):
        transfers = _pair()
        transfers[0] = SolanaTokenTransfer(
            **{**transfers[0].__dict__, "program_id": "wrong-token-program"}
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], transfers, _deltas(), monitored_wallet=WALLET
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("Programa SPL", result.reason)

    def test_rejects_mismatched_mint_delta(self):
        deltas = _deltas()
        deltas[0] = TokenAccountBalanceDelta(
            account_index=0, token_account=INPUT_ACCOUNT, mint="wrong-mint",
            owner=WALLET, pre_amount_raw=1000, post_amount_raw=900,
            delta_raw=-100, decimals=6,
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(), deltas, monitored_wallet=WALLET
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("Mint do delta", result.reason)

    def test_rejects_transfer_amounts_that_do_not_reconcile_to_net_account_deltas(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(input_amount=101), _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("não reconcilia", result.reason)

    def test_rejects_transfer_fee_or_unparsed_transfer_effect(self):
        # Gross transfer amount is 100, but destination net balance only rose 89.
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(output_amount=100), _deltas(output_delta=89),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("não reconcilia", result.reason)

    def test_rejects_token2022_transfer_fee_between_user_debit_and_vault_credit(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap(input_program=TOKEN_2022_PROGRAM_ID)],
            _pair(input_program=TOKEN_2022_PROGRAM_ID),
            _deltas(input_vault_delta=90),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("vault de entrada", result.reason)
        self.assertIn("não reconcilia", result.reason)

    def test_reconciles_transfer_checked_with_fee_using_net_destination_credit(self):
        transfers = _pair(
            input_amount=100,
            output_amount=100,
            input_program=TOKEN_2022_PROGRAM_ID,
            output_program=TOKEN_2022_PROGRAM_ID,
        )
        transfers[0] = SolanaTokenTransfer(
            **{
                **transfers[0].__dict__,
                "instruction_type": "TRANSFER_CHECKED_WITH_FEE",
                "fee_amount_raw": 10,
            }
        )
        transfers[1] = SolanaTokenTransfer(
            **{
                **transfers[1].__dict__,
                "instruction_type": "TRANSFER_CHECKED_WITH_FEE",
                "fee_amount_raw": 5,
            }
        )
        deltas = _deltas(
            input_delta=-100,
            output_delta=95,
            input_vault_delta=90,
            output_vault_delta=-100,
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap(
                input_program=TOKEN_2022_PROGRAM_ID,
                output_program=TOKEN_2022_PROGRAM_ID,
            )],
            transfers,
            deltas,
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "MATCHED")
        self.assertEqual(result.input_amount_raw, 100)
        self.assertEqual(result.output_amount_raw, 95)
        self.assertEqual(result.input_token_account_delta_raw, -100)
        self.assertEqual(result.output_token_account_delta_raw, 95)
        self.assertEqual(result.input_vault_delta_raw, 90)
        self.assertEqual(result.output_vault_delta_raw, -100)

    def test_rejects_invalid_fee_amount_on_fee_checked_transfer(self):
        transfers = _pair(
            input_program=TOKEN_2022_PROGRAM_ID,
            output_program=TOKEN_2022_PROGRAM_ID,
        )
        transfers[0] = SolanaTokenTransfer(
            **{
                **transfers[0].__dict__,
                "instruction_type": "TRANSFER_CHECKED_WITH_FEE",
                "fee_amount_raw": 101,
            }
        )
        result = reconcile_raydium_cpmm_swaps(
            [_swap(
                input_program=TOKEN_2022_PROGRAM_ID,
                output_program=TOKEN_2022_PROGRAM_ID,
            )],
            transfers,
            _deltas(),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("fora dos tipos base", result.reason)

    def test_requires_pool_vault_deltas(self):
        deltas = [item for item in _deltas() if item.token_account != INPUT_VAULT]
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(), deltas, monitored_wallet=WALLET
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("Falta delta pre/post de um vault", result.reason)

    def test_requires_both_user_token_accounts_to_belong_to_monitored_wallet(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(), _deltas(output_owner="other-wallet"),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")
        self.assertIn("pertencem", result.reason)

    def test_does_not_assume_fee_payer_is_economic_owner(self):
        result = reconcile_raydium_cpmm_swaps(
            [_swap()], _pair(), _deltas(input_owner="another-wallet", output_owner="another-wallet"),
            monitored_wallet=WALLET,
        )[0]
        self.assertEqual(result.status, "INCOMPLETE")

    def test_reconciles_multiple_swaps_sharing_user_accounts_without_splitting_net_delta(self):
        first = _swap(path=(0,), inner_index=0, stack_height=2)
        second = _swap(path=(1,), inner_index=3, stack_height=2)
        transfers = (
            _pair(100, 90, path=(0, 0), first_index=1, height=3)
            + _pair(50, 50, path=(1, 0), first_index=5, height=3)
        )
        results = reconcile_raydium_cpmm_swaps(
            [first, second],
            transfers,
            _deltas(input_delta=-150, output_delta=140, input_vault_delta=150, output_vault_delta=-140),
            monitored_wallet=WALLET,
        )
        self.assertEqual([item.status for item in results], ["MATCHED", "MATCHED"])
        self.assertEqual(
            [(item.input_amount_raw, item.output_amount_raw) for item in results],
            [(100, 90), (50, 50)],
        )

    def test_outer_swap_is_ambiguous_when_another_cpmm_swap_is_nested_in_its_group(self):
        outer = _swap()
        nested = _swap(path=(0,), inner_index=0, stack_height=2)
        results = reconcile_raydium_cpmm_swaps(
            [outer, nested],
            _pair(),
            _deltas(),
            monitored_wallet=WALLET,
        )
        self.assertEqual(results[0].status, "AMBIGUOUS")

    def test_marks_reused_transfer_as_ambiguous_for_both_nested_swaps(self):
        parent = _swap(path=(0,), inner_index=0, stack_height=2)
        child = _swap(path=(0, 0), inner_index=1, stack_height=3)
        transfers = [
            _transfer(INPUT_ACCOUNT, INPUT_VAULT, 100, 2, (0, 0, 0), 4),
            _transfer(OUTPUT_VAULT, OUTPUT_ACCOUNT, 90, 3, (0, 0, 1), 4),
        ]
        results = reconcile_raydium_cpmm_swaps(
            [parent, child], transfers, _deltas(), monitored_wallet=WALLET
        )
        self.assertEqual([item.status for item in results], ["AMBIGUOUS", "AMBIGUOUS"])
        self.assertTrue(all("reivindicada" in item.reason for item in results))

    def test_rejects_duplicate_delta_accounts(self):
        deltas = _deltas() + _deltas()[:1]
        with self.assertRaisesRegex(ValueError, "duplicada"):
            reconcile_raydium_cpmm_swaps(
                [_swap()], _pair(), deltas, monitored_wallet=WALLET
            )

    def test_requires_monitored_wallet(self):
        with self.assertRaisesRegex(ValueError, "monitored_wallet"):
            reconcile_raydium_cpmm_swaps(
                [_swap()], _pair(), _deltas(), monitored_wallet=""
            )


if __name__ == "__main__":
    unittest.main()
