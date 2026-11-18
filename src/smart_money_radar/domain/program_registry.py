"""Registro versionado de programas Solana prioritários para a V1.

A presença neste registro identifica programas conhecidos; não significa que
seus decodificadores estejam implementados ou que toda instrução seja suportada.
"""

from dataclasses import dataclass
from typing import Literal


Priority = Literal[0, 1, 2, 3]
ProgramKind = Literal["core", "launchpad", "amm", "aggregator"]


@dataclass(frozen=True)
class ProgramSpec:
    name: str
    program_id: str
    kind: ProgramKind
    priority: Priority
    scope: str
    venue: bool
    source_url: str


PROGRAMS: tuple[ProgramSpec, ...] = (
    ProgramSpec("System Program", "11111111111111111111111111111111", "core", 0,
                "SOL transfers, account creation and native account operations", False,
                "https://solana.com/docs/core/programs"),
    ProgramSpec("SPL Token", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "core", 0,
                "Token mint/account/transfer instructions and CPI", False,
                "https://solana.com/docs/tokens"),
    ProgramSpec("Token-2022", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "core", 0,
                "Token extensions, transfer fees and transfer hooks", False,
                "https://www.solana-program.com/docs/token-2022"),
    ProgramSpec("Associated Token Account", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "core", 0,
                "ATA creation/derivation; supporting evidence, not a trade venue", False,
                "https://solana.com/docs/tokens"),
    ProgramSpec("Pump.fun Bonding Curve", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "launchpad", 1,
                "Token creation, bonding-curve buy/sell and graduation", True,
                "https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md"),
    ProgramSpec("PumpSwap AMM", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "amm", 1,
                "Post-graduation pool creation and swaps", True,
                "https://github.com/pump-fun/pump-public-docs"),
    ProgramSpec("Raydium CPMM", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "amm", 1,
                "Constant-product pool initialization and swaps", True,
                "https://github.com/raydium-io/raydium-docs-v1/blob/main/reference/program-addresses.mdx"),
    ProgramSpec("Raydium AMM v4", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "amm", 1,
                "Legacy AMM pool swaps and liquidity operations", True,
                "https://github.com/mahfuz67/solana-stream-skill/blob/main/skill/resources.md"),
    ProgramSpec("Raydium LaunchLab", "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "launchpad", 2,
                "Launch pool initialization and migration to AMM/CPMM", True,
                "https://github.com/mahfuz67/solana-stream-skill/blob/main/skill/launchpad-migrations.md"),
    ProgramSpec("Raydium CLMM", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "amm", 2,
                "Concentrated-liquidity pools, swaps and positions", True,
                "https://github.com/raydium-io/raydium-docs-v1/blob/main/reference/program-addresses.mdx"),
    ProgramSpec("Orca Whirlpools", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "amm", 2,
                "Concentrated-liquidity swaps and pool/position operations", True,
                "https://github.com/orca-so/whirlpools"),
    ProgramSpec("Meteora DLMM", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "amm", 2,
                "Bin-based swaps, pool initialization and liquidity changes", True,
                "https://github.com/MeteoraAg/docs/blob/main/developer-guides/dlmm/index.mdx"),
    ProgramSpec("Meteora DBC", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "launchpad", 2,
                "Dynamic bonding-curve pool initialization and migration", True,
                "https://github.com/mahfuz67/solana-stream-skill/blob/main/skill/launchpad-migrations.md"),
    ProgramSpec("Meteora DAMM v2", "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "amm", 2,
                "Dynamic AMM pool swaps and liquidity operations", True,
                "https://github.com/mahfuz67/solana-stream-skill/blob/main/skill/resources.md"),
    ProgramSpec("Jupiter Aggregator v6", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "aggregator", 1,
                "Route orchestration; inspect inner instructions for underlying venues", False,
                "https://github.com/solana-foundation/surfpool/blob/main/crates/core/src/scenarios/protocols/jupiter/v6/idl.json"),
)

PROGRAMS_BY_ID = {item.program_id: item for item in PROGRAMS}


def get_program_spec(program_id: str) -> ProgramSpec | None:
    """Retorna metadados conhecidos sem inferir suporte de decodificação."""
    return PROGRAMS_BY_ID.get(program_id)


def _base58_decoded_length(value: str) -> int:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        if char not in alphabet:
            raise ValueError("Program ID contém caractere fora do alfabeto Base58.")
        number = number * 58 + alphabet.index(char)
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return leading_zeroes + ((number.bit_length() + 7) // 8)


def validate_registry() -> None:
    """Valida unicidade e formato dos endereços registrados."""
    if len(PROGRAMS_BY_ID) != len(PROGRAMS):
        raise ValueError("Há Program IDs duplicados no registro.")
    for item in PROGRAMS:
        if not item.name.strip() or not item.scope.strip() or not item.source_url.startswith("https://"):
            raise ValueError("Metadados incompletos no registro de programas.")
        if _base58_decoded_length(item.program_id) != 32:
            raise ValueError(f"Program ID não representa uma chave pública de 32 bytes: {item.name}")
