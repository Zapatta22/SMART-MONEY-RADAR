"""Proof that a Token-2022 mint cannot assess transfer fees.

The proof uses a protocol invariant: TransferFeeConfig initialization requires an
uninitialized mint. If a successfully-used mint has no TransferFeeConfig in a
later finalized snapshot, the extension could not have existed at the earlier
transaction position and then been removed.
"""
from __future__ import annotations

from dataclasses import dataclass

from smart_money_radar.data_sources.token2022_transfer_fee_state import (
    transfer_fee_config_present,
)

TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_2022_SOURCE_COMMIT = "875693f53c77534b46f0d06bdf781430870f8177"


@dataclass(frozen=True, slots=True)
class Token2022NoTransferFeeProof:
    mint: str
    signature: str
    transaction_slot: int
    transaction_index: int
    current_snapshot_slot: int
    owner: str
    transaction_successful: bool
    mint_transfer_observed: bool
    transfer_fee_config_present: bool
    source_commit: str = TOKEN_2022_SOURCE_COMMIT

    def __post_init__(self) -> None:
        if not self.mint.strip() or not self.signature.strip():
            raise ValueError("mint e signature são obrigatórios")
        for name, value in (
            ("transaction_slot", self.transaction_slot),
            ("transaction_index", self.transaction_index),
            ("current_snapshot_slot", self.current_snapshot_slot),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} deve ser inteiro não negativo")
        if self.current_snapshot_slot < self.transaction_slot:
            raise ValueError("snapshot atual antecede a transação")
        if self.owner != TOKEN_2022_PROGRAM_ID:
            raise ValueError("mint não pertence ao Token-2022")
        if self.transaction_successful is not True:
            raise ValueError("execução da transação não foi comprovada")
        if self.mint_transfer_observed is not True:
            raise ValueError("transação não comprova uso do mint em transferência")
        if self.transfer_fee_config_present is not False:
            raise ValueError("mint possui TransferFeeConfig; prova de ausência inválida")
        if self.source_commit != TOKEN_2022_SOURCE_COMMIT:
            raise ValueError("source commit do protocolo não corresponde ao código fixado")

    @property
    def fee_amount_raw(self) -> int:
        return 0

    @property
    def basis(self) -> str:
        return (
            "TransferFeeConfig ausente em snapshot finalized posterior; "
            "Token-2022 exige inicializar essa extensão antes de InitializeMint "
            "e não permite adicioná-la após a inicialização"
        )


def build_no_transfer_fee_proof(
    *,
    mint: str,
    signature: str,
    transaction_slot: int,
    transaction_index: int,
    current_snapshot_slot: int,
    owner: str,
    mint_data: bytes,
    transaction_successful: bool,
    mint_transfer_observed: bool,
) -> Token2022NoTransferFeeProof:
    present = transfer_fee_config_present(mint_data)
    if present:
        raise ValueError("TransferFeeConfig está presente; ausência não pode ser provada")
    return Token2022NoTransferFeeProof(
        mint=mint,
        signature=signature,
        transaction_slot=transaction_slot,
        transaction_index=transaction_index,
        current_snapshot_slot=current_snapshot_slot,
        owner=owner,
        transaction_successful=transaction_successful,
        mint_transfer_observed=mint_transfer_observed,
        transfer_fee_config_present=False,
    )
