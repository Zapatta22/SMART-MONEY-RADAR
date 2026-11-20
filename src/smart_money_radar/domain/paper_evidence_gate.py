"""Fail-closed point-in-time evidence gate for SMR paper simulations.

Independent of RPC decoding. Does not convert model estimates to observed quotes.
"""
from datetime import datetime


def _aware(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} inválido")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} inválido") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{label} sem fuso")
    return parsed


def gate_paper_evidence(*, signal_at: str, decision_at: str,
                        evidence: list[dict], expected_pool: str,
                        require_observed_quote: bool = False):
    """Return eligible evidence only if every item existed by decision time.

    Availability is the time the data was accessible to the strategy, NOT
    the historical block time. This is deliberately all-or-nothing.
    """
    signal = _aware(signal_at, "signal_at")
    decision = _aware(decision_at, "decision_at")
    if decision < signal:
        raise ValueError("decisão anterior ao sinal")
    if not isinstance(expected_pool, str) or not expected_pool.strip():
        raise ValueError("pool obrigatório")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("evidências obrigatórias")
    ids = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("evidência inválida")
        identifier = item.get("evidence_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("identidade de evidência ausente ou duplicada")
        ids.add(identifier)
        if item.get("pool") != expected_pool:
            raise ValueError("pool divergente")
        observed = _aware(item.get("observed_at"), "observed_at")
        available = _aware(item.get("available_at"), "available_at")
        if observed > available or available > decision:
            raise ValueError("evidência futura ou indisponível no instante da decisão")
        source = item.get("source")
        if source not in ("OBSERVED_MARKET_QUOTE", "MODEL_ESTIMATE_NOT_OBSERVED"):
            raise ValueError("origem da evidência desconhecida")
        if require_observed_quote and source != "OBSERVED_MARKET_QUOTE":
            raise ValueError("estimativa não é cotação observada")
        if source == "MODEL_ESTIMATE_NOT_OBSERVED" and item.get("is_observed_quote") is not False:
            raise ValueError("estimativa rotulada incorretamente")
        if source == "OBSERVED_MARKET_QUOTE" and item.get("is_observed_quote") is not True:
            raise ValueError("cotação observada sem marcação")
    return tuple(evidence)
