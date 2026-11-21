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
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART MONEY RADAR</title><meta name="theme-color" content="#0b1018"><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/smr-icon.svg" type="image/svg+xml">
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0b1018;color:#e8edf5}body{margin:0;padding:18px;max-width:1050px;margin-inline:auto}h1{font-size:1.3rem;letter-spacing:.08em}.muted{color:#9aa8ba;font-size:.85rem}.panel{background:#141d29;border:1px solid #293648;border-radius:12px;padding:14px;margin:14px 0}.row{display:flex;gap:8px;flex-wrap:wrap}input,button,select{font:inherit;padding:10px;border-radius:8px;border:1px solid #35465d;background:#0b131e;color:#e8edf5}input{flex:1;min-width:200px}button{background:#234b72}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px}.metric{background:#0d1520;border:1px solid #293648;border-radius:9px;padding:11px}.metric b{display:block;font-size:1.4rem;overflow-wrap:anywhere}.good{color:#76d6a2}.warn{color:#f2c36d}.bad{color:#ff8585}.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.83rem}td,th{text-align:left;padding:8px;border-bottom:1px solid #293648;overflow-wrap:anywhere}#message{min-height:1.3em;color:#f2c36d}

html{scroll-behavior:smooth}h2{font-size:1.08rem}h3{font-size:.92rem}.brand{display:flex;align-items:center;gap:12px;margin:14px 0}.brand img{width:52px;height:52px}.brand h1{margin:0}.brand p{margin:4px 0}.nav{display:flex;overflow:auto;gap:8px;padding:8px 0;position:sticky;top:0;background:#0b1018;z-index:2}.nav a{white-space:nowrap;color:#bce0f8;text-decoration:none;background:#172638;border:1px solid #314763;border-radius:10px;padding:10px;font-size:.8rem}.panel{scroll-margin-top:68px;min-width:0}.scope{font-size:.75rem;color:#f2c36d;letter-spacing:.05em}.grid>section{min-width:0}#freshness{font-size:.82rem;color:#f2c36d}.unavailable{color:#a5b4c6}@media(max-width:600px){body{padding:11px}.grid{grid-template-columns:minmax(0,1fr)}.panel{padding:11px}input{min-width:0;width:100%;flex:1 1 100%}button{min-height:44px}.brand h1{font-size:1.12rem}.nav a{padding:12px 10px}.tablewrap{max-width:100%}}
</style></head><body>
<header class="brand"><img src="/smr-icon.svg" alt=""><div><h1>SMART MONEY RADAR</h1><p class="muted">CENTRAL DE INTELIGÊNCIA SOLANA · somente leitura</p></div></header><nav class="nav" aria-label="Navegação principal"><a href="#patrimonio">Patrimônio</a><a href="#radares">Radares</a><a href="#oportunidades">Oportunidades</a><a href="#negociacoes">Negociações</a><a href="#capital">Capital e risco</a><a href="#carteiras">Carteiras</a><a href="#alertas">Alertas</a><a href="#supervisor">Supervisor</a><a href="#configuracoes">Configurações</a></nav><p id="freshness" role="status">Sem consulta autenticada · indicadores indisponíveis.</p>
<section class="panel"><div class="row"><input id="token" type="password" autocomplete="off" placeholder="Token local SMR_API_TOKEN"><button id="connect">Conectar</button><button id="refresh" disabled>Atualizar</button></div><p id="message" role="status" aria-live="polite">JavaScript ainda não inicializado. Se esta mensagem persistir, recarregue a página no Chrome.</p><noscript>JavaScript desativado: habilite para conectar.</noscript><p class="muted">O token permanece somente na memória desta página e não é salvo no navegador. Abra no mesmo dispositivo onde o SMR está executando.</p></section>
<section class="panel" id="patrimonio"><h2>Patrimônio</h2><p class="scope">SIMULAÇÃO SINTÉTICA · NÃO É SALDO REAL</p><p class="muted">Apenas histórico sintético verificado no journal local; não representa rentabilidade real. Contas e moedas não são somadas.</p><div id="equityCards" class="grid"><p class="unavailable">Aguardando dados persistidos.</p></div><div id="equityHistory" aria-label="Histórico patrimonial sintético"></div><p class="muted">Filtros abaixo se aplicam a posições e negociações, não ao saldo global.</p><div class="row"><label>Radar <select id="filterRadar"><option value="">Todos</option><option value="launch">Launch</option><option value="smart_money">Smart Money</option></select></label><label>Estratégia <select id="filterStrategy"><option value="">Todas</option><option value="immediate">Imediata</option><option value="confirmed">Confirmada</option></select></label><label>Histórico desde <input type="date" id="filterSince"></label><label>Até <input type="date" id="filterUntil"></label></div><div id="filteredPositions"></div></section><section class="panel"><h2>Visão geral</h2><div class="grid" id="metrics"></div><h3>Status de reconciliação</h3><div class="grid" id="statuses"></div></section>
<section class="panel" id="radares"><h2>Estado dos coletores</h2><p class="muted">Status live: UNKNOWN quando não há telemetria autenticada. A última data de arquivo não demonstra coletor ativo.</p><div class="grid" id="radarCollectors"></div></section>
<section class="panel"><h2>Motivos recorrentes</h2><div id="reasons" class="muted">Aguardando conexão.</div></section>
<section class="panel"><h2>Eventos dos radares · evidências</h2><p class="muted">Lançamentos e Smart Money são independentes. Arquivo histórico/fixture não significa captura live; cobertura e autorização permanecem desconhecidas ou bloqueadas.</p><div class="grid"><section><h3>Launch Radar</h3><div id="launchEvents" class="tablewrap muted">Nenhuma evidência arquivada disponível.</div></section><section><h3>Smart Money Radar</h3><div id="smartEvents" class="tablewrap muted">Nenhuma evidência arquivada disponível.</div></section></div></section>
<section class="panel" id="oportunidades"><h2>Inteligência e risco · análise offline</h2><p class="muted">Pontuação observacional; confiança UNKNOWN sem prova independente. Nenhuma ordem autorizada.</p><div class="grid"><section><h3>Launch Radar</h3><div id="launchOpportunities" class="tablewrap muted"></div></section><section><h3>Smart Money Radar</h3><div id="smartOpportunities" class="tablewrap muted"></div></section></div></section>
<section class="panel" id="negociacoes"><h2>Paper Trading · somente testes sintéticos</h2><p class="muted">Capital virtual independente por execução. Não representa rentabilidade histórica ou futura. Replay histórico, prospectivo e live bloqueados.</p><div class="grid"><section><h3>Launch Radar</h3><div id="launchSynthetic" class="tablewrap muted"></div></section><section><h3>Smart Money Radar</h3><div id="smartSynthetic" class="tablewrap muted"></div></section></div></section>
<section class="panel" id="capital"><h2>Capital multipool · sintético</h2><div id="capitalAccounts" class="muted"></div></section>
<section class="panel" id="alertas"><h2>Controles locais e alertas</h2><p class="muted">Somente leitura; sem autorização remota ou operação financeira.</p><div id="operationalState"></div><div id="operationalAlerts"></div></section>
<section class="panel" id="carteiras"><h2>Smart Money · carteiras descobertas</h2><p class="muted">Ranking observacional local, não ranking de rentabilidade. Candidatas não qualificadas não votam no consenso automático.</p><div id="walletDiscovery" class="tablewrap muted"></div></section>
<section class="panel" id="supervisor"><h2>Supervisor · arquivo local</h2><p class="muted">Heartbeat local não comprova conexão à Solana nem execução financeira.</p><div id="supervisorStatus"></div><div id="supervisorHistory" aria-live="polite"></div><div id="supervisorAlerts"></div></section>
<section class="panel"><h2>Últimos eventos</h2><div class="tablewrap"><table><thead><tr><th>Data</th><th>Carteira</th><th>Ativo</th><th>Direção</th><th>Quantidade</th></tr></thead><tbody id="events"></tbody></table></div></section>
<section class="panel"><div class="row"><h2 style="flex:1">Auditoria de swaps</h2><select id="statusFilter"><option value="">Todos os status</option><option>MATCHED</option><option>INCOMPLETE</option><option>AMBIGUOUS</option><option>UNRESOLVED</option></select><button id="loadAttempts" disabled>Consultar</button></div><div class="tablewrap"><table><thead><tr><th>Data</th><th>Status</th><th>Operação</th><th>Instrução</th><th>Motivo</th></tr></thead><tbody id="attempts"></tbody></table></div></section>
<section class="panel" id="configuracoes"><h2>Configurações e controle</h2><p class="scope">COMANDOS EXTERNOS BLOQUEADOS</p><p>Iniciar, pausar, configurar risco, stop-loss, take-profit, capital virtual e parada emergencial: disponíveis somente após homologação administrativa. Nenhuma ordem real autorizada.</p></section><script>
window.addEventListener("error",function(){document.getElementById("message").textContent="Falha de JavaScript. Recarregue a página.";});
</script><script>
let token="",busy=false;
const el=id=>document.getElementById(id), val=v=>v===null||v===undefined||v===""?"—":String(v), short=v=>{v=val(v);return v.length>18?v.slice(0,8)+"…"+v.slice(-6):v};
async function api(path){
 const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
 try {
  const r=await fetch(path,{headers:{Authorization:"Bearer "+token},cache:"no-store",credentials:"omit",redirect:"error",signal:controller.signal});
  if(r.status===401){token="";throw Error("Token inválido ou expirado. Copie o token do servidor atual.");}
  if(!r.ok)throw Error("Servidor respondeu HTTP "+r.status+".");
  return await r.json();
 }catch(e){if(e.name==="AbortError")throw Error("Servidor indisponível: tempo de resposta excedido.");if(e instanceof TypeError)throw Error("Falha de comunicação. Confira se o servidor Termux está ativo.");throw e;}
 finally{clearTimeout(timer);}
}
function td(tr,v){const x=document.createElement("td");x.textContent=val(v);tr.append(x);return x;}
function rowEmpty(target,cols,msg){const tr=document.createElement("tr"),x=document.createElement("td");x.colSpan=cols;x.textContent=msg;tr.append(x);target.replaceChildren(tr);}
let lastOverview=null;
function validDate(at){return typeof at==="string"&&Number.isFinite(Date.parse(at));}
function inPeriod(at){const start=el("filterSince").value,end=el("filterUntil").value;if(!start&&!end)return true;if(!validDate(at))return false;const date=new Date(at).toISOString().slice(0,10);return (!start||date>=start)&&(!end||date<=end);}
function selectedScope(x){const r=el("filterRadar").value,s=el("filterStrategy").value;return (!r||x.radar===r)&&(!s||x.strategy===s);}
function renderScoped(data){
 const target=el("filteredPositions");target.replaceChildren();
 if(el("filterSince").value&&el("filterUntil").value&&el("filterSince").value>el("filterUntil").value){target.textContent="Período inválido.";return;}
 const title=document.createElement("h3");title.textContent="Posições e negociações sintéticas · filtros UTC";target.append(title);
 let count=0;
 for(const a of data.capital_accounts||[]){for(const p of a.positions||[]){if(!selectedScope(p))continue;
 const report=p.report||{};const fills=(report.fills||[]).filter(f=>inPeriod(f.filled_at));
 if((el("filterSince").value||el("filterUntil").value)&&!fills.length)continue;
 const line=document.createElement("p");line.textContent=val(a.account_id)+" · "+val(a.currency)+" · "+val(p.radar)+" · "+val(p.strategy)+" · reserva "+val(p.budget)+" · quantidade aberta "+val(report.open_quantity)+" · execuções no período "+fills.length;target.append(line);count++;}}
 for(const [radar,runs] of Object.entries(data.synthetic_paper||{})){for(const run of runs){if(!selectedScope({...run,radar})||!run.report)continue;for(const f of run.report.fills||[]){if(!inPeriod(f.filled_at))continue;const line=document.createElement("p");line.textContent=val(radar)+" · "+val(run.strategy)+" · "+val(f.side)+" · "+val(f.quantity)+" @ "+val(f.price)+" · "+val(f.filled_at)+" · SIMULAÇÃO";target.append(line);count++;}}}
 if(!count){const p=document.createElement("p");p.textContent="Nenhum registro disponível para os filtros aplicados.";target.append(p);}
}
function appendEquityHistory(data){
 const target=el("equityHistory");target.replaceChildren();
 const ns="http://www.w3.org/2000/svg";
 for(const a of (data.capital_accounts||[])){
  const group=document.createElement("section"),heading=document.createElement("h3"),note=document.createElement("p");
  heading.textContent=val(a.account_id)+" · "+val(a.currency);group.append(heading);
  const points=(a.equity_history||[]);
  const numbers=points.map(p=>Number(p.equity));
  if(a.status==="CONFLICTED"||points.length<2||numbers.some(n=>!Number.isFinite(n))){
    note.textContent="Histórico insuficiente ou indisponível para gráfico.";group.append(note);target.append(group);continue;
  }
  const min=Math.min(...numbers),max=Math.max(...numbers),range=max-min;
  const svg=document.createElementNS(ns,"svg");svg.setAttribute("viewBox","0 0 360 138");svg.setAttribute("width","100%");svg.setAttribute("role","img");svg.setAttribute("aria-label","Patrimônio sintético ao longo dos eventos registrados");
  const poly=document.createElementNS(ns,"polyline");
  poly.setAttribute("points",numbers.map((v,i)=>(12+336*i/(numbers.length-1))+","+(range?122-106*(v-min)/range:69)).join(" "));
  poly.setAttribute("fill","none");poly.setAttribute("stroke","#27d5ab");poly.setAttribute("stroke-width","2.5");svg.append(poly);group.append(svg);
  note.className="muted";note.textContent=points.length+" eventos locais · "+points[0].at+" → "+points[points.length-1].at+(a.history_truncated?" · janela limitada aos últimos 500 eventos":"")+" · eixo X: ordem dos eventos · mínimo "+val(min)+" · máximo "+val(max);group.append(note);
  const stats=document.createElement("p");
  const ratio=a.settled_win_rate===null||a.settled_win_rate===undefined?null:Number(a.settled_win_rate);
  stats.textContent="PnL realizado "+val(a.realized_pnl)+" · não realizado "+val(a.unrealized_pnl)+" · Execuções sintéticas encerradas "+val(a.settled_runs)+" · Execuções lucrativas "+(ratio===null?"indisponível":(100*ratio).toLocaleString("pt-BR",{maximumFractionDigits:2})+"%")+" (não é taxa de trades)";
  group.append(stats);target.append(group);
 }
 if(!target.children.length)target.textContent="Histórico patrimonial indisponível.";
}
function render(data){
 lastOverview=data;
 appendEquityHistory(data);
 renderScoped(data);
 const cards=el("equityCards");cards.replaceChildren();for(const a of (data.capital_accounts||[])){const c=document.createElement("section");c.className="metric";const title=document.createElement("span"),value=document.createElement("b"),detail=document.createElement("p");title.textContent="Conta sintética "+val(a.account_id)+" · "+val(a.currency);value.textContent=val(a.equity);detail.textContent="Disponível "+val(a.capital_available)+" · Reserva "+val(a.capital_reserved)+" · PnL "+val(a.realized_pnl)+" · Drawdown "+val(a.drawdown)+" · Estado "+val(a.status||a.risk_status);c.append(title,value,detail);cards.append(c);}if(!cards.children.length)cards.textContent="Nenhuma conta sintética persistida; patrimônio real indisponível.";
 el("freshness").textContent="Consulta local concluída em "+new Date().toLocaleString("pt-BR")+" · não comprova atualização de mercado.";

 const d=data.reconciliation||{},st=d.statuses||{},labels=["Tentativas auditadas","Operações distintas","Assinaturas distintas","Transações pendentes"],nums=[d.total_attempts,d.distinct_operations,d.distinct_signatures,d.pending_transactions_count],m=el("metrics");m.replaceChildren();
 nums.forEach((n,i)=>{const box=document.createElement("div"),l=document.createElement("span"),b=document.createElement("b");box.className="metric";l.className="muted";l.textContent=labels[i];b.textContent=val(n);box.append(l,b);m.append(box);});
 const s=el("statuses");s.replaceChildren();Object.entries(st).forEach(([k,n])=>{const box=document.createElement("div"),l=document.createElement("span"),b=document.createElement("b");box.className="metric";l.className="muted";l.textContent=k;b.textContent=val(n);b.className=k==="MATCHED"?"good":k==="INCOMPLETE"?"warn":"bad";box.append(l,b);s.append(box);});
 const collectors=el("radarCollectors");collectors.replaceChildren();
 Object.entries(data.radars||{}).forEach(([name,state])=>{
   const box=document.createElement("div"),title=document.createElement("b"),detail=document.createElement("p");
   box.className="metric";title.textContent=name==="launch"?"Launch Radar":"Smart Money Radar";
   detail.className="muted";detail.textContent="Coletor: "+val(state.status)+" · Cobertura: "+val(state.evidence_coverage)+" · Último arquivo: "+val(state.last_archived_event_at);
   const offline=state.offline_supervisor||{},progress=document.createElement("p");
   progress.className="muted";progress.textContent="Supervisor offline: "+val(offline.lease_status)+" · Tarefa: "+val(offline.task_status)+" · Ciclos persistidos: "+val(offline.cycles)+" · Última atividade local: "+val(offline.last_activity);
   box.append(title,detail,progress);collectors.append(box);
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
 const opportunities=data.radar_opportunities||{};
 [["launch","launchOpportunities"],["smart_money","smartOpportunities"]].forEach(([radar,id])=>{
  const panel=el(id);panel.replaceChildren();const items=opportunities[radar]||[];
  if(!items.length){panel.textContent="Nenhuma análise disponível.";return;}
  const table=document.createElement("table"),head=document.createElement("thead"),tr=document.createElement("tr");
  ["Evento / data","Classificação / score","Confiança / risco","Evidências / motivos"].forEach(h=>{const th=document.createElement("th");th.textContent=h;tr.append(th);});head.append(tr);table.append(head);const body=document.createElement("tbody");
  items.forEach(x=>{const r=document.createElement("tr");td(r,short(x.event_id)+" · "+(x.event_available_at||"UNKNOWN"));td(r,(x.verdict||"UNKNOWN")+" · "+(x.score??"UNKNOWN"));td(r,(x.confidence||"UNKNOWN")+" · "+(x.risk_status||"UNKNOWN"));td(r,(x.evidence_ids||[]).join(", ")+" · "+(x.reasons||[]).join(", "));body.append(r);});table.append(body);panel.append(table);
 });
 const synthetic=data.synthetic_paper||{};
 [["launch","launchSynthetic"],["smart_money","smartSynthetic"]].forEach(([radar,id])=>{
  const panel=el(id);panel.replaceChildren();const items=synthetic[radar]||[];
  if(!items.length){panel.textContent="Nenhuma simulação sintética registrada.";return;}
  items.forEach(x=>{const item=document.createElement("div"),r=x.report;item.textContent=!r?x.run_id+" · CONFLICTED":x.run_id+" · "+x.strategy+" · "+x.pool+" · Capital "+r.initial_cash+" · Saldo "+r.cash+" · Quantidade aberta "+r.open_quantity+" · PnL realizado "+r.realized_pnl+" · PnL não realizado "+r.unrealized_pnl+" · Taxas "+r.total_fees+" · Rejeições "+r.rejected_entries+" · "+r.risk_status;panel.append(item);if(r){(r.fills||[]).forEach(f=>{const line=document.createElement("p");line.textContent=f.side+" · "+f.quantity+" @ "+f.price+" · taxa "+f.fee+" · "+f.reason+" · "+f.filled_at;panel.append(line);});(r.risk_evaluations||[]).filter(k=>k.reasons.length).forEach(k=>{const line=document.createElement("p");line.textContent=k.quote_id+" · "+k.reasons.join(", ");panel.append(line);});}});
 });
 const accounts=el("capitalAccounts");accounts.replaceChildren();
 (data.capital_accounts||[]).forEach(x=>{const line=document.createElement("p");line.textContent=x.account_id+" · "+(x.status||x.risk_status)+" · "+(x.currency||"")+" · Disponível "+(x.capital_available||"?")+" · Reservado "+(x.capital_reserved||"?")+" · Equity "+(x.equity||"?")+" · Drawdown "+(x.drawdown||"?")+" · PnL "+(x.realized_pnl||"?");accounts.append(line);if(x.risk_limits){const p=document.createElement("p");p.textContent="Limites auditados: "+Object.entries(x.risk_limits).map(([k,v])=>k+"="+v).join(" · ");accounts.append(p);}if(x.future_run_config){const cfg=document.createElement("p");cfg.textContent="Somente novas alocações · limite por entrada "+val(x.future_run_config.max_entry_cash)+" · stop-loss "+val(x.future_run_config.stop_loss)+" · take-profit "+val(x.future_run_config.take_profit);accounts.append(cfg);}});if(!accounts.children.length)accounts.textContent="Nenhuma conta sintética multipool.";
 const op=data.operational_controls||{},ops=el("operationalState"),alerts=el("operationalAlerts");ops.textContent="Launch: "+((op.radars||{}).launch||"UNKNOWN")+" · Smart Money: "+((op.radars||{}).smart_money||"UNKNOWN")+" · Entradas: "+(op.entries_paused?"PAUSADAS":"habilitadas apenas sinteticamente")+" · Emergência: "+(op.emergency_halt?"ATIVA":"inativa")+" · Live: BLOQUEADO";alerts.replaceChildren();(op.alerts||[]).forEach(a=>{const line=document.createElement("p");line.textContent=a.at+" · "+a.action+" · "+(a.radar||"global")+" · "+a.reason;alerts.append(line);});
 const walletPanel=el("walletDiscovery");walletPanel.replaceChildren();
 (data.wallet_discovery||[]).forEach(s=>{const head=document.createElement("p");head.textContent=(s.status||s.coverage||"UNKNOWN")+" · "+(s.as_of||"")+" · Qualificadas "+(s.qualified_count??"UNKNOWN");walletPanel.append(head);(s.profiles||[]).forEach(w=>{const line=document.createElement("p");line.textContent=w.wallet+" · "+w.status+" · Score local "+(w.score??"UNKNOWN")+" · Confiança "+w.confidence+" · "+w.local_distinct_transactions+" transações locais · "+(w.reasons||[]).join(", ")+" · "+(w.indicators||[]).join(", ");walletPanel.append(line);});});
 if(!walletPanel.children.length)walletPanel.textContent="Nenhum snapshot de descoberta publicado.";
 const sup=data.supervisor||{},supPanel=el("supervisorStatus"),supAlerts=el("supervisorAlerts");supPanel.replaceChildren();supAlerts.replaceChildren();const supHeader=document.createElement("p");supHeader.textContent=(sup.status||"NOT_STARTED")+" · geração "+(sup.generation??"-")+" · heartbeat "+(sup.last_heartbeat||"-");supPanel.append(supHeader);
 const hist=data.supervisor_history||{},historyPanel=el("supervisorHistory");historyPanel.replaceChildren();
 const summary=document.createElement("p");
 summary.textContent="Watchdog local · integridade "+val(hist.integrity)+" · disponibilidade "+val(hist.availability)+" · dados "+val(hist.freshness)+" · expiração "+val(hist.expires_at)+" · expirações registradas "+val(hist.restart_events)+" · recuperações após expiração "+val(hist.recovery_count)+" · estado "+val(hist.watchdog_state);
 historyPanel.append(summary);
 if(hist.integrity==="VERIFIED_LOCAL"){
  for(const entry of hist.recovery_history||[]){
   const line=document.createElement("p");
   line.textContent="Ciclo · "+val(entry.kind)+" · "+val(entry.at)+" · geração "+val(entry.generation);
   historyPanel.append(line);
  }
 }
 if(hist.integrity==="VERIFIED_LOCAL"){
  for(const entry of hist.watchdog_history||[]){
   const line=document.createElement("p");
   line.textContent=val(entry.at)+" · "+val(entry.radar)+" · "+val(entry.kind)+" · "+val(entry.identity);
   historyPanel.append(line);
  }
 }else{
  const warning=document.createElement("p");warning.textContent="Histórico indisponível: integridade não verificada.";historyPanel.append(warning);
 }
 Object.entries(sup.radars||{}).forEach(([r,t])=>{const p=document.createElement("p");p.textContent=r+" · "+t.status+" · checkpoint "+(t.checkpoint||"-")+" · conexão "+t.connection+" · falhas "+t.failures+" · última atividade "+(t.last_activity||"-");supPanel.append(p);});(sup.alerts||[]).forEach(a=>{const p=document.createElement("p");p.textContent=a.at+" · "+a.radar+" · "+a.kind;supAlerts.append(p);});
 const events=el("events");events.replaceChildren();(data.recent_events||[]).forEach(x=>{const tr=document.createElement("tr");td(tr,x.occurred_at);td(tr,short(x.wallet_address));td(tr,short(x.token_mint));td(tr,x.direction);td(tr,x.amount);events.append(tr);});if(!events.children.length)rowEmpty(events,5,"Nenhum evento persistido.");
}
function unavailable(){lastOverview=null;for(const id of ["equityCards","equityHistory","filteredPositions","capitalAccounts","launchSynthetic","smartSynthetic","launchOpportunities","smartOpportunities","walletDiscovery","events","attempts","metrics","statuses","radarCollectors","launchEvents","smartEvents","operationalState","operationalAlerts","supervisorStatus","supervisorAlerts","reasons"]){const node=el(id);if(node)node.replaceChildren();}el("freshness").textContent="Dados indisponíveis · nenhum resultado atual confirmado.";}
async function refresh(){
 if(busy)return;busy=true;el("connect").disabled=true;el("refresh").disabled=true;el("loadAttempts").disabled=true;
 el("message").textContent="Verificando autenticação no servidor local…";
 let authenticated=false;
 try{
  const health=await api("/health");
  if(health.status!=="ok"||health.mode!=="read_only")throw Error("Resposta de saúde inesperada.");
  authenticated=true;el("message").textContent="Autenticação aprovada · consultando banco…";
  const data=await api("/api/v1/dashboard");
  try{render(data);}catch(e){throw Error("Falha de apresentação dos dados.");}
  el("message").textContent="Conexão aprovada · dados atualizados · somente leitura";
 }catch(e){unavailable();el("message").textContent=(authenticated&&token?"Autenticação aprovada, mas consulta falhou: ":"")+e.message;}
 finally{busy=false;el("connect").disabled=false;el("refresh").disabled=!token;el("loadAttempts").disabled=!token;}
}
async function attempts(){el("message").textContent="Consultando auditoria…";try{const q=new URLSearchParams({limit:"100"});if(el("statusFilter").value)q.set("status",el("statusFilter").value);const data=await api("/api/v1/reconciliation/attempts?"+q),body=el("attempts");body.replaceChildren();(data.items||[]).forEach(x=>{const tr=document.createElement("tr"),s=td(tr,x.attempted_at),status=td(tr,x.status);status.className=x.status==="MATCHED"?"good":x.status==="INCOMPLETE"?"warn":"bad";td(tr,short(x.operation_id));td(tr,x.instruction_index);td(tr,x.reason);body.append(tr);});if(!body.children.length)rowEmpty(body,5,"Nenhuma tentativa encontrada.");el("message").textContent="Auditoria atualizada.";}catch(e){el("message").textContent=e.message;}}
el("connect").addEventListener("click",async()=>{if(busy)return;token=el("token").value.trim();el("token").value="";if(token.length<32||!(/^[!-~]+$/).test(token)){token="";unavailable();el("message").textContent="Token inválido: cole somente o código completo, sem espaços internos.";el("refresh").disabled=true;el("loadAttempts").disabled=true;return;}await refresh();});
el("token").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();el("connect").click();}});
for(const id of ["filterRadar","filterStrategy","filterSince","filterUntil"])el(id).addEventListener("change",()=>{if(lastOverview)renderScoped(lastOverview);});
el("refresh").addEventListener("click",refresh);el("loadAttempts").addEventListener("click",attempts);
el("message").textContent="Interface pronta. Cole o token temporário e toque em Conectar. · revisão Android 1";
if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/smr-sw.js",{updateViaCache:"none"}).catch(()=>{});
</script></body></html>"""


# Only fixed public shell assets are available without the bearer token.
_PWA_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="104" fill="#0b1018"/><g fill="none" stroke="#27d5ab" stroke-width="16"><circle cx="256" cy="256" r="170"/><circle cx="256" cy="256" r="110"/><circle cx="256" cy="256" r="48"/><path d="M256 256 389 146M86 256h340M256 86v340" opacity=".6"/></g><circle cx="389" cy="146" r="26" fill="#54edc7"/><circle cx="256" cy="256" r="13" fill="#fff"/></svg>"""
_PWA_MANIFEST = json.dumps({"name":"SMART MONEY RADAR","short_name":"SMR","id":"/dashboard","start_url":"/dashboard","scope":"/","display":"standalone","lang":"pt-BR","theme_color":"#0b1018","background_color":"#0b1018","icons":[{"src":"/smr-icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any"}]},ensure_ascii=False)
# No caching, no background sync, no authenticated request interception.
# Installing this worker does not make market/account data available offline.
_PWA_WORKER = """self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));"""
_PUBLIC_PWA = {"/manifest.webmanifest":("application/manifest+json",_PWA_MANIFEST),"/smr-icon.svg":("image/svg+xml",_PWA_ICON),"/smr-sw.js":("application/javascript",_PWA_WORKER)}

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
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; manifest-src 'self'; worker-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
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
        if len(self.headers.get_all("Authorization") or []) != 1 or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            self._send_json(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/dashboard"):
            self._send_html()
            return
        if parsed.path in _PUBLIC_PWA and not parsed.query:
            mime, content = _PUBLIC_PWA[parsed.path]
            body=content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",mime+"; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            self.wfile.write(body)
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
