"""CM37C independent admin security core; NOT exposed through HTTP.

Uses a salted scrypt verifier, opaque hashed session/CSRF/confirmation
tokens, persistent rate limits and a hash-linked audit journal. The dashboard
remains read-only. This module issues one-time authorization receipts only;
it cannot execute operational or financial commands.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import time
from pathlib import Path

N=2**15
R=8
P=1
MAXMEM=64*1024*1024
COMMANDS={"START","PAUSE","PAUSE_ENTRIES","RESUME_ENTRIES","EMERGENCY_HALT"}
CRITICAL={"START","RESUME_ENTRIES","EMERGENCY_HALT"}
RADARS={"launch","smart_money"}

def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def password_verifier(password, salt):
    if not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError("password must have 12 to 256 characters")
    return hashlib.scrypt(password.encode(),salt=salt,n=N,r=R,p=P,maxmem=MAXMEM).hex()

class AdminSecurity:
    """Explicit local setup; separate SQLite security file, no external routes."""
    def __init__(self,path,*,clock=time.time,session_seconds=900):
        self.path=Path(path); self.clock=clock
        if type(session_seconds) is not int or not 60<=session_seconds<=3600:
            raise ValueError("invalid session lifetime")
        self.session_seconds=session_seconds
        if not self.path.is_file():
            # Do not create credentials or a writable surface implicitly.
            raise ValueError("security database requires explicit provisioning")

    @classmethod
    def provision(cls,path,password,**kwargs):
        path=Path(path)
        # Exclusive creation avoids replacing credentials or following symlinks.
        fd=__import__("os").open(path,__import__("os").O_CREAT|__import__("os").O_EXCL|__import__("os").O_WRONLY,0o600)
        __import__("os").close(fd)
        salt=secrets.token_bytes(32)
        conn=sqlite3.connect(path)
        try:
            with conn:
                conn.executescript("""
                CREATE TABLE credentials (singleton INTEGER PRIMARY KEY CHECK(singleton=1),salt BLOB NOT NULL,verifier TEXT NOT NULL);
                CREATE TABLE sessions (token_hash TEXT PRIMARY KEY,csrf_hash TEXT NOT NULL,issued REAL NOT NULL,expires REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE confirmations (token_hash TEXT PRIMARY KEY,session_hash TEXT NOT NULL,command TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE receipts (request_id TEXT PRIMARY KEY,session_hash TEXT NOT NULL,command TEXT NOT NULL,issued REAL NOT NULL);
                CREATE TABLE rate_limit (scope TEXT PRIMARY KEY,window REAL NOT NULL,attempts INTEGER NOT NULL);
                CREATE TABLE audit (seq INTEGER PRIMARY KEY,previous TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL);
                """)
                conn.execute("INSERT INTO credentials VALUES(1,?,?)",(salt,password_verifier(password,salt)))
        finally:
            conn.close()
        return cls(path,**kwargs)

    def _connect(self):
        return sqlite3.connect(self.path,timeout=5)

    def _now(self):
        now=self.clock()
        if type(now) not in (float,int) or not math.isfinite(now) or now<0:
            raise PermissionError("invalid security clock")
        return float(now)

    def _verify_audit_connection(self,conn):
        prev="0"*64;expected=1
        for seq,previous,payload,digest in conn.execute("SELECT seq,previous,payload,digest FROM audit ORDER BY seq"):
            if seq!=expected or previous!=prev or not hmac.compare_digest(digest,_sha(_json([seq,prev,payload]))):
                raise PermissionError("audit chain conflict")
            prev=digest;expected+=1
        return expected-1

    def _audit(self,conn,kind,at,scope):
        row=conn.execute("SELECT seq,digest FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        seq,prev=(row[0]+1,row[1]) if row else (1,"0"*64)
        payload=_json({"kind":kind,"at":at,"scope":scope})
        conn.execute("INSERT INTO audit VALUES(?,?,?,?)",(seq,prev,payload,_sha(_json([seq,prev,payload]))))

    def _rate(self,conn,scope,now,limit,seconds):
        row=conn.execute("SELECT window,attempts FROM rate_limit WHERE scope=?",(scope,)).fetchone()
        if row and now<row[0]: return False
        start,count=(now,0) if not row or now-row[0]>=seconds else row
        if count>=limit: return False
        conn.execute("INSERT INTO rate_limit VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET window=excluded.window,attempts=excluded.attempts",(scope,start,count+1))
        return True

    def login(self,password):
        now=self._now()
        conn=self._connect()
        result=None
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_audit_connection(conn)
                if not self._rate(conn,"login",now,5,60):
                    self._audit(conn,"LOGIN_RATE_LIMIT",now,"admin")
                else:
                    salt,expected=conn.execute("SELECT salt,verifier FROM credentials WHERE singleton=1").fetchone()
                    try: valid=hmac.compare_digest(password_verifier(password,salt),expected)
                    except (ValueError,TypeError): valid=False
                    if valid:
                        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                        conn.execute("INSERT INTO sessions(token_hash,csrf_hash,issued,expires) VALUES(?,?,?,?)",(_sha(token),_sha(csrf),now,now+self.session_seconds))
                        self._audit(conn,"LOGIN_OK",now,"admin")
                        result={"session":token,"csrf":csrf,"expires":now+self.session_seconds}
                    else: self._audit(conn,"LOGIN_FAILED",now,"admin")
        finally: conn.close()
        if result is None: raise PermissionError("authentication denied")
        return result

    def _session(self,conn,token,csrf,now):
        if not isinstance(token,str) or not isinstance(csrf,str) or not 20<=len(token)<=128 or not 20<=len(csrf)<=128:
            raise PermissionError("session denied")
        sid=_sha(token)
        row=conn.execute("SELECT csrf_hash,issued,expires,revoked FROM sessions WHERE token_hash=?",(sid,)).fetchone()
        if not row or row[3] or not row[1]<=now<row[2] or not hmac.compare_digest(row[0],_sha(csrf)):
            raise PermissionError("session denied")
        return sid

    @staticmethod
    def _command(action,radar):
        if action not in COMMANDS: raise ValueError("unsupported command")
        if action in ("START","PAUSE"):
            if radar not in RADARS: raise ValueError("explicit radar required")
        elif radar is not None: raise ValueError("global action has no radar")
        return _json({"action":action,"radar":radar})

    def confirm(self,token,csrf,*,action,radar=None):
        command=self._command(action,radar);now=self._now()
        conn=self._connect();result=None
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_audit_connection(conn)
                sid=self._session(conn,token,csrf,now)
                if self._rate(conn,"confirm:"+sid,now,10,60):
                    nonce=secrets.token_urlsafe(32)
                    conn.execute("INSERT INTO confirmations VALUES(?,?,?,?)",(_sha(nonce),sid,command,now+60))
                    self._audit(conn,"CONFIRMATION_ISSUED",now,command)
                    result=nonce
        finally: conn.close()
        if result is None: raise PermissionError("confirmation denied")
        return result

    def authorize(self,token,csrf,*,request_id,action,radar=None,confirmation=None):
        command=self._command(action,radar);now=self._now()
        if not isinstance(request_id,str) or not 16<=len(request_id)<=128 or not request_id.isascii():
            raise ValueError("invalid request id")
        conn=self._connect();result=None
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_audit_connection(conn)
                sid=self._session(conn,token,csrf,now)
                if not self._rate(conn,"command:"+sid,now,20,60):
                    self._audit(conn,"COMMAND_RATE_LIMIT",now,command)
                elif conn.execute("SELECT 1 FROM receipts WHERE request_id=?",(request_id,)).fetchone():
                    self._audit(conn,"COMMAND_REPLAY_DENIED",now,command)
                else:
                    allowed=action not in CRITICAL
                    if not allowed and isinstance(confirmation,str) and 20<=len(confirmation)<=128:
                        key=_sha(confirmation)
                        row=conn.execute("SELECT session_hash,command,expires FROM confirmations WHERE token_hash=?",(key,)).fetchone()
                        allowed=bool(row and row[0]==sid and row[1]==command and now<row[2])
                        if allowed: conn.execute("DELETE FROM confirmations WHERE token_hash=?",(key,))
                    if allowed:
                        conn.execute("INSERT INTO receipts VALUES(?,?,?,?)",(request_id,sid,command,now))
                        self._audit(conn,"AUTHORIZATION_ONLY",now,command)
                        result={"request_id":request_id,"action":action,"radar":radar,"authorized_for_review":True,"executed":False,"remote_writes_enabled":False}
                    else: self._audit(conn,"CONFIRMATION_DENIED",now,command)
        finally: conn.close()
        if result is None: raise PermissionError("command denied")
        return result

    def revoke(self,token,csrf):
        now=self._now();conn=self._connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_audit_connection(conn)
                sid=self._session(conn,token,csrf,now)
                conn.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?",(sid,))
                conn.execute("DELETE FROM confirmations WHERE session_hash=?",(sid,))
                self._audit(conn,"SESSION_REVOKED",now,"admin")
        finally: conn.close()

    def inspect_session(self,token,csrf):
        """Authenticated, bounded receipt history; never return credentials."""
        conn=self._connect()
        try:
            with conn:
                conn.execute("BEGIN")
                self._verify_audit_connection(conn)
                sid=self._session(conn,token,csrf,self._now())
                rows=conn.execute("SELECT request_id,command,issued FROM receipts WHERE session_hash=? ORDER BY issued DESC,request_id DESC LIMIT 100",(sid,)).fetchall()
                return [{"request_id":rid,"command":json.loads(command),"issued":issued} for rid,command,issued in rows]
        finally:
            conn.close()

    def inspect_receipt(self,token,csrf,request_id):
        conn=self._connect()
        try:
            with conn:
                conn.execute("BEGIN")
                self._verify_audit_connection(conn)
                sid=self._session(conn,token,csrf,self._now())
                row=conn.execute("SELECT command FROM receipts WHERE request_id=? AND session_hash=?",(request_id,sid)).fetchone()
                if row is None: raise PermissionError("receipt denied")
                return json.loads(row[0])
        finally:
            conn.close()

    def verify_audit(self):
        conn=self._connect()
        try:
            prev="0"*64;expected=1
            for seq,previous,payload,digest in conn.execute("SELECT seq,previous,payload,digest FROM audit ORDER BY seq"):
                if seq!=expected or previous!=prev or not hmac.compare_digest(digest,_sha(_json([seq,prev,payload]))):
                    raise ValueError("audit chain conflict")
                prev=digest;expected+=1
            return expected-1
        finally: conn.close()
