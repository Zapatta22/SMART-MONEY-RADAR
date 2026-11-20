"""Local, reproducible and secret-free evidence manifest for Solana Live sessions.

This is a measurement *manifest*, not independent proof of RPC provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from smart_money_radar.services.launch_live_monitor import LaunchLiveMetrics


def save_launch_live_report(
    destination: Path,
    *, source_id: str, cluster: str, addresses: tuple[str, ...],
    started_at: datetime, ended_at: datetime,
    metrics: LaunchLiveMetrics, rpc_cursors: dict[str, dict | None],
    sqlite_integrity: list[str],
) -> dict[str, Any]:
    """Safely persist a manifest without endpoint URL, API key or raw credentials.

    Percentiles describe locally measured intervals, not Solana propagation
    latency. A provider-reported finalized status is not cryptographic proof.
    """
    if not isinstance(destination, Path) or destination.suffix.lower() != ".json":
        raise ValueError("relatório precisa ser um caminho .json")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id é obrigatório")
    if not isinstance(sqlite_integrity, list) or sqlite_integrity != ["ok"]:
        raise RuntimeError("integridade SQLite não comprovada; relatório não produzido")
    metrics_dict = asdict(metrics)
    data = {
        "schema": "smr.solana_live_observation.v1",
        "network": "solana",
        "cluster": cluster,
        "provider": "operator_configured_rpc",
        "provenance": "RPC_PROVIDER_ASSERTED_NOT_INDEPENDENTLY_ATTESTED",
        "time_source": "local_utc_not_attested",
        "coverage": "UNKNOWN",
        "network_execution": "operator_opt_in",
        "source_id_sha256": hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
        "monitored_public_addresses": list(addresses),
        "started_at_utc": started_at.isoformat(),
        "ended_at_utc": ended_at.isoformat(),
        "metrics": metrics_dict,
        "finalized_rpc_cursors": rpc_cursors,
        "sqlite_integrity": "ok",
        "latency_semantics": {
            "notification_to_finalized_ms":
                "local elapsed time from confirmed WebSocket receipt until matching "
                "signature was archived through finalized RPC",
            "rpc_collection_ms":
                "monotonic elapsed time collecting signatures and transactions",
            "persistence_ms":
                "monotonic elapsed time committing SQLite batch",
            "reconnect_ms":
                "monotonic local elapsed time between disconnect and re-subscription ACK",
            "percentiles":
                "nearest-rank over at least 20 local samples; null if insufficient",
            "not_measured":
                "Solana validator emission-to-network-receive latency",
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=destination.parent, prefix=".smr-live-", suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return data
