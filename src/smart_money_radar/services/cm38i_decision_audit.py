"""CM38I: immutable offline opportunity -> risk -> BLOCKED virtual-entry receipts.

All evidence and financial policy are reread from the same SQLite snapshot.
No caller may authorize a prospective entry. No paper ledger mutation, RPC
request, private key, financial transaction, or bypass of CM38/CM39 gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import sqlite3

from smart_money_radar.services.rpc_observation_journal import RpcObservationJournal
from smart_money_radar.services.synthetic_capital import _load, _snapshot
from smart_money_radar.storage.collector_authority import collector_write
from smart_money_radar.storage.event_store import SQLiteEventStore

MODES = ("immediate", "confirmed")
RADARS = ("launch", "smart_money")
VERSION = "CM38I-OFFLINE-1"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode()).hexdigest()


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware decision time required")
    utc = value.astimezone(timezone.utc)
    if utc > datetime.now(timezone.utc):
        raise ValueError("future decision forbidden")
    return utc


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
        raise ValueError("bounded ASCII identifier required")
    if not all(c.isalnum() or c in "._:-" for c in value):
        raise ValueError("unsafe identifier")
    return value


def _money(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError("positive finite Decimal required")
    return value


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS cm38i_opportunities(
        opportunity_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL,
        radar TEXT NOT NULL, strategy TEXT NOT NULL, signature TEXT NOT NULL,
        slot INTEGER NOT NULL, source_id TEXT NOT NULL, raw_sha256 TEXT NOT NULL,
        observed_at TEXT NOT NULL, available_at TEXT NOT NULL,
        decision_at TEXT NOT NULL, processing_version TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status='UNKNOWN'),
        FOREIGN KEY(evidence_id) REFERENCES cm38_rpc_observations(evidence_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cm38i_risk_decisions(
        decision_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL UNIQUE,
        request_fingerprint TEXT NOT NULL, account_id TEXT NOT NULL,
        reasons_json TEXT NOT NULL, account_snapshot_sha256 TEXT NOT NULL,
        requested_notional TEXT NOT NULL, status TEXT NOT NULL CHECK(status='BLOCKED'),
        processing_version TEXT NOT NULL,
        FOREIGN KEY(opportunity_id) REFERENCES cm38i_opportunities(opportunity_id),
        FOREIGN KEY(account_id) REFERENCES cm34_capital_accounts(account_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cm38i_virtual_entry_attempts(
        attempt_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL UNIQUE,
        request_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status='BLOCKED'),
        created_at TEXT NOT NULL, virtual_ledger_mutated INTEGER NOT NULL CHECK(virtual_ledger_mutated=0),
        FOREIGN KEY(decision_id) REFERENCES cm38i_risk_decisions(decision_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cm38i_decision_integrity(
        attempt_id TEXT PRIMARY KEY,receipt_sha256 TEXT NOT NULL,
        FOREIGN KEY(attempt_id) REFERENCES cm38i_virtual_entry_attempts(attempt_id))""")
    for table in ("cm38i_opportunities","cm38i_risk_decisions",
                  "cm38i_virtual_entry_attempts","cm38i_decision_integrity"):
        for kind in ("UPDATE","DELETE"):
            conn.execute("CREATE TRIGGER IF NOT EXISTS cm38i_immut_"+table+"_"+kind.lower()+
                         " BEFORE "+kind+" ON "+table+
                         " BEGIN SELECT RAISE(ABORT,'CM38I audit is immutable'); END")


def _integrity(conn, attempt_id):
    """Verify persisted opportunity/risk/attempt content; never trust caller or mutated rows."""
    tables=(
        ("cm38i_virtual_entry_attempts","attempt_id",attempt_id),
        ("cm38i_risk_decisions","decision_id",None),
        ("cm38i_opportunities","opportunity_id",None),
    )
    att=conn.execute("SELECT * FROM cm38i_virtual_entry_attempts WHERE attempt_id=?",
                     (attempt_id,)).fetchone()
    if att is None: raise ValueError("orphan virtual attempt")
    dec=conn.execute("SELECT * FROM cm38i_risk_decisions WHERE decision_id=?",(att[1],)).fetchone()
    if dec is None: raise ValueError("orphan risk decision")
    opp=conn.execute("SELECT * FROM cm38i_opportunities WHERE opportunity_id=?",(dec[1],)).fetchone()
    if opp is None: raise ValueError("orphan opportunity")
    try:
        prior=conn.execute(
            "SELECT receipt_sha256 FROM cm38i_decision_integrity WHERE attempt_id=?",
            (attempt_id,)).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("missing immutable decision integrity receipt") from exc
    actual=_hash(["CM38I-DECISION-INTEGRITY-1",list(opp),list(dec),list(att)])
    if prior is None or prior[0]!=actual:
        raise ValueError("retroactive risk decision integrity conflict")
    causal = [reason.removeprefix("causal_economic_sha256:") for reason in json.loads(dec[4])
              if reason.startswith("causal_economic_sha256:")]
    if causal:
        row = conn.execute("SELECT payload,digest FROM cm38i_causal_economics WHERE attempt_id=?",
                           (attempt_id,)).fetchone()
        if row is None or causal != [row[1]] or _hash(json.loads(row[0])) != row[1]:
            raise ValueError("causal economic integrity conflict")
    return opp,dec,att



def record_blocked_virtual_entry(store: SQLiteEventStore, *, request_id: str,
                                 account_id: str, radar: str, strategy: str,
                                 evidence_id: str, decision_at: datetime,
                                 requested_notional: Decimal,
                                 max_age_seconds: int = 300, economic_scope: tuple[str,str,str] | None = None):
    """Persist a fail-closed attempt using the existing capital/RPC journals.

    Idempotency applies only to identical request content. A new request for an
    old opportunity is rejected, not treated as a transferable authorization.
    """
    if not isinstance(store, SQLiteEventStore) or store.read_only:
        raise PermissionError("writable existing evaluation store required")
    _name(request_id)
    _name(account_id)
    if radar not in RADARS or strategy not in MODES:
        raise ValueError("radar and strategy required")
    if not isinstance(evidence_id, str) or len(evidence_id) != 64:
        raise ValueError("original RPC evidence ID required")
    at = _utc(decision_at)
    amount = _money(requested_notional)
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
        raise ValueError("bounded evidence TTL required")
    params = [request_id, account_id, radar, strategy, evidence_id,
              at.isoformat(), str(amount), max_age_seconds, VERSION]
    if economic_scope is not None:
        if radar != "smart_money" or not isinstance(economic_scope, tuple) or len(economic_scope)!=3:
            raise ValueError("invalid causal economic scope")
        for item in economic_scope:
            _name(item)
        params.append(list(economic_scope))
    fingerprint = _hash(params)
    with store._connection_scope() as conn, collector_write(
        conn, getattr(store, "_collector_authority", None), radar
    ):
        # Capture integrity must be confirmed before checking existing receipts.
        row = conn.execute(
            "SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",
            (evidence_id,)
        ).fetchone()
        if row is None:
            raise ValueError("original RPC evidence missing")
        meta = RpcObservationJournal._read(evidence_id, row)["metadata"]
        if meta["radar"] != radar:
            raise ValueError("original RPC belongs to another radar")
        observed = _utc(datetime.fromisoformat(meta["observed_at"]))
        available = _utc(datetime.fromisoformat(meta["available_at"]))
        if observed > available or available > at:
            raise ValueError("future or inconsistent source availability")
        if type(meta["slot"]) is not int or meta["slot"] < 0:
            raise ValueError("source slot unresolved")
        existing_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cm38i_virtual_entry_attempts'"
        ).fetchone()
        if existing_table:
            old = conn.execute(
                """SELECT d.request_fingerprint,a.attempt_id,d.decision_id,d.opportunity_id,
                          d.reasons_json
                   FROM cm38i_virtual_entry_attempts a
                   JOIN cm38i_risk_decisions d ON d.decision_id=a.decision_id
                   WHERE a.request_id=?""", (request_id,)
            ).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise ValueError("idempotency request conflicts with prior decision")
                _integrity(conn,old[1])
                return {"opportunity_id": old[3], "decision_id": old[2],
                        "attempt_id": old[1], "request_id": request_id,
                        "status": "BLOCKED", "reasons": tuple(json.loads(old[4])),
                        "virtual_ledger_mutated": False, "prospective_authorized": False,
                        "real_execution_authorized": False, "idempotent_replay": True}

        economic = None
        if economic_scope is not None:
            from smart_money_radar.services.cm38k_persisted_fifo import reconstruct_persisted_wallet, fifo_metric_receipts
            from smart_money_radar.services.cm38j_metric_provenance import qualify_metric_set
            wallet, token, quote = economic_scope
            fifo = reconstruct_persisted_wallet(store,wallet=wallet,token=token,quote_mint=quote,
                                                as_of=at,_connection=conn)
            if evidence_id not in {line["evidence_id"] for line in fifo["lineage"]}:
                raise ValueError("causal decision evidence absent from FIFO")
            metrics = fifo_metric_receipts(fifo)
            economic = {"schema":"CM38I-CAUSAL-ECONOMICS-1","radar":radar,"strategy":strategy,
                        "decision_at":at.isoformat(),"fifo":fifo,"metrics":metrics,
                        "qualification":qualify_metric_set(radar=radar,metrics=metrics),
                        "disposition":"REJECTED_UNVERIFIED_ECONOMICS"}
        account = _snapshot(_load(conn, account_id))
        if radar not in account["allowed_radars"]:
            raise ValueError("synthetic account radar scope mismatch")
        reasons = {"independent_market_attestation_missing",
                   "economic_qualification_unverified",
                   "prospective_human_gate_pending"}
        if meta["status"] != "VERIFIED":
            reasons.add("source_not_independently_verified")
        if meta["commitment_requested"] != "finalized":
            reasons.add("finalization_unverified")
        if (at - available).total_seconds() > max_age_seconds:
            reasons.add("opportunity_expired")
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cm38_economic_evidence_links'"
        ).fetchone() or not conn.execute(
            "SELECT 1 FROM cm38_economic_evidence_links WHERE radar=? AND signature=? AND evidence_id=?",
            (radar, meta["signature"], evidence_id)
        ).fetchone():
            reasons.add("economic_operation_link_missing")
        # Different locally declared sources are *not* independent attestations.
        receipts = conn.execute(
            "SELECT evidence_id,metadata,metadata_sha,raw FROM cm38_rpc_observations "
            "WHERE radar=? AND signature=? ORDER BY evidence_id LIMIT 1001",
            (radar, meta["signature"])
        ).fetchall()
        if len(receipts) > 1000:
            raise ValueError("unbounded conflicting evidence set")
        for eid, data, digest, raw in receipts:
            other = RpcObservationJournal._read(eid, (data,digest,raw))["metadata"]
            if other["slot"] != meta["slot"]:
                reasons.add("divergent_rpc_slot")
            if other["available_at"] > at.isoformat():
                continue
        reasons.add("historical_coverage_unknown")
        equity = Decimal(account["equity"])
        initial = Decimal(account["initial_capital"])
        available_cash = Decimal(account["capital_available"])
        reserved = Decimal(account["capital_reserved"])
        limits = account["risk_limits"]
        if amount > available_cash:
            reasons.add("insufficient_virtual_capital")
        if amount + reserved > equity * Decimal(limits["total_exposure"]):
            reasons.add("total_exposure_limit")
        if amount > equity * Decimal(limits["per_radar"]):
            reasons.add("per_radar_limit")
        if amount > equity * Decimal(limits["per_strategy"]):
            reasons.add("per_strategy_limit")
        if amount > equity * Decimal(limits["per_token"]):
            reasons.add("per_token_limit")
        if amount > equity * Decimal(limits["per_pool"]):
            reasons.add("per_pool_limit")
        if Decimal(account["drawdown"]) >= initial * Decimal(limits["max_drawdown"]):
            reasons.add("maximum_drawdown_limit")
        if -Decimal(account["daily_realized_pnl"]) >= initial * Decimal(limits["max_daily_loss"]):
            reasons.add("daily_loss_limit")
        budgets = account.get("strategy_budgets")
        if budgets is None:
            reasons.add("strategy_budget_not_configured")
        elif amount > Decimal(budgets[radar][strategy]):
            reasons.add("strategy_budget_exceeded")
        if account.get("future_run_config") is None:
            reasons.add("paper_run_config_missing")
        if account.get("future_entry_risk") is None:
            reasons.add("paper_entry_risk_missing")
        op_id = _hash(["CM38I_OP", radar, strategy, meta["signature"], evidence_id])
        decision_id = _hash(["CM38I_DEC", op_id, request_id])
        attempt_id = _hash(["CM38I_ATT", decision_id, request_id])
        _schema(conn)
        # A second request_id for the same opportunity cannot create a new
        # authorization or overwrite a prior decision.
        if conn.execute(
            "SELECT 1 FROM cm38i_opportunities WHERE opportunity_id=?", (op_id,)
        ).fetchone():
            raise ValueError("duplicate opportunity: distinct request denied")
        if economic is not None:
            reasons.add("causal_economic_sha256:"+_hash(economic))
            reasons.add("causal_economics_not_computable")
        reason_json = _json(sorted(reasons))
        conn.execute(
            "INSERT INTO cm38i_opportunities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (op_id,evidence_id,radar,strategy,meta["signature"],meta["slot"],
             meta["source_id"],meta["raw_sha256"],observed.isoformat(),
             available.isoformat(),at.isoformat(),VERSION,"UNKNOWN")
        )
        conn.execute(
            "INSERT INTO cm38i_risk_decisions VALUES (?,?,?,?,?,?,?,?,?)",
            (decision_id,op_id,fingerprint,account_id,reason_json,_hash(account),
             str(amount),"BLOCKED",VERSION)
        )
        conn.execute(
            "INSERT INTO cm38i_virtual_entry_attempts VALUES (?,?,?,?,?,?)",
            (attempt_id,decision_id,request_id,"BLOCKED",
             datetime.now(timezone.utc).isoformat(),0)
        )
        attempt_row=conn.execute("SELECT * FROM cm38i_virtual_entry_attempts WHERE attempt_id=?",
                                 (attempt_id,)).fetchone()
        decision_row=conn.execute("SELECT * FROM cm38i_risk_decisions WHERE decision_id=?",
                                  (decision_id,)).fetchone()
        opportunity_row=conn.execute("SELECT * FROM cm38i_opportunities WHERE opportunity_id=?",
                                     (op_id,)).fetchone()
        receipt_hash=_hash(["CM38I-DECISION-INTEGRITY-1",
                            list(opportunity_row),list(decision_row),list(attempt_row)])
        conn.execute("INSERT INTO cm38i_decision_integrity VALUES (?,?)",
                     (attempt_id,receipt_hash))
        if economic is not None:
            conn.execute("""CREATE TABLE IF NOT EXISTS cm38i_causal_economics(
                attempt_id TEXT PRIMARY KEY REFERENCES cm38i_virtual_entry_attempts(attempt_id),
                payload TEXT NOT NULL,digest TEXT NOT NULL)""")
            for action in ("UPDATE","DELETE"):
                conn.execute("CREATE TRIGGER IF NOT EXISTS cm38i_causal_no_"+action.lower()+
                    " BEFORE "+action+" ON cm38i_causal_economics BEGIN SELECT RAISE(ABORT,'immutable causal economics'); END")
            conn.execute("INSERT INTO cm38i_causal_economics VALUES(?,?,?)",
                         (attempt_id,_json(economic),_hash(economic)))
        _integrity(conn,attempt_id)
    return {"opportunity_id":op_id,"decision_id":decision_id,
            "attempt_id":attempt_id,"request_id":request_id,"status":"BLOCKED",
            "reasons":tuple(sorted(reasons)),"virtual_ledger_mutated":False,
            "prospective_authorized":False,"real_execution_authorized":False,
            "idempotent_replay":False}


def audit_blocked_entry(store: SQLiteEventStore, request_id: str):
    """Read back a blocked entry and revalidate its original RAW before use."""
    _name(request_id)
    with store._connection_scope() as conn, conn:
        conn.execute("BEGIN")
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cm38i_virtual_entry_attempts'"
        ).fetchone():
            return None
        row = conn.execute(
            """SELECT a.attempt_id,a.status,a.virtual_ledger_mutated,d.decision_id,
                      d.opportunity_id,d.reasons_json,o.evidence_id,o.radar,
                      o.signature,o.slot,o.available_at,o.raw_sha256
               FROM cm38i_virtual_entry_attempts a
               JOIN cm38i_risk_decisions d ON a.decision_id=d.decision_id
               JOIN cm38i_opportunities o ON d.opportunity_id=o.opportunity_id
               WHERE a.request_id=?""",(request_id,)
        ).fetchone()
        if row is None: return None
        _integrity(conn,row[0])
        raw = conn.execute(
            "SELECT metadata,metadata_sha,raw FROM cm38_rpc_observations WHERE evidence_id=?",
            (row[6],)
        ).fetchone()
        if raw is None:
            raise ValueError("orphan original RPC evidence")
        meta = RpcObservationJournal._read(row[6],raw)["metadata"]
        if (meta["radar"],meta["signature"],meta["slot"],meta["available_at"],
            meta["raw_sha256"]) != (row[7],row[8],row[9],row[10],row[11]):
            raise ValueError("derived evidence provenance conflict")
        if row[1] != "BLOCKED" or row[2] != 0:
            raise ValueError("forbidden prospective execution state")
        account_scope=conn.execute("SELECT account_id FROM cm38i_risk_decisions WHERE decision_id=?",
                                   (row[3],)).fetchone()
        opportunity_scope=conn.execute("SELECT strategy FROM cm38i_opportunities WHERE opportunity_id=?",
                                       (row[4],)).fetchone()
        if account_scope is None or opportunity_scope is None:
            raise ValueError("orphan decision scope")
        return {"attempt_id":row[0],"decision_id":row[3],
                "opportunity_id":row[4],"evidence_id":row[6],
                "account_id":account_scope[0],"radar":row[7],
                "strategy":opportunity_scope[0],
                "status":"BLOCKED","reasons":tuple(json.loads(row[5])),
                "virtual_ledger_mutated":False,
                "prospective_authorized":False}
