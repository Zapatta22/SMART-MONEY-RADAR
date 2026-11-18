"""Decodificação estrutural das instruções de swap do Raydium CPMM.

Os valores decodificados são argumentos/limites da instrução, não quantidades
efetivamente executadas. A reconstrução econômica deve usar evidências on-chain.
"""
from dataclasses import dataclass
from typing import TypeAlias


RAYDIUM_CPMM_PROGRAM_ID = (
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
)

SWAP_BASE_INPUT_DISCRIMINATOR = bytes.fromhex("8fbe5adac41e33de")
SWAP_BASE_OUTPUT_DISCRIMINATOR = bytes.fromhex("37d96256a34ab4ad")
SWAP_INSTRUCTION_DATA_LENGTH = 24


@dataclass(frozen=True)
class RaydiumCpmmSwapBaseInput:
    """Exact-input: amount_in e limite mínimo, não output efetivo."""

    amount_in: int
    minimum_amount_out: int


@dataclass(frozen=True)
class RaydiumCpmmSwapBaseOutput:
    """Exact-output: output solicitado e limite máximo, não input efetivo."""

    max_amount_in: int
    amount_out: int


RaydiumCpmmSwapInstruction: TypeAlias = (
    RaydiumCpmmSwapBaseInput | RaydiumCpmmSwapBaseOutput
)


def decode_raydium_cpmm_instruction(
    program_id: str,
    data: bytes,
) -> RaydiumCpmmSwapInstruction | None:
    """Decodifica SwapBaseInput ou SwapBaseOutput; ignora outros programas/IXs."""

    if program_id != RAYDIUM_CPMM_PROGRAM_ID:
        return None

    if not isinstance(data, bytes):
        raise TypeError("instruction data deve ser bytes")

    if not data:
        raise ValueError("instruction data vazio")

    discriminator = data[:8]
    if discriminator not in (
        SWAP_BASE_INPUT_DISCRIMINATOR,
        SWAP_BASE_OUTPUT_DISCRIMINATOR,
    ):
        return None

    if len(data) != SWAP_INSTRUCTION_DATA_LENGTH:
        raise ValueError(
            f"instrução CPMM de swap exige {SWAP_INSTRUCTION_DATA_LENGTH} bytes; "
            f"recebidos {len(data)}"
        )

    first_value = int.from_bytes(data[8:16], "little")
    second_value = int.from_bytes(data[16:24], "little")

    if discriminator == SWAP_BASE_INPUT_DISCRIMINATOR:
        return RaydiumCpmmSwapBaseInput(
            amount_in=first_value,
            minimum_amount_out=second_value,
        )

    return RaydiumCpmmSwapBaseOutput(
        max_amount_in=first_value,
        amount_out=second_value,
    )
