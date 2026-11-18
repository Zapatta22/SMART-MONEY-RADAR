"""Métricas descritivas simples, sem pontuação de investimento."""

from collections import Counter
from collections.abc import Iterable

from smart_money_radar.domain.models import ActivityEvent


def count_events_by_token(events: Iterable[ActivityEvent]) -> dict[str, int]:
    """Conta eventos por mint de token, sem combinar valores entre tokens."""
    counts = Counter(event.token_mint for event in events)
    return dict(sorted(counts.items()))