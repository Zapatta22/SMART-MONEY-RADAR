"""CM37E: HTTP administrative evaluation on a newly created local database.

Never imported by the ordinary read-only dashboard launcher. No operational
production database, remote listener, network collector or financial adapter
can be passed to this factory. The HTTP evaluation is a distinct opt-in test
surface. Remote HTTP administration remains disabled.
"""
from __future__ import annotations
import hmac
import json
import math
import re
import sqlite3
import time
from http.server import ThreadingHTTPServer
from threading import RLock
from smart_money_radar.services.admin_evaluation import IsolatedAdminEvaluation
from smart_money_radar.services.dashboard_http import _SMRRequestHandler, _DASHBOARD_HTML
from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.services.reconciliation_diagnostics import ReconciliationDiagnosticsService

_PREFIX="/evaluation/admin/"
_ROUTES={"login","logout","session","confirm","execute","outcome"}
_REQUEST_ID=re.compile(r"[A-Za-z0-9_-]{16,128}\Z")

# No cookie/session token in URL, storage, cache or markup. Explicit bearer in
# memory; separate CSRF secret, exact Origin/Host, no CORS. HTTPS is mandatory
# before any future non-local exposure: this factory has no remote-bind option.
_ADMIN_PANEL="""<section class="panel" id="adminEval"><h2>Administração · avaliação isolada</h2>
<p class="scope">Somente controles do banco de teste. Operações reais e administração externa bloqueadas.</p>
<label>Senha administrativa <input id="adminPassword" type="password" autocomplete="current-password" maxlength="256"></label>
<button id="adminLogin" type="button">Entrar</button>
<button id="adminLogout" type="button" disabled>Sair</button>
<p id="adminStatus" role="status">Sessão indisponível.</p>
<label>Comando <select id="adminAction"><option value="START">Iniciar radar</option><option value="PAUSE">Pausar radar</option><option value="PAUSE_ENTRIES">Bloquear entradas</option><option value="RESUME_ENTRIES">Retomar entradas</option><option value="EMERGENCY_HALT">Parada emergencial</option></select></label>
<label>Radar <select id="adminRadar"><option value="launch">Launch Radar</option><option value="smart_money">Smart Money Radar</option></select></label>
<button id="adminExecute" type="button" disabled>Executar no ambiente isolado</button>
<button id="adminHistory" type="button" disabled>Consultar histórico</button>
<pre id="adminResult" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></section>
<script>
(()=>{let session="",csrf="",expires=0,busy=false;
const el=id=>document.getElementById(id);
const controls=()=>{const active=!!session&&!busy;el("adminLogin").disabled=busy||!!session;for(const k of ["adminLogout","adminExecute","adminHistory"])el(k).disabled=!active;};
function clear(){session="";csrf="";expires=0;el("adminPassword").value="";el("adminResult").textContent="";controls();}
async function request(route,body={}){const headers={"Content-Type":"application/json"};if(session){headers.Authorization="Bearer "+session;headers["X-SMR-CSRF"]=csrf;}const res=await fetch("/evaluation/admin/"+route,{method:"POST",headers,body:JSON.stringify(body),cache:"no-store",credentials:"omit",redirect:"error"});if(res.status===401||res.status===403){clear();throw Error("Não autorizado. Entre novamente.");}if(!res.ok)throw Error("Solicitação recusada ("+res.status+").");return res.json();}
async function run(fn){if(busy)return;busy=true;controls();try{await fn();}catch(e){el("adminStatus").textContent=e.message;}finally{busy=false;controls();}}
el("adminLogin").onclick=()=>run(async()=>{const password=el("adminPassword").value;el("adminPassword").value="";const s=await request("login",{password});session=s.session;csrf=s.csrf;expires=s.expires;el("adminStatus").textContent="Sessão local de avaliação autenticada.";});
el("adminLogout").onclick=()=>run(async()=>{try{await request("logout");}finally{clear();el("adminStatus").textContent="Sessão encerrada localmente."; }});
el("adminExecute").onclick=()=>run(async()=>{if(Date.now()/1000>=expires){clear();throw Error("Sessão expirada.");}const action=el("adminAction").value,radar=action==="START"||action==="PAUSE"?el("adminRadar").value:null;
if(!window.confirm("Confirmar "+action+(radar?" — "+radar:"")+" apenas na avaliação?"))return;
const nonce=(await request("confirm",{action,radar})).confirmation;
const request_id=Array.from(crypto.getRandomValues(new Uint8Array(24)),b=>b.toString(16).padStart(2,"0")).join("");
el("adminResult").textContent="Solicitação: "+request_id+" · aguardando confirmação do journal.";
const receipt=await request("execute",{request_id,action,radar,confirmation:nonce});const outcome=await request("outcome",{request_id});el("adminResult").textContent=JSON.stringify({receipt,outcome},null,2);});
el("adminHistory").onclick=()=>run(async()=>{const history=await request("session");el("adminResult").textContent=JSON.stringify(history,null,2);});
setInterval(()=>{if(session&&Date.now()/1000>=expires){clear();el("adminStatus").textContent="Sessão expirada.";}},1000);
window.addEventListener("pagehide",clear);controls();})();
</script>"""

class _EvaluationHandler(_SMRRequestHandler):
    server_version="SMREvaluation/1.0"
    def _origin_ok(self):
        values=self.headers.get_all("Host") or []
        origins=self.headers.get_all("Origin") or []
        return (self.client_address[0]=="127.0.0.1" and values==[self.server.eval_host]
                and origins==["http://"+self.server.eval_host]
                and not any(self.headers.get(x) for x in ("Forwarded","X-Forwarded-For","X-Forwarded-Host","X-Forwarded-Proto")))
    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("transfer encoding denied")
        lens=self.headers.get_all("Content-Length") or []
        if len(lens)!=1 or not lens[0].isascii() or not lens[0].isdigit():
            raise ValueError("length required")
        n=int(lens[0])
        if not 2<=n<=4096 or self.headers.get("Content-Type")!="application/json":
            raise ValueError("invalid request body")
        def pairs(items):
            result={}
            for key,value in items:
                if key in result: raise ValueError("duplicate field")
                result[key]=value
            return result
        body=json.loads(self.rfile.read(n),object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid number")))
        if type(body) is not dict: raise ValueError("object required")
        return body
    def _credentials(self):
        hdr=self.headers.get_all("Authorization") or []
        cs=self.headers.get_all("X-SMR-CSRF") or []
        if len(hdr)!=1 or not hdr[0].startswith("Bearer ") or len(cs)!=1:
            raise PermissionError("missing session")
        return hdr[0][7:],cs[0]
    def _send_html(self):
        if self.headers.get_all("Host")!=[self.server.eval_host]:
            self._send_json(403,{"error":"origin_denied"})
            return
        html=_DASHBOARD_HTML.replace("</body>",_ADMIN_PANEL+"</body>",1)
        body=html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; manifest-src 'self'; worker-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith(_PREFIX):
            self._send_json(405,{"error":"method_not_allowed"})
        elif self.headers.get_all("Host")!=[self.server.eval_host]:
            self._send_json(403,{"error":"origin_denied"})
        else:
            super().do_GET()
    def do_POST(self):
        if not self.path.startswith(_PREFIX):
            return super().do_POST()
        route=self.path[len(_PREFIX):]
        if route not in _ROUTES:
            self._send_json(404,{"error":"not_found"});return
        if not self._origin_ok():
            self._send_json(403,{"error":"origin_denied"});return
        self.connection.settimeout(5)
        try:
            data=self._body()
            fields={"login":{"password"},"logout":set(),"session":set(),"confirm":{"action","radar"},"execute":{"action","radar","request_id","confirmation"},"outcome":{"request_id"}}
            if set(data)!=fields[route]: raise ValueError("unexpected fields")
            if route in ("outcome","execute") and (not isinstance(data["request_id"],str) or not _REQUEST_ID.fullmatch(data["request_id"])):
                raise ValueError("invalid request id")
            evaluator=self.server.evaluation
            with self.server.admin_lock:
                if route=="login":
                    result=evaluator.login(data["password"])
                else:
                    token,csrf=self._credentials()
                    security=evaluator.security
                    if route=="logout":
                        security.revoke(token,csrf);result={"revoked":True}
                    elif route=="session":
                        entries=security.inspect_session(token,csrf)
                        result={"scope":"ISOLATED_EVALUATION","items":[dict(item,outcome=evaluator.outcome(item["request_id"])) for item in entries],"remote_writes_enabled":False}
                    elif route=="confirm":
                        result={"confirmation":evaluator.confirm(token,csrf,**data)}
                    elif route=="execute":
                        result=evaluator.execute(token,csrf,**data)
                    else:
                        security.inspect_receipt(token,csrf,data["request_id"])
                        result=evaluator.outcome(data["request_id"])
            self._send_json(200,result)
        except PermissionError:
            self._send_json(401,{"error":"unauthorized_or_replayed"})
        except (ValueError,TypeError,KeyError,UnicodeError):
            self._send_json(400,{"error":"invalid_request"})
        except (sqlite3.Error,OSError,RuntimeError):
            self._send_json(503,{"error":"evaluation_unavailable"})
    def do_OPTIONS(self):
        self._send_json(405,{"error":"method_not_allowed"})

def create_isolated_admin_http(root,*,password,clock=time.time,port=0):
    """Explicit test entrypoint, new directory only, fixed IPv4 loopback."""
    if type(port) is not int or not 0<=port<=65535:
        raise ValueError("invalid local port")
    evaluation=IsolatedAdminEvaluation(root,password=password,clock=clock)
    try:
        server=ThreadingHTTPServer(("127.0.0.1",port),_EvaluationHandler)
        server.eval_host="127.0.0.1:"+str(server.server_port)
        server.evaluation=evaluation
        server.admin_lock=RLock()
        # Standard read-only API reuses a distinct capability that is not
        # returned by the administrative authentication surface.
        import secrets
        server.auth_token=secrets.token_urlsafe(32)
        server.dashboard_service=DashboardReadService(evaluation.store)
        server.diagnostics_service=ReconciliationDiagnosticsService(evaluation.store)
        return server
    except BaseException:
        evaluation.close()
        raise
