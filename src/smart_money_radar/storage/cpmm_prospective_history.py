"""Append-only SQLite inventory of prospective Raydium CPMM captures.

Raw bytes remain immutable and available in the evidence archive. SQLite
stores exact bytes plus hashes so a database restart never changes the audit
meaning. No live trading or complete-coverage status exists in this module.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

from smart_money_radar.services.prospective_cpmm_history import CpmmCapture,CpmmHistoryDelta

_SCHEMA="""
CREATE TABLE IF NOT EXISTS prospective_cpmm_captures(
  capture_id TEXT PRIMARY KEY,
  pool TEXT NOT NULL,
  slot INTEGER NOT NULL,
  source_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  available_at TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  response_sha256 TEXT NOT NULL,
  request_raw BLOB NOT NULL,
  response_raw BLOB NOT NULL,
  manifest_raw BLOB NOT NULL,
  decoder_version TEXT NOT NULL,
  prior_capture_id TEXT,
  coverage TEXT NOT NULL CHECK (coverage IN ('OBSERVED','PARTIAL','UNKNOWN','CONFLICT')),
  integrity TEXT NOT NULL,
  UNIQUE(pool,slot,source_id,response_sha256)
);
CREATE TABLE IF NOT EXISTS prospective_cpmm_deltas(
  from_capture_id TEXT NOT NULL,
  to_capture_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(from_capture_id,to_capture_id)
);
"""


class SQLiteCpmmProspectiveHistory:
    """No migrations of the existing swap observation/event SQLite database."""

    def __init__(self,path:str|Path):
        self.path=str(path)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(_SCHEMA)

    def close(self):
        self.connection.close()

    def integrity_check(self):
        return [row[0] for row in self.connection.execute("PRAGMA integrity_check")]

    def append_capture(self,capture:CpmmCapture,*,manifest_raw:bytes,
                       prior_capture_id:str|None=None,coverage:str="OBSERVED")->bool:
        if not isinstance(capture,CpmmCapture):
            raise TypeError("captura inválida")
        if coverage not in {"OBSERVED","PARTIAL","UNKNOWN","CONFLICT"}:
            raise ValueError("cobertura inválida")
        if not isinstance(manifest_raw,bytes) or not manifest_raw:
            raise ValueError("manifesto RAW ausente")
        if json.loads(manifest_raw)!=capture.manifest:
            raise ValueError("manifesto RAW diverge da evidência")
        if (sha256(capture.request_raw).hexdigest()!=capture.manifest["request_sha256"]
            or sha256(capture.response_raw).hexdigest()!=capture.manifest["response_sha256"]):
            raise ValueError("RAW da captura adulterado")
        if capture.observation.status!="RPC_DECLARED_PROSPECTIVE_ONLY":
            raise ValueError("captura não validada")
        connection=self.connection
        prior=None
        if prior_capture_id is not None:
            prior=connection.execute(
                "SELECT pool,slot,available_at FROM prospective_cpmm_captures WHERE capture_id=?",
                (prior_capture_id,)).fetchone()
            if prior is None or prior[0]!=capture.observation.pool:
                raise ValueError("captura anterior ausente/de outro pool")
            if (capture.observation.slot<=prior[1]
                or capture.observation.available_at<=datetime.fromisoformat(prior[2])):
                raise ValueError("sequência de snapshots não crescente")
        old=connection.execute(
            "SELECT request_raw,response_raw,manifest_raw,prior_capture_id,coverage "
            "FROM prospective_cpmm_captures WHERE capture_id=?",(capture.capture_id,)).fetchone()
        if old is not None:
            if old!=(capture.request_raw,capture.response_raw,manifest_raw,prior_capture_id,coverage):
                raise ValueError("conflito de captura imutável")
            return False
        with connection:
            connection.execute(
                "INSERT INTO prospective_cpmm_captures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (capture.capture_id,capture.observation.pool,capture.observation.slot,
                 capture.observation.source_id,capture.observation.endpoint,
                 capture.observation.observed_at.isoformat(),
                 capture.observation.available_at.isoformat(),
                 capture.manifest["request_sha256"],capture.manifest["response_sha256"],
                 capture.request_raw,capture.response_raw,manifest_raw,
                 capture.decoder_version,prior_capture_id,coverage,"SHA256_BOUND_UNATTESTED"))
        return True

    def append_delta(self,delta:CpmmHistoryDelta):
        if not isinstance(delta,CpmmHistoryDelta):raise TypeError("delta inválido")
        content=json.dumps(asdict(delta),sort_keys=True,separators=(",",":"))
        with self.connection:
            for id in (delta.first_capture_id,delta.second_capture_id):
                if self.connection.execute(
                    "SELECT 1 FROM prospective_cpmm_captures WHERE capture_id=?",(id,)).fetchone() is None:
                    raise ValueError("referência de captura inexistente")
            found=self.connection.execute(
                "SELECT payload_json FROM prospective_cpmm_deltas WHERE from_capture_id=? AND to_capture_id=?",
                (delta.first_capture_id,delta.second_capture_id)).fetchone()
            if found is not None:
                if found[0]!=content:raise ValueError("comparação imutável divergente")
                return False
            self.connection.execute(
                "INSERT INTO prospective_cpmm_deltas VALUES(?,?,?)",
                (delta.first_capture_id,delta.second_capture_id,content))
        return True

    def get_capture(self,capture_id:str):
        row=self.connection.execute(
            "SELECT capture_id,pool,slot,source_id,observed_at,available_at,request_sha256,"
            "response_sha256,request_raw,response_raw,manifest_raw,prior_capture_id,"
            "coverage,integrity,decoder_version FROM prospective_cpmm_captures WHERE capture_id=?",
            (capture_id,)).fetchone()
        if row is None:return None
        keys=("capture_id","pool","slot","source_id","observed_at","available_at","request_sha256",
              "response_sha256","request_raw","response_raw","manifest_raw",
              "prior_capture_id","coverage","integrity","decoder_version")
        entry=dict(zip(keys,row))
        if (sha256(entry["request_raw"]).hexdigest()!=entry["request_sha256"]
            or sha256(entry["response_raw"]).hexdigest()!=entry["response_sha256"]):
            raise ValueError("SQLite RAW corrompido")
        return entry

    def get_delta(self,from_id:str,to_id:str):
        row=self.connection.execute(
            "SELECT payload_json FROM prospective_cpmm_deltas WHERE from_capture_id=? AND to_capture_id=?",
            (from_id,to_id)).fetchone()
        return json.loads(row[0]) if row else None
