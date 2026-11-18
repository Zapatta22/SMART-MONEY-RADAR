"""Serviço de consulta de atividade através de uma fonte injetada."""

from smart_money_radar.data_sources.base import WalletDataSource
from smart_money_radar.domain.models import ActivityEvent, Wallet


class WalletTracker:
    """Coordena consultas de atividade sem conhecer detalhes da fonte."""

    def __init__(self, data_source: WalletDataSource) -> None:
        self._data_source = data_source

    def get_activity(self, wallet: Wallet) -> list[ActivityEvent]:
        """Obtém eventos para o endereço público informado."""
        return self._data_source.get_activity(wallet.address)