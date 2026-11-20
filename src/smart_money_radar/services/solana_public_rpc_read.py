"""Read-only public Solana RPC sampling with explicit opt-in, bounded requests.

No private keys. No fixture masquerades as observed; the response carries
its actual retrieval time and original HTTP bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from smart_money_radar.data_sources.rpc_fixture_collector import _is_solana_signature
from smart_money_radar.services.solana_rpc_verification import (
    RpcTransactionEvidence, verify_transaction_rpc_response,
)


@dataclass(frozen=True)
class PublicRpcReadResult:
    status: str
    evidence: RpcTransactionEvidence | None
    reasons: tuple[str, ...]
    requests_sent: int


def fetch_public_finalized_transaction(
    *, endpoint: str, signature: str, enabled: bool = False,
    source_id: str = "solana-public-rpc",
    timeout_seconds: float = 8.0,
    opener=None,
) -> PublicRpcReadResult:
    """Explicitly authorized ONE read query. Never POST a transaction."""
    if not enabled:
        return PublicRpcReadResult("BLOCKED",None,("network_opt_in_required",),0)
    if not _is_solana_signature(signature):
        raise ValueError("assinatura Solana inválida")
    parsed=urlparse(endpoint)
    if (parsed.scheme!="https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment):
        raise ValueError("endpoint HTTPS inválido")
    if type(timeout_seconds) not in (int,float) or not 0<timeout_seconds<=20:
        raise ValueError("timeout inválido")
    if not isinstance(source_id,str) or not source_id.strip():
        raise ValueError("source_id inválido")
    params={"jsonrpc":"2.0","id":1,"method":"getTransaction",
            "params":[signature,{"commitment":"finalized","encoding":"json",
                                 "maxSupportedTransactionVersion":0}]}
    req=Request(endpoint,data=json.dumps(params,separators=(",",":")).encode(),
                headers={"Content-Type":"application/json"},method="POST")
    send=opener or urlopen
    try:
        observed=datetime.now(timezone.utc)
        with send(req,timeout=timeout_seconds) as response:
            raw=response.read(2_000_001)
        available=datetime.now(timezone.utc)
    except (HTTPError,URLError,TimeoutError,OSError) as exc:
        return PublicRpcReadResult(
            "UNKNOWN",None,("rpc_unavailable",type(exc).__name__),1)
    if len(raw)>2_000_000:
        return PublicRpcReadResult("UNKNOWN",None,("rpc_payload_too_large",),1)
    try:
        ev=verify_transaction_rpc_response(
            raw_payload=raw,signature=signature,source_id=source_id,
            endpoint_host=parsed.hostname,observed_at=observed,
            available_at=available,requested_commitment="finalized",
        )
    except ValueError:
        return PublicRpcReadResult("UNKNOWN",None,("rpc_response_invalid",),1)
    return PublicRpcReadResult(ev.status,ev,ev.reasons,1)
