"""Read-only Solana accountSubscribe session: bounded, auditable and unsequenced.

JSON-RPC accountNotification provides context.slot, account bytes and a local
subscription ID; it does NOT provide txn_signature, write_version, bank fork,
global ordering or delivery continuity. Never invent Geyser semantics.
The existing SQLiteGeyserRawStore is used only as a RAW frame journal and
never as proof of actual Geyser transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import base64
import json
from pathlib import Path
from typing import Literal

from smart_money_radar.storage.geyser_raw_store import SQLiteGeyserRawStore

ADDRESS_COUNT=4


@dataclass(frozen=True)
class LiveRpcAccountObservation:
    account: str
    slot: int
    subscription_id: int
    raw_sha256: str
    observed_at: str
    content_sha256: str
    status: Literal["OBSERVED","CONFLICT"]
    txn_signature: None=None
    write_version: None=None
    ordered_across_streams: bool=False
    finalized_attested: bool=False
    operational_authorized: bool=False


class PublicCpmmWsSession:
    """A single connection; account notifications are local arrival order only."""

    def __init__(self, store:SQLiteGeyserRawStore, *, source_id:str,session_id:str,
                 accounts:tuple[str,str,str,str], initial_baseline:bool=False):
        if not isinstance(store,SQLiteGeyserRawStore):
            raise TypeError("journal existente obrigatório")
        if len(accounts)!=ADDRESS_COUNT or len(set(accounts))!=ADDRESS_COUNT or any(
            not isinstance(a,str) or not a for a in accounts):
            raise ValueError("exatamente quatro contas distintas")
        if not isinstance(source_id,str) or not source_id or not isinstance(session_id,str) or not session_id:
            raise ValueError("origem e sessão obrigatórias")
        self.store=store
        self.source_id=source_id
        self.session_id=session_id
        self.accounts=accounts
        self.subscription_accounts:dict[int,str]={}
        self.next_local_sequence=0
        self.status="UNKNOWN"
        self.active=False
        self.baseline_validated=bool(initial_baseline) and False
        self.seen:dict[tuple[str,int],str]={}
        self.last_slot:dict[str,int]={}
        self.observations:list[LiveRpcAccountObservation]=[]
        self.gaps:list[str]=["subscription_start_without_verified_baseline"]
        self.reconnects=0

    def start(self):
        if self.active:
            raise ValueError("sessão já iniciada")
        self.store.register_frame_stream(self.source_id,self.session_id,
                                         self.session_id,0)
        self.store.start_capture_session(self.source_id,self.session_id)
        self.active=True

    def finish(self,outcome:str):
        if not self.active:raise ValueError("sessão não iniciada")
        self.active=False
        self.status="UNKNOWN"
        return self.store.finish_capture_session(self.source_id,self.session_id,outcome)

    def _record(self,raw:bytes,kind:str)->str:
        if not self.active:raise ValueError("sessão inativa")
        if not isinstance(raw,bytes) or not raw or len(raw)>1_000_000:
            raise ValueError("frame RAW ausente ou excede limite")
        receipt=self.store.append_wire_frame(
            source_id=self.source_id,stream_id=self.session_id,
            ordering_domain_id=self.session_id,
            stream_sequence=self.next_local_sequence,payload=raw,frame_kind=kind)
        self.next_local_sequence+=1
        if receipt.status not in ("accepted","duplicate"):
            self.gaps.append("journal_frame_"+receipt.status)
            self.status="UNKNOWN"
        return sha256(raw).hexdigest()

    def process_frame(self,raw:bytes,*,received_at:datetime)->LiveRpcAccountObservation|None:
        if not isinstance(received_at,datetime) or received_at.utcoffset() is None:
            raise ValueError("horário UTC com fuso obrigatório")
        digest=self._record(raw,"solana_ws_jsonrpc")
        try:
            frame=json.loads(raw)
            if not isinstance(frame,dict):raise ValueError("not an object")
            if frame.get("method")!="accountNotification":
                raise ValueError("not an accountNotification")
            params=frame["params"]
            subscription=params["subscription"]
            context=params["result"]["context"]
            account=params["result"]["value"]
            slot=context["slot"]
            if type(subscription) is not int or type(slot) is not int or slot<0:
                raise ValueError("slot/subscription invalid")
            pubkey=self.subscription_accounts.get(subscription)
            if not pubkey:
                raise ValueError("subscription unknown")
            if not isinstance(account,dict):
                raise ValueError("account missing")
            encoded=account.get("data")
            if (not isinstance(encoded,list) or len(encoded)!=2 or
                encoded[1]!="base64" or not isinstance(encoded[0],str)):
                raise ValueError("base64 data missing")
            decoded=base64.b64decode(encoded[0],validate=True)
            if len(decoded)>1_000_000:raise ValueError("account data above bound")
            owner=account.get("owner")
            if not isinstance(owner,str) or not owner:
                raise ValueError("owner missing")
            metadata=json.dumps({"account":pubkey,"lamports":account.get("lamports"),
                                 "owner":owner,"executable":account.get("executable"),
                                 "rentEpoch":account.get("rentEpoch")},sort_keys=True,
                                 separators=(",",":"),allow_nan=False).encode()
            content_sha=sha256(metadata+len(decoded).to_bytes(8,"big")+decoded).hexdigest()
            prev=self.last_slot.get(pubkey)
            status="OBSERVED"
            if prev is not None and slot<prev:
                self.gaps.append("regressive_slot:"+pubkey)
                status="CONFLICT"
            if (pubkey,slot) in self.seen and self.seen[(pubkey,slot)]!=content_sha:
                self.gaps.append("same_slot_account_content_conflict:"+pubkey)
                status="CONFLICT"
            if status!="CONFLICT":
                self.seen.setdefault((pubkey,slot),content_sha)
                self.last_slot[pubkey]=slot
            observation=LiveRpcAccountObservation(
                account=pubkey,slot=slot,subscription_id=subscription,
                raw_sha256=digest,observed_at=received_at.astimezone(timezone.utc).isoformat(),
                content_sha256=content_sha,status=status)
            self.observations.append(observation)
            return observation
        except (KeyError,IndexError,TypeError,ValueError,base64.binascii.Error):
            self.gaps.append("malformed_or_unmatched_ws_frame")
            self.status="UNKNOWN"
            return None

    def register_subscription(self,subscription_id:int,account:str):
        if type(subscription_id) is not int or subscription_id<0:
            raise ValueError("subscription inválida")
        if account not in self.accounts:
            raise ValueError("conta fora do escopo")
        if subscription_id in self.subscription_accounts:
            raise ValueError("subscription já vinculada")
        if account in self.subscription_accounts.values():
            raise ValueError("conta inscrita duas vezes")
        self.subscription_accounts[subscription_id]=account

    def mark_disconnect(self):
        self.gaps.append("connection_lost")
        self.status="UNKNOWN"
        self.reconnects+=1
        self.subscription_accounts.clear()

    def report(self)->dict:
        return {"source_id":self.source_id,"session_id":self.session_id,
            "subscriptions_bound":len(self.subscription_accounts),
            "notifications_received":len(self.observations),
            "observations":[o.__dict__ for o in self.observations],
            "gaps":list(self.gaps),"reconnects":self.reconnects,
            "coverage":"UNKNOWN","baseline_validated":False,
            "account_write_order_verified":False,
            "signature_proven":False,"finalized_independently_attested":False,
            "economic_execution_authorized":False,
            "frames_archived":self.next_local_sequence}
