"""Strictly offline preflight for a bounded Solana Live validation session.

The result is informational and never makes network calls or reads secret values.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from smart_money_radar.settings import HeliusSettings, SettingsError


@dataclass(frozen=True)
class LaunchLivePreflight:
    ready: bool
    network_authorized: bool
    credentials_configured: bool
    cluster: str
    address_count: int
    duration_seconds: int
    max_rpc_pages_per_reconciliation: int
    limits_known: bool
    reasons: tuple[str, ...]


def evaluate_launch_live_preflight(
    *, environ: Mapping[str, str], addresses: tuple[str, ...],
    duration_seconds: int, page_size: int, max_pages: int,
    source_id: str,
) -> LaunchLivePreflight:
    """Validate only metadata; API key never appears in returned structure."""
    authorized = environ.get("SMR_ALLOW_NETWORK", "").strip().lower() in (
        "true", "1", "yes"
    )
    value = environ.get("HELIUS_API_KEY", "")
    configured = bool(value.strip()) and value.strip() != "replace_with_your_helius_api_key"
    cluster = environ.get("SOLANA_CLUSTER", "mainnet").strip().lower()
    reasons = []
    if not authorized:
        reasons.append("network_not_authorized")
    if not configured:
        reasons.append("helius_credential_missing")
    if cluster not in ("mainnet", "devnet"):
        reasons.append("invalid_cluster")
    if not isinstance(addresses, tuple) or not addresses or len(addresses) > 4:
        reasons.append("address_limit_exceeded")
    elif any(not isinstance(a, str) or not a.strip() for a in addresses):
        reasons.append("invalid_public_address")
    elif len(set(addresses)) != len(addresses):
        reasons.append("duplicate_public_address")
    if type(duration_seconds) is not int or not 1 <= duration_seconds <= 900:
        reasons.append("duration_out_of_bounds")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        reasons.append("page_size_out_of_bounds")
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        reasons.append("max_pages_out_of_bounds")
    if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 160:
        reasons.append("invalid_source_identity")
    budget = page_size * max_pages if type(page_size) is int and type(max_pages) is int else 0
    return LaunchLivePreflight(
        ready=not reasons,
        network_authorized=authorized,
        credentials_configured=configured,
        cluster=cluster,
        address_count=len(addresses) if isinstance(addresses, tuple) else 0,
        duration_seconds=duration_seconds,
        max_rpc_pages_per_reconciliation=max(0, budget),
        limits_known=False,  # Actual RPC quota must be confirmed by the operator.
        reasons=tuple(reasons),
    )
