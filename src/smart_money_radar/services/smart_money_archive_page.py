"""Causal pages for the local Smart Money supervisor archive."""

from dataclasses import dataclass
from datetime import datetime, timezone

from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal, _strict_json
from smart_money_radar.services.synthetic_paper_ledger import _encode, _hash


@dataclass(frozen=True)
class SmartMoneyArchivePage:
    rows: list[dict]
    cursor: int
    cursor_anchor: str | None
    coverage: dict


def _time(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("archive timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def _anchor(receipt_id, operation, wallet, available):
    return _hash(_encode((receipt_id, operation, wallet, available)))


def verify_archive_cursor(connection, cursor, anchor):
    if type(cursor) is not int or not 0 <= cursor < 2**63:
        raise ValueError("invalid Smart Money archive cursor")
    if cursor == 0 and anchor is None:
        return
    row = connection.execute(
        """SELECT receipt_id, operation_id, wallet_address, available_at
           FROM swap_replay_archive WHERE receipt_id = ?""",
        (cursor,),
    ).fetchone()
    if row is None or _anchor(*row) != anchor:
        raise ValueError("Smart Money archive cursor anchor conflict")


def _rpc_link_status(connection, row, cutoff, archive_tables, observed_payload):
    if "cm38_economic_evidence_links" not in archive_tables:
        return "missing_rpc_links"
    if "cm38_rpc_observations" not in archive_tables:
        return "conflicted_receipts"
    link = connection.execute(
        """SELECT l.linked_at, l.evidence_id, r.radar, r.signature, r.available_at,
                  r.metadata, r.metadata_sha, r.raw
           FROM cm38_economic_evidence_links l
           LEFT JOIN cm38_rpc_observations r USING(evidence_id)
           WHERE l.radar='smart_money' AND l.wallet_address=? AND l.signature=?
             AND l.entity_type='replay_opportunity' AND l.entity_id=?""",
        (row["wallet"], row["signature"], row["operation_id"]),
    ).fetchone()
    if link is None:
        return "missing_rpc_links"
    linked_at, evidence_id, radar, signature, available_at, *raw = link
    try:
        linked = _time(linked_at)
        if linked > cutoff:
            return "waiting_for_cutoff"
        observation = RpcObservationJournal._read(evidence_id, raw)
        metadata = observation["metadata"]
        if ((radar, signature, available_at) != (
                "smart_money", row["signature"], metadata["available_at"])
                or (metadata["radar"], metadata["signature"], metadata["slot"]) != (
                    "smart_money", row["signature"], row["slot"])
                or metadata["commitment_requested"] != "confirmed"
                or metadata["source_id"] != "helius-wallet-rpc"
                or observation["evidence"].available_at > linked
                or _encode(_strict_json(raw[2])["result"]) != _encode(observed_payload)
                or set(observation["evidence"].reasons) - {
                    "provider_independent_attestation_missing",
                    "finalization_independent_attestation_missing",
                    "finalized_not_requested",
                }):
            raise ValueError("conflicting Smart Money archive RPC link")
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return "conflicted_receipts"
    return "linked_rpc_receipts"


def read_smart_money_archive_page(store, *, cursor, cursor_anchor, cutoff, limit):
    """Scan a bounded causal prefix, including receipts with missing evidence."""
    coverage = {
        "status": "LOCAL_PAGE_DRAINED",
        "scanned_receipts": 0,
        "linked_rpc_receipts": 0,
        "missing_rpc_links": 0,
        "conflicted_receipts": 0,
        "missing_receipt_positions": 0,
        "independent_coverage": "UNKNOWN",
    }
    eligible = []
    with store._connection_scope() as connection, connection:
        connection.execute("BEGIN")
        verify_archive_cursor(connection, cursor, cursor_anchor)
        tables = {name for name, in connection.execute(
            """SELECT name FROM sqlite_master WHERE type='table'
               AND name IN ('cm38_economic_evidence_links', 'cm38_rpc_observations')"""
        )}
        rows = store._smr_archived_event_inputs(connection, limit=limit + 1, after=cursor)
        for row in rows[:limit]:
            try:
                available = _time(row["available_at"])
                if available > cutoff:
                    coverage["status"] = "WAITING_FOR_CUTOFF"
                    break
                if (_time(row["occurred_at"]) > available
                        or (row["observed_at"] is not None and _time(row["observed_at"]) > available)
                        or any(not isinstance(row[key], str) or not row[key].strip()
                               for key in ("operation_id", "wallet", "signature", "pool"))):
                    raise ValueError("invalid Smart Money archive receipt")
                observed = None
                if row["raw_bytes"] is not None:
                    document = _strict_json(row["raw_bytes"])
                    if not isinstance(document, dict):
                        raise ValueError("Smart Money archive observation must be a JSON object")
                    observed = document.get("result", document)
                    if not isinstance(observed, dict):
                        raise ValueError("Smart Money transaction must be a JSON object")
                outcome = _rpc_link_status(connection, row, cutoff, tables, observed)
            except (ValueError, TypeError, RecursionError):
                outcome = "conflicted_receipts"
            if outcome == "waiting_for_cutoff":
                coverage["status"] = "WAITING_FOR_CUTOFF"
                break
            coverage["missing_receipt_positions"] += row["receipt_id"] - cursor - 1
            cursor = row["receipt_id"]
            cursor_anchor = _anchor(cursor, row["operation_id"], row["wallet"], row["available_at"])
            coverage["scanned_receipts"] += 1
            coverage[outcome] += 1
            if outcome != "conflicted_receipts":
                eligible.append(row)
        else:
            if len(rows) > limit:
                coverage["status"] = "LOCAL_BACKLOG"
    return SmartMoneyArchivePage(eligible, cursor, cursor_anchor, coverage)
