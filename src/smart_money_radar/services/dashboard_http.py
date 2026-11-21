"""Adaptador HTTP local, autenticado e somente leitura para o SMR."""

import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from smart_money_radar.services.dashboard_read import DashboardReadService
from smart_money_radar.services.reconciliation_diagnostics import (
    ReconciliationDiagnosticsService,
)
from smart_money_radar.storage.event_store import SQLiteEventStore


_DASHBOARD_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART MONEY RADAR</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0b1018;color:#e8edf5}body{margin:0;padding:18px;max-width:1050px;margin-inline:auto}h1{font-size:1.3rem;letter-spacing:.08em}.muted{color:#9aa8ba;font-size:.85rem}.panel{background:#141d29;border:1px solid #293648;border-radius:12px;padding:14px;margin:14px 0}.row{display:flex;gap:8px;flex-wrap:wrap}input,button,select{font:inherit;padding:10px;border-radius:8px;border:1px solid #35465d;background:#0b131e;color:#e8edf5}input{flex:1;min-width:200px}button{background:#234b72}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px}.metric{background:#0d1520;border:1px solid #293648;border-radius:9px;padding:11px}.metric b{display:block;font-size:1.4rem;overflow-wrap:anywhere}.good{color:#76d6a2}.warn{color:#f2c36d}.bad{color:#ff8585}.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.83rem}td,th{text-align:left;padding:8px;border-bottom:1px solid #293648;overflow-wrap:anywhere}#message{min-height:1.3em;color:#f2c36d}
</style></head><body>
<h1>SMART MONEY RADAR</h1><p class="muted">Painel local · consulta somente leitura</p>
<section class="panel"><div class="row"><input id="token" type="password" autocomplete="off" placeholder="Token local SMR_API_TOKEN"><button id="connect">Conectar</button><button id="refresh" disabled>Atualizar</button></div><p id="message" role="status" aria-live="polite"></p><p class="muted">O token permanece somente na memória desta página e não é salvo no navegador. Abra no mesmo dispositivo onde o SMR está executando.</p></section>
<section class="panel"><h2>Visão geral</h2><div class="grid" id="metrics"></div><h3>Status de reconciliação</h3><div class="grid" id="statuses"></div></section>
<section class="panel"><h2>Estado dos coletores</h2><p class="muted">Status live: UNKNOWN quando não há telemetria autenticada. A última data de arquivo não demonstra coletor ativo.</p><div class="grid" id="radarCollectors"></div></section>
<section class="panel"><h2>Motivos recorrentes</h2><div id="reasons" class="muted">Aguardando conexão.</div></section>
<section class="panel"><h2>Eventos dos radares · evidências</h2><p class="muted">Lançamentos e Smart Money são independentes. Arquivo histórico/fixture não significa captura live; cobertura e autorização permanecem desconhecidas ou bloqueadas.</p><div class="grid"><section><h3>Launch Radar</h3><div id="launchEvents" class="tablewrap muted">Nenhuma evidência arquivada disponível.</div></section><section><h3>Smart Money Radar</h3><div id="smartEvents" class="tablewrap muted">Nenhuma evidência arquivada disponível.</div></section></div></section>
<section class="panel"><h2>Últimos eventos</h2><div class="tablewrap"><table><thead><tr><th>Data</th><th>Carteira</th><th>Ativo</th><th>Direção</th><th>Quantidade</th></tr></thead><tbody id="events"></tbody></table></div></section>
<section class="panel"><div class="row"><h2 style="flex:1">Auditoria de swaps</h2><select id="statusFilter"><option value="">Todos os status</option><option>MATCHED</option><option>INCOMPLETE</option><option>AMBIGUOUS</option><option>UNRESOLVED</option></select><button id="loadAttempts" disabled>Consultar</button></div><div class="tablewrap"><table><thead><tr><th>Data</th><th>Status</th><th>Operação</th><th>Instrução</th><th>Motivo</th></tr></thead><tbody id="attempts"></tbody></table></div></section>
<script>
let token="";
const el=id=>document.getElementById(id), val=v=>v===null||v===undefined||v===""?"—":String(v), short=v=>{v=val(v);return v.length>18?v.slice(0,8)+"…"+v.slice(-6):v};
async function api(path){const r=await fetch(path,{headers:{Authorization:"Bearer "+token},cache:"no-store"});if(!r.ok){if(r.status===401)throw Error("Token inválido ou ausente.");throw Error("Falha HTTP "+r.status);}return r.json();}
function td(tr,v){const x=document.createElement("td");x.textContent=val(v);tr.append(x);return x;}
function rowEmpty(target,cols,msg){const tr=document.createElement("tr"),x=document.createElement("td");x.colSpan=cols;x.textContent=msg;tr.append(x);target.replaceChildren(tr);}
function render(data){
 const d=data.reconciliation||{},st=d.statuses||{},labels=["Tentativas auditadas","Operações distintas","Assinaturas distintas","Transações pendentes"],nums=[d.total_attempts,d.distinct_operations,d.distinct_signatures,d.pending_transactions_count],m=el("metrics");m.replaceChildren();
 nums.forEach((n,i)=>{const box=document.createElement("div"),l=document.createElement("span"),b=document.createElement("b");box.className="metric";l.className="muted";l.textContent=labels[i];b.textContent=val(n);box.append(l,b);m.append(box);});
 const s=el("statuses");s.replaceChildren();Object.entries(st).forEach(([k,n])=>{const box=document.createElement("div"),l=document.createElement("span"),b=document.createElement("b");box.className="metric";l.className="muted";l.textContent=k;b.textContent=val(n);b.className=k==="MATCHED"?"good":k==="INCOMPLETE"?"warn":"bad";box.append(l,b);s.append(box);});
 const collectors=el("radarCollectors");collectors.replaceChildren();
 Object.entries(data.radars||{}).forEach(([name,state])=>{
   const box=document.createElement("div"),title=document.createElement("b"),detail=document.createElement("p");
   box.className="metric";title.textContent=name==="launch"?"Launch Radar":"Smart Money Radar";
   detail.className="muted";detail.textContent="Coletor: "+val(state.status)+" · Cobertura: "+val(state.evidence_coverage)+" · Último arquivo: "+val(state.last_archived_event_at);
   box.append(title,detail);collectors.append(box);
 });
 const reasons=el("reasons");reasons.replaceChildren();(d.top_reasons||[]).forEach(x=>{const p=document.createElement("p");p.textContent=val(x.reason)+" · "+val(x.count)+" ocorrência(s)";reasons.append(p);});if(!reasons.children.length)reasons.textContent="Nenhum motivo registrado.";
 const radarChannels=data.radar_events||{};
 [["launch","launchEvents"],["smart_money","smartEvents"]].forEach(([name,id])=>{
  const panel=el(id),items=radarChannels[name]||[];panel.replaceChildren();
  if(!items.length){panel.textContent="Nenhum evento arquivado disponível.";return;}
  const table=document.createElement("table"),head=document.createElement("thead"),tr=document.createElement("tr");
  ["Tipo / ID","Proveniência / evidência","Disponível","Sinal / bloqueio"].forEach(h=>{const th=document.createElement("th");th.textContent=h;tr.append(th);});
  head.append(tr);table.append(head);const body=document.createElement("tbody");
  items.forEach(x=>{const r=document.createElement("tr");td(r,x.event_type+" · "+short(x.id)+(x.wallet_address?" · "+short(x.wallet_address):""));td(r,(x.origin||"UNKNOWN")+" · "+(x.source_id||"UNKNOWN")+" · "+(x.evidence_quality||"UNKNOWN")+" · "+(x.coverage||"UNKNOWN")+" · "+short(x.raw_sha256));td(r,x.available_at);td(r,(x.direction||x.verdict||"UNKNOWN")+" · "+((x.reasons||[]).slice(0,3).join(", ")||"sem justificativa"));body.append(r);});
  table.append(body);panel.append(table);
 });
 const events=el("events");events.replaceChildren();(data.recent_events||[]).forEach(x=>{const tr=document.createElement("tr");td(tr,x.occurred_at);td(tr,short(x.wallet_address));td(tr,short(x.token_mint));td(tr,x.direction);td(tr,x.amount);events.append(tr);});if(!events.children.length)rowEmpty(events,5,"Nenhum evento persistido.");
}
async function refresh(){el("message").textContent="Consultando banco local…";try{render(await api("/api/v1/dashboard"));el("message").textContent="Conectado · dados atualizados · somente leitura";}catch(e){el("message").textContent=e.message;}}
async function attempts(){el("message").textContent="Consultando auditoria…";try{const q=new URLSearchParams({limit:"100"});if(el("statusFilter").value)q.set("status",el("statusFilter").value);const data=await api("/api/v1/reconciliation/attempts?"+q),body=el("attempts");body.replaceChildren();(data.items||[]).forEach(x=>{const tr=document.createElement("tr"),s=td(tr,x.attempted_at),status=td(tr,x.status);status.className=x.status==="MATCHED"?"good":x.status==="INCOMPLETE"?"warn":"bad";td(tr,short(x.operation_id));td(tr,x.instruction_index);td(tr,x.reason);body.append(tr);});if(!body.children.length)rowEmpty(body,5,"Nenhuma tentativa encontrada.");el("message").textContent="Auditoria atualizada.";}catch(e){el("message").textContent=e.message;}}
el("connect").addEventListener("click",async()=>{token=el("token").value.trim();if(token.length<32){token="";el("message").textContent="Informe o token completo (mínimo 32 caracteres).";return;}el("refresh").disabled=false;el("loadAttempts").disabled=false;await refresh();});
el("refresh").addEventListener("click",refresh);el("loadAttempts").addEventListener("click",attempts);
</script></body></html>"""

class _SMRRequestHandler(BaseHTTPRequestHandler):
    server_version = "SMRReadOnly/1.0"
    sys_version = ""

    def _send_html(self) -> None:
        body = _DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.auth_token}"
        # Constant-time comparison avoids leaking token-prefix timing.
        import hmac
        if not hmac.compare_digest(supplied, expected):
            self._send_json(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/dashboard"):
            self._send_html()
            return
        if not self._authorized():
            return
        params = parse_qs(parsed.query, keep_blank_values=False)
        try:
            if parsed.path == "/health":
                self._send_json(200, {"status": "ok", "mode": "read_only"})
                return
            if parsed.path == "/api/v1/dashboard":
                wallet = params.get("wallet_address", [None])[0]
                result = self.server.dashboard_service.get_overview(
                    wallet_address=wallet
                )
                self._send_json(200, result)
                return
            if parsed.path == "/api/v1/reconciliation/attempts":
                requested_limit = int(params.get("limit", ["100"])[0])
                if requested_limit < 1 or requested_limit > 500:
                    raise ValueError("limit deve estar entre 1 e 500.")
                result = self.server.diagnostics_service.list_attempts(
                    wallet_address=params.get("wallet_address", [None])[0],
                    signature=params.get("signature", [None])[0],
                    operation_id=params.get("operation_id", [None])[0],
                    status=params.get("status", [None])[0],
                    since=params.get("since", [None])[0],
                    until=params.get("until", [None])[0],
                    limit=requested_limit,
                )
                self._send_json(200, {"items": DashboardReadService._json_value(result)})
                return
            self._send_json(404, {"error": "not_found"})
        except (TypeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid_query", "detail": str(exc)})
        except Exception:
            self._send_json(500, {"error": "internal_error"})

    def do_POST(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def do_PUT(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def log_message(self, format, *args):
        # Avoid logging authorization headers or query values that may be sensitive.
        return


def create_read_only_server(
    event_store: SQLiteEventStore,
    *,
    auth_token: str,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Create, but do not start, an authenticated loopback-only HTTP server."""
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError as exc:
        raise ValueError("host must be a loopback IP address") from exc
    if not is_loopback:
        raise ValueError("SMR read-only API must bind to loopback only")
    if not isinstance(auth_token, str) or len(auth_token) < 32:
        raise ValueError("auth_token must contain at least 32 characters")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer between 0 and 65535")

    server = ThreadingHTTPServer((host, port), _SMRRequestHandler)
    server.auth_token = auth_token
    server.dashboard_service = DashboardReadService(event_store)
    server.diagnostics_service = ReconciliationDiagnosticsService(event_store)
    return server


def main(argv=None) -> None:
    """Run the local read-only API without enabling Helius/RPC networking."""
    import argparse
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="smr-api",
        description="API HTTP local e somente leitura do SMART MONEY RADAR.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    token = os.environ.get("SMR_API_TOKEN", "")
    if len(token) < 32:
        raise SystemExit(
            "Defina SMR_API_TOKEN com pelo menos 32 caracteres antes de iniciar."
        )
    database_path = Path(
        os.environ.get("SMR_DB_PATH", "data/smr_history.sqlite3")
    ).expanduser()
    event_store = SQLiteEventStore(database_path, read_only=True)
    server = None
    try:
        server = create_read_only_server(
            event_store, auth_token=token, host=args.host, port=args.port
        )
        print(f"SMR API somente leitura disponível em http://{args.host}:{server.server_port}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSMR API encerrada.")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    finally:
        if server is not None:
            server.server_close()
        event_store.close()
