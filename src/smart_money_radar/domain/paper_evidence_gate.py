"""Fail-closed point-in-time evidence gate for SMR paper simulations.

Independent of RPC decoding. Does not convert model estimates to observed quotes.
"""
import base64
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from smart_money_radar.domain.paper_replay import ReplayTick


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


def _unique_json_fields(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("campo duplicado no JSON RAW da cotação")
        result[name] = value
    return result


def _quote_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) not in (str, int, Decimal):
        raise ValueError("valor numérico RAW da cotação inválido")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("valor numérico RAW da cotação inválido") from exc
    if not parsed.is_finite():
        raise ValueError("valor numérico RAW da cotação inválido")
    return parsed


def verify_paper_quote_tick(
    tick: ReplayTick, evidence: list[dict], expected_pool: str,
) -> str:
    """Bind an observed quote to its archived bytes and the simulator inputs.

    The digest checks integrity against the supplied archive record. It does
    not authenticate the provider or the capture clock. Those require evidence
    from outside the caller-supplied replay bundle.
    """
    if not isinstance(tick, ReplayTick) or not isinstance(tick.quote_id, str) or not tick.quote_id.strip():
        raise ValueError("tick sem identidade de cotação")
    stamp = tick.at.isoformat()
    records = gate_paper_evidence(
        signal_at=stamp, decision_at=stamp, evidence=evidence,
        expected_pool=expected_pool, require_observed_quote=True,
    )
    if len(records) != 1:
        raise ValueError("evidência RAW da cotação precisa ser única")
    record = records[0]
    encoded = record.get("raw_capture_base64")
    expected_digest = record.get("raw_capture_sha256")
    if (not isinstance(encoded, str) or not encoded
            or not isinstance(expected_digest, str) or len(expected_digest) != 64
            or any(char not in "0123456789abcdef" for char in expected_digest)):
        raise ValueError("captura RAW e SHA-256 da cotação são obrigatórios")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("captura RAW da cotação em Base64 inválida") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise ValueError("SHA-256 divergente da cotação RAW")
    try:
        quote = json.loads(raw.decode("utf-8"), parse_float=Decimal, object_pairs_hook=_unique_json_fields)
    except (ValueError, RecursionError) as exc:
        raise ValueError("JSON RAW da cotação inválido") from exc

    if not isinstance(quote, dict) or quote.get("quote_id") != tick.quote_id or quote.get("pool") != expected_pool:
        raise ValueError("identidade ou pool divergente na cotação RAW")
    observed = _aware(quote.get("observed_at"), "observed_at RAW")
    available = _aware(quote.get("available_at"), "available_at RAW")
    if (observed != (tick.market_at or tick.at) or available != tick.at
            or observed != _aware(record.get("observed_at"), "observed_at")
            or available != _aware(record.get("available_at"), "available_at")):
        raise ValueError("horários divergentes na cotação RAW")
    for field in ("price", "volume", "bid", "ask", "bid_size", "ask_size"):
        if field not in quote or _quote_decimal(quote[field]) != getattr(tick, field):
            raise ValueError(f"campo {field} diverge da cotação RAW")
    return digest
