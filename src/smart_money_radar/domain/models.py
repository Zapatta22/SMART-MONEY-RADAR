"""Tipos de domínio para endereços públicos e eventos observados."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class Wallet:
    """Identifica uma carteira por seu endereço público, sem guardar credenciais."""

    address: str
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.address.strip():
            raise ValueError("O endereço público da carteira não pode estar vazio.")


@dataclass(frozen=True)
class ActivityEvent:
    """Representa um evento de atividade já obtido por uma fonte de dados."""

    wallet_address: str
    signature: str
    occurred_at: datetime | None
    token_mint: str
    direction: Literal["in", "out"]
    amount: Decimal

    def __post_init__(self) -> None:
        if not self.wallet_address.strip():
            raise ValueError("O endereço público da carteira não pode estar vazio.")
        if not self.signature.strip():
            raise ValueError("A assinatura do evento não pode estar vazia.")
        if not self.token_mint.strip():
            raise ValueError("O mint do token não pode estar vazio.")
        if self.direction not in {"in", "out"}:
            raise ValueError("A direção deve ser 'in' ou 'out'.")
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("O valor do evento não pode ser negativo.")

@dataclass(frozen=True)
class ObservedTransaction:
    """Envelope normalizado de uma transação observada na blockchain."""

    chain: str
    wallet_address: str
    signature: str
    observed_at: datetime
    raw_transaction: dict | None
    parser_version: str
    parse_status: Literal["parsed", "no_events", "parse_error", "failed_on_chain"]
    slot: int | None = None
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.chain.strip() or not self.wallet_address.strip() or not self.signature.strip():
            raise ValueError("Chain, carteira e assinatura são obrigatórias.")
        if not self.parser_version.strip():
            raise ValueError("A versão do parser é obrigatória.")
        if self.parse_status not in {"parsed", "no_events", "parse_error", "failed_on_chain"}:
            raise ValueError("Estado de parsing inválido.")
        if self.slot is not None and (isinstance(self.slot, bool) or self.slot < 0):
            raise ValueError("Slot deve ser inteiro não negativo.")
        if self.parse_status == "failed_on_chain" and self.raw_transaction is not None:
            # O payload pode existir para uma transação falha; não há restrição.
            pass


@dataclass(frozen=True)
class TokenBalanceDelta:
    """Variação observada de saldo de um mint para uma carteira."""

    chain: str
    wallet_address: str
    signature: str
    token_mint: str
    direction: Literal["in", "out"]
    amount: Decimal
    decimals: int | None = None

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.chain, self.wallet_address, self.signature, self.token_mint)):
            raise ValueError("Chain, carteira, assinatura e mint são obrigatórios.")
        if self.direction not in {"in", "out"}:
            raise ValueError("Direção inválida.")
        if not self.amount.is_finite() or self.amount <= 0:
            raise ValueError("Delta de saldo deve ser finito e positivo.")
        if self.decimals is not None and (
            isinstance(self.decimals, bool) or not isinstance(self.decimals, int) or not 0 <= self.decimals <= 255
        ):
            raise ValueError("Decimais devem ser um inteiro entre 0 e 255.")


@dataclass(frozen=True)
class SwapObservation:
    """Hipótese de swap derivada de evidências; não representa certeza semântica."""

    chain: str
    wallet_address: str
    signature: str
    input_mint: str
    output_mint: str
    input_amount: Decimal
    output_amount: Decimal
    confidence: Decimal
    evidence: tuple[str, ...]
    observed_at: datetime
    parser_version: str

    def __post_init__(self) -> None:
        required = (self.chain, self.wallet_address, self.signature, self.input_mint,
                    self.output_mint, self.parser_version)
        if not all(value.strip() for value in required):
            raise ValueError("Campos de identificação do swap são obrigatórios.")
        if self.input_mint == self.output_mint:
            raise ValueError("Mint de entrada e saída devem ser diferentes.")
        if not self.input_amount.is_finite() or self.input_amount <= 0:
            raise ValueError("Quantidade de entrada inválida.")
        if not self.output_amount.is_finite() or self.output_amount <= 0:
            raise ValueError("Quantidade de saída inválida.")
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("Confiança deve estar entre 0 e 1.")
        if not self.evidence or any(not item.strip() for item in self.evidence):
            raise ValueError("A hipótese de swap precisa de evidências explícitas.")


@dataclass(frozen=True)
class PoolSnapshot:
    """Snapshot observado de reservas; não presume preço USD ou liquidez total."""

    chain: str
    pool_address: str
    token_a_mint: str
    token_b_mint: str
    reserve_a: Decimal
    reserve_b: Decimal
    observed_at: datetime
    slot: int | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.chain, self.pool_address, self.token_a_mint, self.token_b_mint)):
            raise ValueError("Identificação do pool e dos tokens é obrigatória.")
        if self.token_a_mint == self.token_b_mint:
            raise ValueError("Os dois ativos do pool devem ser diferentes.")
        if any(not value.is_finite() or value < 0 for value in (self.reserve_a, self.reserve_b)):
            raise ValueError("Reservas devem ser finitas e não negativas.")
        if self.slot is not None and (isinstance(self.slot, bool) or not isinstance(self.slot, int) or self.slot < 0):
            raise ValueError("Slot deve ser inteiro não negativo.")


@dataclass(frozen=True)
class WalletProfile:
    """Resumo analítico versionado de uma carteira pública."""

    chain: str
    wallet_address: str
    first_seen_at: datetime
    last_seen_at: datetime
    transactions_observed: int = 0
    swaps_observed: int = 0
    realized_pnl: Decimal | None = None
    win_rate: Decimal | None = None
    profile_version: str = "1"

    def __post_init__(self) -> None:
        if not self.chain.strip() or not self.wallet_address.strip() or not self.profile_version.strip():
            raise ValueError("Chain, carteira e versão do perfil são obrigatórias.")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("Última observação não pode anteceder a primeira.")
        for count in (self.transactions_observed, self.swaps_observed):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Contagens devem ser inteiros não negativos.")
        if self.swaps_observed > self.transactions_observed:
            raise ValueError("Swaps observados não podem exceder transações observadas.")
        if self.win_rate is not None and (
            not self.win_rate.is_finite() or not Decimal("0") <= self.win_rate <= Decimal("1")
        ):
            raise ValueError("Win rate deve estar entre 0 e 1.")
        if self.realized_pnl is not None and not self.realized_pnl.is_finite():
            raise ValueError("PnL realizado deve ser finito.")
