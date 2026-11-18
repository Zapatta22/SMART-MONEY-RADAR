"""Compatibilidade com o nome original da fonte de dados Solana."""

from smart_money_radar.data_sources.helius import HeliusDataSource
from smart_money_radar.domain.models import ActivityEvent
from smart_money_radar.settings import HeliusSettings


class SolanaDataSource:
    """Compatibilidade para código que usava o adaptador Solana inicial.

    Sem configuração, mantém o comportamento seguro anterior de falhar quando
    a coleta é solicitada. Com HeliusSettings, encaminha para o adaptador real.
    """

    def __init__(self, settings: HeliusSettings | None = None) -> None:
        self._helius = HeliusDataSource(settings) if settings is not None else None

    def get_activity(self, wallet_address: str) -> list[ActivityEvent]:
        if self._helius is None:
            raise NotImplementedError(
                "Configure HeliusSettings para habilitar consultas somente leitura."
            )
        return self._helius.get_activity(wallet_address)