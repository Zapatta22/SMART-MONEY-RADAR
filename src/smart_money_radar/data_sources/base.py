"""Contrato para fontes que fornecem atividade pública de carteiras."""

from typing import Protocol

from smart_money_radar.domain.models import ActivityEvent


class WalletDataSource(Protocol):
    """Interface de leitura que deve ser implementada por uma fonte de dados."""

    def get_activity(self, wallet_address: str) -> list[ActivityEvent]:
        """Retorna eventos existentes para um endereço público."""
        ...