const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
let allModels = [];
let currentModel = null;
let parameterDefs = [];
let currentMtpCapability = { status: 'unknown', evidence: [] };
let currentModelLimits = {};
let currentDetails = {};
let currentThinkingDetected = null;
let liveTimer = null;
let managerStatus = null;
let hardwareRequestActive = false;
let hardwareLoadedOnce = false;

const views = {
  dashboard: { el: '#dashboardView', title: 'Dashboard', sub: 'Monitor usage and your active Ollama runtime.' },
  models: { el: '#modelsView', title: 'Models', sub: 'Manage installed models, MTP, and persistent model-level parameter overrides.' }
};

function toast(message, type='success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toastWrap').appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

function formatBytes(bytes=0) {
  if (!bytes) return '0 B';
  const units = ['B','KB','MB','GB','TB'];
  const i = Math.min(Math.floor(Math.log(bytes)/Math.log(1024)), units.length-1);
  return `${(bytes/Math.pow(1024,i)).toFixed(i>2?1:0)} ${units[i]}`;
}
function fmt(n=0){ return new Intl.NumberFormat().format(Math.round(n)); }
function formatDuration(ms){ return ms == null ? '—' : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms/1000).toFixed(2)} s`; }
function ago(iso){ if(!iso) return '—'; const d=(Date.now()-new Date(iso).getTime())/1000; if(d<60)return `${Math.max(0,Math.round(d))}s ago`; if(d<3600)return `${Math.round(d/60)}m ago`; if(d<86400)return `${Math.round(d/3600)}h ago`; return `${Math.round(d/86400)}d ago`; }
function tps(v){ return v == null ? '—' : `${Number(v).toFixed(1)} tok/s`; }

async function api(url, options={}) {
  const r = await fetch(url, options);
  let data = {};
  try { data = await r.json(); } catch (_) {}
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}

function switchView(name) {
  Object.values(views).forEach(v => $(v.el).classList.remove('active'));
  $$('.nav-item[data-view]').forEach(n => n.classList.toggle('active', n.dataset.view === name));
  $(views[name].el).classList.add('active');
  $('#pageTitle').textContent = views[name].title;
  $('#pageSub').textContent = views[name].sub;
  if (name === 'dashboard') { loadDashboard(); loadLive(); }
  if (name === 'models') loadModels();
}

async function loadStatus(){
  try{
    const d=await api('/api/manager/status');
    managerStatus=d;
    $('#statusDot').classList.toggle('online', d.online);
    $('#serverState').textContent = d.online ? 'Ollama online' : 'Ollama offline';
    $('#serverVersion').textContent = d.version ? `v${d.version}` : d.url;
    const proxy = new URL(location.origin);
    proxy.port = String(d.proxy_port || 11435);
    proxy.pathname = '';
    proxy.search = '';
    proxy.hash = '';
    $('#proxyUrl').textContent = proxy.origin;
    updateNativeMtpStatus();
  }catch(e){ managerStatus=null; $('#serverState').textContent='Ollama unavailable'; $('#serverVersion').textContent=e.message; updateNativeMtpStatus(); }
}

function updateNativeMtpStatus(){
  const el=$('#mtpNativeStatus'); if(!el)return;
  const native=managerStatus?.mtp_native;
  const ok=Boolean(managerStatus?.online&&native?.verified);
  el.classList.toggle('verified',ok); el.classList.toggle('unverified',!ok);
  $('b',el).textContent=ok ? `Native per-model MTP verified · Ollama v${managerStatus.version}` : 'Native per-model MTP not verified';
  $('small',el).textContent=ok ? 'Ollama will auto-select draft-mtp only when the GGUF contains MTP/NextN layers.' : (native?.summary || 'Use Ollama 0.32.14 or newer for the model-aware MTP behaviour this UI expects.');
}

async function loadHardware({silent=false}={}){
  if(hardwareRequestActive)return;
  hardwareRequestActive=true;
  const panel=$('.hardware-panel'), source=$('#hardwareSource');
  panel?.classList.remove('is-error');
  // Do not replace live values with "Detecting…" on every poll; that caused
  // the card to reflow on mobile. Only show it on the very first request.
  if(!silent&&!hardwareLoadedOnce&&source)source.textContent='Detecting…';
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),6500);
  try{
    const d=await api('/api/hardware',{signal:controller.signal,cache:'no-store'}), sys=d.system||{}, gpu=d.gpu||{};
    const ramTotal=Number(sys.total_bytes||0), ramUsed=Number(sys.used_bytes||0), ramPct=ramTotal?Math.min(100,ramUsed/ramTotal*100):0;
    $('#ramUsageText').textContent=ramTotal?`${formatBytes(ramUsed)} / ${formatBytes(ramTotal)}`:'Unavailable';
    $('#ramUsageBar').style.width=`${ramPct}%`;
    $('#ramUsageSub').textContent=ramTotal?`${formatBytes(sys.available_bytes||0)} available · ${sys.source||'auto-detected'}`:'Host RAM unavailable';

    const gpuTotal=Number(gpu.total_bytes||0), gpuUsed=Number(gpu.used_bytes||0), gpuPct=gpuTotal?Math.min(100,gpuUsed/gpuTotal*100):0;
    $('#gpuUsageText').textContent=gpuTotal?`${formatBytes(gpuUsed)} / ${formatBytes(gpuTotal)}`:(gpuUsed?`${formatBytes(gpuUsed)} used`:'Total VRAM unavailable');
    $('#gpuUsageBar').style.width=`${gpuPct}%`;
    const devices=gpu.devices||[];
    const names=devices.map(x=>x.name).filter(Boolean).join(' + ');
    const hasLive=devices.some(x=>x.used_bytes!=null);
    const dev=devices[0]||{};
    const util=Number.isFinite(Number(dev.utilization))?`${Number(dev.utilization).toFixed(0)}% GPU`:null;
    const temp=Number.isFinite(Number(dev.temperature_c))?`${Number(dev.temperature_c).toFixed(0)}°C`:null;
    const power=Number.isFinite(Number(dev.power_w))?`${Number(dev.power_w).toFixed(0)} W`:null;
    const liveBits=[util,temp,power].filter(Boolean).join(' · ');
    if(gpuTotal){
      $('#gpuUsageSub').textContent=hasLive?`${names||'GPU'} · ${liveBits||'live telemetry'} · ${gpu.source||'auto'}`:`${names||'GPU'} · ${formatBytes(gpu.ollama_used_bytes||0)} Ollama residency · ${gpu.source||'host snapshot'}`;
    }else{
      const seed=d.diagnostics?.hardware_seed_loaded?'snapshot contains no GPU total':'host snapshot missing';
      $('#gpuUsageSub').textContent=`${formatBytes(gpu.ollama_used_bytes||0)} Ollama residency · ${seed} · run make preflight`;
    }
    $('#hardwareLoadedModels').textContent=(d.loaded_models||[]).length;
    $('#hardwareModelVram').textContent=`${formatBytes(gpu.ollama_used_bytes||0)} Ollama VRAM`;
    $('#hardwareCpu').textContent=sys.cpu_count?`${sys.cpu_count}`:'—';
    const sourceText=gpuTotal&&ramTotal?'Detected':ramTotal?'RAM only':'Partial';
    source.textContent=sourceText;
    source.title=`RAM: ${sys.source||'unknown'} · GPU: ${gpu.source||'unknown'}`;
    hardwareLoadedOnce=true;
  }catch(e){
    // During background polling keep the last good values instead of making the
    // panel jump between success/error layouts for a transient timeout.
    if(!silent||!hardwareLoadedOnce){
      panel?.classList.add('is-error'); source.textContent='Unavailable';
      $('#gpuUsageText').textContent='Unavailable'; $('#gpuUsageBar').style.width='0%';
      $('#ramUsageText').textContent='Unavailable'; $('#ramUsageBar').style.width='0%';
      const msg=e?.name==='AbortError'?'Hardware request timed out':(e?.message||'Hardware request failed');
      $('#gpuUsageSub').textContent=`${msg}. Tap refresh to retry.`;
      $('#ramUsageSub').textContent='Run make preflight on the Docker host to refresh detection.';
      $('#hardwareLoadedModels').textContent='—'; $('#hardwareModelVram').textContent='Ollama runtime unavailable'; $('#hardwareCpu').textContent='—';
    }
  }finally{clearTimeout(timer);hardwareRequestActive=false}
}

async function loadDashboard(){
  loadStatus();
  loadHardware();
  try{
    const d=await api('/api/manager/dashboard');
    $('#statRequests').textContent=fmt(d.summary.requests);
    $('#statTokens').textContent=fmt(d.summary.output_tokens);
    $('#statPromptTokens').textContent=`${fmt(d.summary.prompt_tokens)} prompt tokens`;
    $('#statLatency').textContent=formatDuration(d.summary.avg_latency_ms);
    $('#statTps').textContent=d.summary.tokens_per_second ? d.summary.tokens_per_second.toFixed(1) : '—';
    renderChart(d.timeline || []);
    renderUsage(d.by_model || []);
    renderRunning(d.running || []);
    renderRecent(d.recent || []);
  }catch(e){ toast(e.message,'error'); }
}

async function loadLive(){
  if (!$('#dashboardView').classList.contains('active')) return;
  try {
    const d = await api('/api/manager/live');
    const proxyState=$('#proxyState');
    if(proxyState){ proxyState.textContent=d.proxy_online?'● Telemetry proxy online':'● Telemetry proxy unavailable'; proxyState.classList.toggle('proxy-online',Boolean(d.proxy_online)); }
    renderLive(d.active || [], d.recent || []);
  } catch (e) {
    const el = $('#liveGenerations');
    el.className = 'live-generations empty-state';
    const proxyState=$('#proxyState'); if(proxyState){proxyState.textContent='● Telemetry proxy unavailable';proxyState.classList.remove('proxy-online');}
    el.textContent = `Live telemetry unavailable: ${e.message}`;
  }
}

async function clearDashboardData(){
  const button=$('#confirmClearTelemetry');
  if(!button)return;
  button.disabled=true;
  button.textContent='Clearing…';
  try{
    const result=await api('/api/manager/telemetry',{method:'DELETE'});
    closeModal('clearTelemetryModal');
    await Promise.all([loadDashboard(),loadLive()]);
    const suffix=result.proxy_recent_cleared?'':' · completed proxy summaries will expire shortly';
    toast(`Cleared ${fmt(result.deleted_requests||0)} dashboard request${Number(result.deleted_requests)===1?'':'s'}${suffix}`);
  }catch(e){toast(e.message,'error')}
  finally{button.disabled=false;button.textContent='Clear dashboard data'}
}

function renderLive(active, recent){
  const el = $('#liveGenerations');
  if (!active.length && !recent.length) {
    el.className='live-generations empty-state';
    el.textContent='No active generation. Point clients at the Ollama-compatible proxy on port 11435 and use normal /api/chat, /api/generate, or supported /v1 generation paths.';
    return;
  }
  el.className='live-generations';
  const activeHtml = active.map(r => {
    const phase = r.phase === 'starting' ? 'Loading / prompt eval' : 'Generating';
    const mtp = r.mtp_enabled ? `<span class="tiny-pill mtp-on">MTP · depth ${fmt(r.mtp_draft_n_max)}</span>` : '<span class="tiny-pill">MTP off</span>';
    return `<div class="live-row active-live">
      <div class="live-model"><span class="pulse-dot"></span><div><b>${escapeHtml(r.model||'unknown')}</b><span>${escapeHtml(r.endpoint||'')} · ${escapeHtml(phase)}</span></div></div>
      <div class="live-metric"><small>Elapsed</small><strong>${formatDuration(r.elapsed_ms)}</strong></div>
      <div class="live-metric"><small>~ tokens</small><strong>${fmt(r.estimated_tokens||0)}</strong></div>
      <div class="live-metric"><small>Current rate</small><strong>${tps(r.estimated_current_tps)}</strong></div>
      <div class="live-metric"><small>Avg rate</small><strong>${tps(r.estimated_tps)}</strong></div>
      <div class="live-mtp">${mtp}<small>stream estimate</small></div>
    </div>`;
  }).join('');
  const recentHtml = recent.slice(0,3).map(r => {
    const mtp = r.mtp_enabled ? `<span class="tiny-pill mtp-on">MTP · depth ${fmt(r.mtp_draft_n_max)}</span>` : '<span class="tiny-pill">MTP off</span>';
    return `<div class="live-row completed-live">
      <div class="live-model"><span class="done-dot">✓</span><div><b>${escapeHtml(r.model||'unknown')}</b><span>Finished ${ago(r.finished_at)} · HTTP ${r.status_code ?? '—'}</span></div></div>
      <div class="live-metric"><small>Prompt</small><strong>${fmt(r.prompt_tokens||0)}</strong></div>
      <div class="live-metric"><small>Generated</small><strong>${fmt(r.output_tokens||0)}</strong></div>
      <div class="live-metric exact"><small>Exact rate</small><strong>${tps(r.exact_tps)}</strong></div>
      <div class="live-metric"><small>Total</small><strong>${formatDuration(r.elapsed_ms)}</strong></div>
      <div class="live-mtp">${mtp}<small>final Ollama metrics</small></div>
    </div>`;
  }).join('');
  el.innerHTML = `${activeHtml}${recentHtml}`;
}

function renderChart(points){
  const c=$('#requestsChart'); const rect=c.getBoundingClientRect();
  c.width=Math.max(520,Math.floor(rect.width*devicePixelRatio)); c.height=210*devicePixelRatio;
  const ctx=c.getContext('2d'); ctx.scale(devicePixelRatio,devicePixelRatio);
  const W=c.width/devicePixelRatio,H=210,p={l:28,r:10,t:12,b:24};
  ctx.clearRect(0,0,W,H); ctx.strokeStyle='#252c35'; ctx.lineWidth=1; ctx.fillStyle='#77818e'; ctx.font='9px system-ui';
  const max=Math.max(1,...points.map(x=>x.requests));
  for(let i=0;i<4;i++){ const y=p.t+(H-p.t-p.b)*i/3; ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke(); const v=Math.round(max*(1-i/3));ctx.fillText(String(v),2,y+3); }
  if(!points.length)return;
  const xStep=(W-p.l-p.r)/Math.max(1,points.length-1), yBase=H-p.b;
  ctx.beginPath(); points.forEach((pt,i)=>{const x=p.l+i*xStep,y=yBase-(pt.requests/max)*(yBase-p.t); i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
  ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()||'#78a9ff';ctx.lineWidth=2;ctx.stroke();
  const accentRgb=getComputedStyle(document.documentElement).getPropertyValue('--accent-rgb').trim()||'120,169,255';
  ctx.lineTo(p.l+(points.length-1)*xStep,yBase);ctx.lineTo(p.l,yBase);ctx.closePath();ctx.fillStyle=`rgba(${accentRgb},.08)`;ctx.fill();
  const labels=[0,6,12,18,points.length-1].filter((v,i,a)=>v<points.length&&a.indexOf(v)===i); ctx.fillStyle='#77818e';
  labels.forEach(i=>{const x=p.l+i*xStep;ctx.fillText(points[i].label,x-12,H-6);});
}
function renderUsage(rows){
  const el=$('#modelUsage'); if(!rows.length){el.className='usage-list empty-state';el.textContent='No proxied requests yet.';return;} el.className='usage-list';
  const max=Math.max(...rows.map(x=>x.requests),1);
  el.innerHTML=rows.map(r=>`<div class="usage-row"><div><b>${escapeHtml(r.model||'unknown')}</b><span>${fmt(r.output_tokens)} generated · ${fmt(r.prompt_tokens)} prompt tokens</span><div class="usage-bar"><i style="width:${Math.max(3,r.requests/max*100)}%"></i></div></div><div class="usage-val">${fmt(r.requests)} req</div></div>`).join('');
}
function renderRunning(rows){
  const el=$('#runningModels'); if(!rows.length){el.className='running-list empty-state';el.textContent='Nothing loaded.';return;} el.className='running-list';
  el.innerHTML=rows.map(r=>`<div class="running-row"><div><b>${escapeHtml(r.name||r.model)}</b><span>${formatBytes(r.size_vram||r.size)} in VRAM · ${r.context_length?fmt(r.context_length)+' ctx · ':''}expires ${r.expires_at?ago(r.expires_at):'—'}</span></div><div class="running-meta"><span class="tiny-pill">${escapeHtml(r.details?.quantization_level||'loaded')}</span><button class="btn ghost unload-running" data-name="${escapeAttr(r.name||r.model)}">Unload</button></div></div>`).join('');$$('.unload-running',el).forEach(b=>b.onclick=()=>setRuntime(b.dataset.name,true));
}
function renderRecent(rows){
  const el=$('#recentRequests'); if(!rows.length){el.className='request-list empty-state';el.textContent='No request history.';return;} el.className='request-list';
  el.innerHTML=rows.map(r=>`<div class="request-row" data-id="${r.id}"><div><b>${escapeHtml(r.model||'unknown')} · ${escapeHtml(r.endpoint)}</b><span>${ago(r.created_at)} · ${formatDuration(r.latency_ms)} · ${fmt(r.output_tokens)} tokens${r.client_name?` · <span class="client-pill">${escapeHtml(r.client_name)}</span>`:''}</span></div><div class="status-code">${r.status_code}</div></div>`).join('');
  $$('.request-row',el).forEach(row=>row.onclick=()=>openRequestInspector(row.dataset.id));
}
async function openRequestInspector(id){
  try{const d=await api(`/api/manager/request/${id}`);$('#requestTitle').textContent=`${d.model||'unknown'} · ${d.endpoint}`;$('#requestSubtitle').textContent=`${new Date(d.created_at).toLocaleString()} · HTTP ${d.status_code}`;const meta=d.request_meta||{}, options=meta.options||{};const item=(k,v,wide=false)=>`<div class="request-detail ${wide?'wide':''}"><span>${escapeHtml(k)}</span><b>${v==null||v===''?'—':escapeHtml(String(v))}</b></div>`;$('#requestDetails').innerHTML=item('Client',d.client_name||meta.client_name||'Unknown')+item('Client IP',d.client_ip)+item('Latency',formatDuration(d.latency_ms))+item('Generation rate',d.tokens_per_second?`${Number(d.tokens_per_second).toFixed(1)} tok/s`:'—')+item('Prompt tokens',fmt(d.prompt_tokens||0))+item('Generated tokens',fmt(d.output_tokens||0))+item('Thinking',meta.think)+item('Tools',meta.tools_count||0)+item('Keep alive',meta.keep_alive)+item('Stream',meta.stream)+item('Request options',Object.keys(options).length?JSON.stringify(options,null,2):'No per-request options',true)+item('Privacy','Prompt/response bodies are not stored by request telemetry.',true);openModal('requestModal')}catch(e){toast(e.message,'error')}
}

async function loadModels(){
  try{
    const [d,runtime]=await Promise.all([api('/api/models'),api('/api/manager/runtime').catch(()=>({models:[]}))]);
    allModels=d.models||[]; loadedModels=new Set((runtime.models||[]).map(m=>m.name||m.model)); $('#modelCount').textContent=allModels.length; renderModels();
  }catch(e){ $('#modelsGrid').innerHTML=`<div class="loading">${escapeHtml(e.message)}</div>`; }
}
function renderModels(){
  const q=$('#modelSearch').value.trim().toLowerCase(); const rows=allModels.filter(m=>(m.name||m.model||'').toLowerCase().includes(q));
  $('#modelsGrid').innerHTML=rows.length?rows.map(m=>{const d=m.details||{},name=m.name||m.model,isLoaded=loadedModels.has(name);return `<article class="model-card ${isLoaded?'is-loaded':''}"><div class="model-card-head"><a class="model-icon-link" href="/model/${encodeURIComponent(name)}">${window.OllamaBrand?OllamaBrand.html(name,'ollama',true):'<div class="model-icon">◈</div>'}</a><div class="model-actions"><button class="icon-btn runtime-model ${isLoaded?'loaded':''}" data-name="${escapeAttr(name)}" data-loaded="${isLoaded?'1':'0'}" title="${isLoaded?'Unload model from memory':'Load model into memory'}">${isLoaded?'■':'▶'}</button><button class="icon-btn edit-model" data-name="${escapeAttr(name)}" title="Edit model parameters and MTP">⚙</button><button class="icon-btn danger delete-model" data-name="${escapeAttr(name)}" title="Delete model">⌫</button></div></div><h3 title="${escapeAttr(name)}"><a class="model-title-link" href="/model/${encodeURIComponent(name)}">${escapeHtml(name)}</a></h3><div class="hash">${escapeHtml((m.digest||'').slice(0,18))}${m.digest?'…':''}</div><div class="model-details"><span>${escapeHtml(d.parameter_size||'unknown size')}</span><span>${escapeHtml(d.quantization_level||'unknown quant')}</span><span>${escapeHtml(d.family||'model')}</span>${isLoaded?'<span class="loaded-pill">Loaded</span>':''}</div><div class="model-foot"><span>${formatBytes(m.size)}</span><span>${ago(m.modified_at)}</span></div></article>`}).join(''):'<div class="loading">No installed models match your search.</div>';
  $$('.runtime-model').forEach(b=>b.onclick=()=>setRuntime(b.dataset.name,b.dataset.loaded==='1'));
  $$('.edit-model').forEach(b=>b.onclick=()=>openEditor(b.dataset.name));
  $$('.delete-model').forEach(b=>b.onclick=()=>deleteModel(b.dataset.name));
}
async function setRuntime(name,isLoaded){
  const action=isLoaded?'unload':'load';
  try{toast(`${action==='load'?'Loading':'Unloading'} ${name}…`);await api('/api/manager/runtime',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:name,action})});toast(`${name} ${action==='load'?'loaded':'unloaded'}`);await loadModels();await loadDashboard();}catch(e){toast(e.message,'error')}
}

async function deleteModel(name){
  if(!confirm(`Delete ${name}? This removes the local Ollama model.`))return;
  try{ await api(`/api/delete-model?name=${encodeURIComponent(name)}`,{method:'DELETE'}); toast(`${name} deleted`); await loadModels(); }catch(e){toast(e.message,'error');}
}

function openModal(id){ $('#'+id).classList.add('open'); }
function closeModal(id){ $('#'+id).classList.remove('open'); }

async function startPull(){
  const name=$('#pullModelName').value.trim(); if(!name)return toast('Enter a model name','error');
  $('#pullProgressWrap').classList.remove('hidden'); $('#startPullBtn').disabled=true; $('#pullProgress').style.width='2%'; $('#pullStatus').textContent='Adding to download queue…'; $('#pullPercent').textContent='';
  try{
    const queued=await api('/api/downloads/ollama',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:name})});
    const jobId=queued.job_id;
    while(true){
      await new Promise(r=>setTimeout(r,700));
      const d=await api('/api/downloads'); const job=(d.jobs||[]).find(j=>j.id===jobId);
      if(!job)throw new Error('Download job disappeared');
      const pct=job.total?Math.min(100,(job.completed||0)/job.total*100):(job.done&&job.success?100:5);
      $('#pullProgress').style.width=`${pct}%`; $('#pullPercent').textContent=`${pct.toFixed(0)}%`; $('#pullStatus').textContent=job.status||job.phase||'Queued';
      if(job.done){if(!job.success)throw new Error(job.error||'Pull failed');break;}
    }
    toast(`${name} pulled successfully`); setTimeout(()=>closeModal('pullModal'),700); await loadModels();
  }catch(e){toast(e.message,'error');$('#pullStatus').textContent=e.message;}finally{$('#startPullBtn').disabled=false;}
}

async function openEditor(name){
  currentModel=name;
  currentMtpCapability={status:'unknown',evidence:[]};
  currentModelLimits={};
  currentDetails={};
  currentThinkingDetected=null;
  setReasoningUi(null,{enabled:false},true);
  $('#editorModelName').textContent=name;
  $('#targetModelName').value=name;
  $('#editorMeta').textContent='Loading model details…';
  $('#parameterGroups').innerHTML='<div class="loading">Loading parameters…</div>';
  setMtpUi({status:'unknown',summary:'Inspecting verbose Ollama model metadata and tensor names.',evidence:[]},{mtp_enabled:false,mtp_draft_n_max:2,source:'default'},true);
  openModal('editorModal');
  try{
    const [info, defs] = await Promise.all([
      api('/api/manager/model-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:name})}),
      parameterDefs.length?Promise.resolve({parameters:parameterDefs}):api('/api/manager/parameters')
    ]);
    parameterDefs=defs.parameters||defs;
    const details=info.details||{};
    currentDetails=details;
    currentModelLimits=info.model_limits||{};
    $('#editorMeta').textContent=[details.parameter_size,details.quantization_level,details.family].filter(Boolean).join(' · ') || 'Installed Ollama model';
    const values=info.parsed_parameters||{};
    const ctxVal=Array.isArray(values.num_ctx)?values.num_ctx[0]:values.num_ctx;
    $('#ctxEnabled').checked=ctxVal!==undefined;
    applyContextLimit(ctxVal??4096);
    $('#ctxNumber').value=clamp(Number(ctxVal??4096),Number($('#ctxRange').min),Number($('#ctxRange').max));
    $('#ctxRange').value=$('#ctxNumber').value;
    currentMtpCapability=info.mtp_capability||{status:'unknown',evidence:[]};
    setMtpUi(currentMtpCapability, info.manager_preferences||{mtp_enabled:false,mtp_draft_n_max:2,source:'default'});
    currentThinkingDetected=info.thinking_detected||info.thinking_profile||null;
    setReasoningUi(currentThinkingDetected,info.thinking_override||{enabled:false});
    renderParameterEditor(values);
    renderEditorMemory(info.memory_estimate);
  }catch(e){
    $('#parameterGroups').innerHTML=`<div class="loading">${escapeHtml(e.message)}</div>`;
    setMtpUi({status:'unknown',summary:`Capability check failed: ${e.message}`,evidence:[]},{mtp_enabled:false,mtp_draft_n_max:2},false);
    toast(e.message,'error');
  }
}

function renderEditorMemory(m){if(!m){$('#editorGpuEstimate').textContent='Unavailable';$('#editorKvEstimate').textContent='—';$('#editorFitEstimate').textContent='—';return}$('#editorGpuEstimate').textContent=formatBytes(m.estimated_gpu_bytes||0);$('#editorKvEstimate').textContent=`${formatBytes(m.kv_cache_bytes||0)} · ${m.kv_cache_type||'f16'}`;const fit=$('#editorFitEstimate');fit.textContent=m.fit_label||'Estimate';fit.className=`fit-${m.fit||''}`;$('#editorEstimateNote').textContent=`${m.context_tokens?fmt(m.context_tokens)+' context · ':''}${m.kv_metadata_based?'KV based on model attention metadata':'KV uses fallback estimate'} · KV ${m.kv_cache_type||'f16'} (${m.kv_cache_source||'default'}) · estimate only.`}
let editorEstimateTimer=null;function recalcEditorMemory(){if(!currentModel)return;clearTimeout(editorEstimateTimer);editorEstimateTimer=setTimeout(async()=>{try{const gpuRow=$('.param-row[data-param="num_gpu"]'),gpuEnabled=gpuRow&&$('.param-enable',gpuRow)?.checked;const gpu=gpuEnabled?Number($('.param-value',gpuRow).value):-1;const d=await api('/api/manager/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:currentModel,num_ctx:Number($('#ctxNumber').value),num_gpu:gpu})});renderEditorMemory(d)}catch(_){ }},180)}

function setMtpUi(cap, pref, loading=false){
  const status = cap?.status || 'unknown';
  const badge=$('#mtpCapabilityBadge');
  badge.className=`capability-badge ${status}`;
  badge.textContent=loading?'CHECKING':status.toUpperCase();
  const title = status==='supported' ? 'MTP / NextN layers detected' : status==='unsupported' ? 'No embedded MTP layers detected' : loading ? 'Checking model capability…' : 'MTP capability uncertain';
  $('#mtpCapabilityTitle').textContent=title;
  $('#mtpCapabilityText').textContent=cap?.summary||'No capability information.';
  const evidence=cap?.evidence||[];
  $('#mtpEvidence').innerHTML=evidence.length?evidence.map(x=>`<code>${escapeHtml(x)}</code>`).join(''):'<span>No positive MTP / NextN tensor evidence returned.</span>';
  $('#mtpEvidenceWrap').style.display=evidence.length||status!=='supported'?'block':'none';
  const blocked=status==='unsupported'||loading;
  $('#mtpEnabled').disabled=blocked;
  $('#mtpToggleLine').classList.toggle('blocked',blocked);
  const enabled=!blocked&&Boolean(pref?.mtp_enabled);
  $('#mtpEnabled').checked=enabled;
  const depth=clamp(Number(pref?.mtp_draft_n_max||2),1,8);
  $('#mtpDepthRange').value=depth;
  $('#mtpDepthNumber').value=depth;
  syncMtpDepthDisplay();
  syncMtpControls();
  $('#mtpFeature').classList.toggle('unsupported',status==='unsupported');
  $('#mtpFeature').classList.toggle('supported',status==='supported');
  $('#mtpFeature').classList.toggle('unknown',status==='unknown');
}

function syncMtpDepthDisplay(){
  const raw=$('#mtpDepthNumber').value.trim(), value=Number(raw); const depth=raw!==''&&Number.isFinite(value)&&value>=1&&value<=8?value:'—';
  $('#mtpRunnerDepth').textContent=depth;
  $('#mtpRunnerDepthFlag').textContent=depth;
}
function syncMtpControls(){
  const usable=!$('#mtpEnabled').disabled&&$('#mtpEnabled').checked;
  $('#mtpDepthRange').disabled=!usable;
  $('#mtpDepthNumber').disabled=!usable;
  $('#mtpControls').classList.toggle('disabled',!usable);
  $('.mtp-runner-map').classList.toggle('disabled',!usable);
  syncMtpDepthDisplay();
}

function reasoningLabel(level){return ({off:'Off',on:'On',low:'Low',medium:'Medium',high:'High',xhigh:'XHigh',max:'Max'})[level]||level}
function detectedReasoningLevels(profile){return (profile?.options||[]).map(o=>String(o.value||'').toLowerCase()).filter(v=>['off','on','low','medium','high','xhigh','max'].includes(v))}
function updateReasoningDefault(){
  const select=$('#reasoningDefault'),checked=$$('[data-thinking-level]:checked').map(x=>x.dataset.thinkingLevel),previous=select.value;
  select.innerHTML=checked.length?checked.map(v=>`<option value="${escapeAttr(v)}">${escapeHtml(reasoningLabel(v))}</option>`).join(''):'<option value="">Choose at least one level</option>';
  if(checked.includes(previous))select.value=previous;
  else if(currentThinkingDetected?.default&&checked.includes(String(currentThinkingDetected.default)))select.value=String(currentThinkingDetected.default);
  else if(checked.length)select.value=checked[0];
}
function updateReasoningMethodHelp(){
  const method=$('#reasoningMethod').value,help=$('#reasoningMethodHelp');
  const text={native:'Uses Ollama’s native think field. Low/Medium/High map directly; XHigh is sent as max.', 'xhigh-default':'Uses native think for the normal levels, but selecting XHigh omits the think field so a template whose own default is XHigh can select it safely.', 'system-directive':'Does not send named think levels. Instead it adds “Reasoning effort: <level>” as a system directive; useful for Muse Glimmer and custom GGUF templates controlled by reasoning_strength.'};
  help.textContent=text[method]||'';
}
function syncReasoningManualState(){const manual=$('#reasoningOverrideEnabled').checked;$('#reasoningManualControls').classList.toggle('disabled',!manual);$$('#reasoningManualControls input,#reasoningManualControls select').forEach(el=>el.disabled=!manual);updateReasoningMethodHelp()}
function setReasoningUi(profile,override={},loading=false){
  const badge=$('#reasoningDetectedBadge'),supported=Boolean(profile?.supported);badge.className=`capability-badge ${loading?'unknown':supported?'supported':'unsupported'}`;badge.textContent=loading?'CHECKING':supported?'DETECTED':'BASIC';
  $('#reasoningDetectedTitle').textContent=loading?'Detecting model reasoning controls…':supported?(profile?.manual_override?'Manual override active':'Reasoning support detected'):'No named reasoning levels detected';
  $('#reasoningDetectedText').textContent=loading?'Reading the installed chat template and Ollama capabilities.':(profile?.summary||'The model currently falls back to basic/default thinking controls.');
  const evidence=profile?.evidence||[];$('#reasoningEvidence').innerHTML=evidence.length?evidence.map(x=>`<code>${escapeHtml(x)}</code>`).join(''):'<span>No detailed template evidence was returned by Ollama.</span>';
  const enabled=Boolean(override?.enabled);$('#reasoningOverrideEnabled').checked=enabled;
  const detected=detectedReasoningLevels(profile),levels=enabled?(override.levels||[]):detected;
  $$('[data-thinking-level]').forEach(box=>box.checked=levels.includes(box.dataset.thinkingLevel));
  $('#reasoningMethod').value=enabled&&['native','xhigh-default','system-directive'].includes(override.method)?override.method:'native';
  updateReasoningDefault();
  if(enabled&&override.default&&[...$('#reasoningDefault').options].some(o=>o.value===override.default))$('#reasoningDefault').value=override.default;
  syncReasoningManualState();
}
function collectReasoningOverride(){
  if(!$('#reasoningOverrideEnabled').checked)return {enabled:false};
  const levels=$$('[data-thinking-level]:checked').map(x=>x.dataset.thinkingLevel);
  return {enabled:true,levels,method:$('#reasoningMethod').value,default:$('#reasoningDefault').value};
}
function applyContextLimit(value=4096){
  const limit=currentModelLimits?.num_ctx||{};
  const max=Number(limit.max)||1048576;
  const min=512;
  const step=max<4096?64:512;
  $('#ctxRange').min=min; $('#ctxRange').max=max; $('#ctxRange').step=step;
  $('#ctxNumber').dataset.min=min; $('#ctxNumber').dataset.max=max; $('#ctxNumber').step=step;
  $('#ctxRangeMax').textContent=Number(limit.max)?`${fmt(max)} max`:'maximum unavailable';
  $('#ctxLimitNote').textContent=Number(limit.max)?`Model maximum: ${fmt(max)} tokens · values above this are blocked`:'Model training context was not exposed by Ollama; using the editor safety ceiling.';
  const safe=clamp(Number(value)||4096,min,max); $('#ctxRange').value=safe; $('#ctxNumber').value=safe;
}
function effectiveParamBounds(p){
  let min=p.min, max=p.max, note='';
  if(p.name==='num_gpu'){
    const lim=currentModelLimits?.num_gpu||{};
    if(Number.isFinite(Number(lim.max))&&Number(lim.max)>0){
      max=Number(lim.max); min=-1; note=`Model max: ${max} layers · ${max} = full GPU offload`;
    }else note='Model layer maximum unavailable from Ollama metadata.';
  }
  return {min,max,note};
}
function renderParameterEditor(values){
  const groups={};
  parameterDefs.filter(p=>p.name!=='num_ctx'&&!p.editor_hidden).forEach(p=>(groups[p.group]??=[]).push(p));
  $('#parameterGroups').innerHTML=Object.entries(groups).map(([group,items])=>`<div class="param-group" data-group="${escapeAttr(group)}"><div class="param-group-title">${escapeHtml(group)}</div>${items.map(p=>paramRow(p,values[p.name])).join('')}</div>`).join('');
  $$('.param-enable').forEach(c=>c.addEventListener('change',()=>syncParamRow(c.closest('.param-row'))));
  $$('.param-slider').forEach(slider=>slider.addEventListener('input',()=>{const row=slider.closest('.param-row');const input=$('.param-value',row);input.value=slider.value;syncSliderMeta(row);if(row.dataset.param==='num_gpu')recalcEditorMemory();}));
  $$('.param-value[type=number]').forEach(input=>input.addEventListener('input',()=>{const row=input.closest('.param-row');const slider=$('.param-slider',row);if(!slider)return;const raw=input.value.trim();if(raw==='')return;const value=Number(raw),min=Number(slider.min),max=Number(slider.max);if(!Number.isFinite(value)||value<min||value>max)return;slider.value=value;syncSliderMeta(row);if(row.dataset.param==='num_gpu')recalcEditorMemory();}));
  $$('.param-row').forEach(row=>{syncParamRow(row);syncSliderMeta(row)}); filterParams();
}
function paramRow(p,current){
  const has=current!==undefined; let v=has?(Array.isArray(current)?current.join('\n'):current):p.default;
  const bounds=effectiveParamBounds(p);
  if((p.type==='int'||p.type==='float')&&Number.isFinite(Number(bounds.max))&&Number.isFinite(Number(bounds.min))) v=clamp(Number(v),Number(bounds.min),Number(bounds.max));
  let control='';
  if(p.type==='bool') control=`<select class="param-value"><option value="true" ${String(v)==='true'?'selected':''}>true</option><option value="false" ${String(v)==='false'?'selected':''}>false</option></select>`;
  else if(p.type==='enum') control=`<select class="param-value">${p.options.map(o=>`<option value="${escapeAttr(o)}" ${String(v)===String(o)?'selected':''}>${escapeHtml(String(o))}</option>`).join('')}</select>`;
  else if(p.type==='string-list') control=`<input class="param-value" type="text" value="${escapeAttr(Array.isArray(current)?current.join(', '):(current??''))}" placeholder="comma-separated">`;
  else {
    const minData=bounds.min!==undefined?`data-min="${bounds.min}"`:''; const maxData=bounds.max!==undefined?`data-max="${bounds.max}"`:'';
    const number=`<input class="param-value" type="number" value="${escapeAttr(v)}" ${minData} ${maxData} step="${p.step??1}">`;
    if(p.slider&&bounds.min!==undefined&&bounds.max!==undefined){
      control=`<div class="param-slider-control"><input class="param-slider" type="range" value="${escapeAttr(v)}" min="${bounds.min}" max="${bounds.max}" step="${p.step??1}"><div class="param-number-line">${number}<span class="param-range-readout"></span></div>${bounds.note?`<small class="model-limit-note">${escapeHtml(bounds.note)}</small>`:''}</div>`;
    }else control=number;
  }
  return `<div class="param-row ${p.name==='num_gpu'?'featured-param':''}" data-param="${escapeAttr(p.name)}"><input type="checkbox" class="check param-enable" ${has?'checked':''}><div class="param-name"><b>${escapeHtml(p.name)}</b><span>${escapeHtml(p.type_label||p.type)}</span></div><div class="param-desc">${escapeHtml(p.description)}</div><div class="param-control">${control}</div></div>`;
}
function syncSliderMeta(row){
  const slider=$('.param-slider',row), readout=$('.param-range-readout',row); if(!slider||!readout)return;
  const value=Number(slider.value); const name=row.dataset.param;
  if(name==='num_gpu') readout.textContent=value===-1?'Auto':value===0?'CPU only':value===Number(slider.max)?'Full offload':`${value}/${slider.max} layers`;
  else readout.textContent=`${slider.value} / ${slider.max}`;
}
function syncParamRow(row){const on=$('.param-enable',row).checked;row.classList.toggle('disabled',!on);$$('.param-value,.param-slider',row).forEach(el=>el.disabled=!on);}
function filterParams(){const q=$('#parameterSearch').value.trim().toLowerCase();$$('.param-row').forEach(r=>{r.style.display=(!q||r.dataset.param.includes(q)||r.textContent.toLowerCase().includes(q))?'grid':'none'});$$('.param-group').forEach(g=>g.style.display=$$('.param-row',g).some(r=>r.style.display!=='none')?'block':'none');}
function collectParameters(){
  const out={}; if($('#ctxEnabled').checked)out.num_ctx=parseInt($('#ctxNumber').value,10);
  $$('.param-row').forEach(r=>{if(!$('.param-enable',r).checked)return;const def=parameterDefs.find(p=>p.name===r.dataset.param);let v=$('.param-value',r).value;if(def.type==='int')v=parseInt(v,10);else if(def.type==='float')v=parseFloat(v);else if(def.type==='bool')v=v==='true';else if(def.type==='enum'&&def.numeric)v=parseInt(v,10);else if(def.type==='string-list')v=v.split(',').map(x=>x.trim()).filter(Boolean);out[def.name]=v;});return out;
}
function collectMtp(){
  return {enabled:$('#mtpEnabled').checked&&!$('#mtpEnabled').disabled,draft_n_max:parseInt($('#mtpDepthNumber').value,10)};
}
function validateEditorNumbers(){
  if($('#ctxEnabled').checked){
    const raw=$('#ctxNumber').value.trim(), min=Number($('#ctxRange').min), max=Number($('#ctxRange').max), value=Number(raw);
    if(raw===''||!Number.isFinite(value)||!Number.isInteger(value))return 'num_ctx must be a whole number.';
    if(value<min)return `num_ctx cannot be below ${fmt(min)} tokens.`;
    if(value>max)return `num_ctx cannot be above this model maximum of ${fmt(max)} tokens.`;
  }
  for(const row of $$('.param-row')){
    if(!$('.param-enable',row).checked)continue;
    const def=parameterDefs.find(p=>p.name===row.dataset.param); if(!def||!['int','float'].includes(def.type))continue;
    const input=$('.param-value',row), raw=input.value.trim(), value=Number(raw), bounds=effectiveParamBounds(def);
    if(raw===''||!Number.isFinite(value))return `${def.name} must be a valid number.`;
    if(def.type==='int'&&!Number.isInteger(value))return `${def.name} must be a whole number.`;
    if(bounds.min!==undefined&&value<Number(bounds.min))return `${def.name} cannot be below ${bounds.min}.`;
    if(bounds.max!==undefined&&value>Number(bounds.max))return `${def.name} cannot be above ${bounds.max}.`;
  }
  if($('#mtpEnabled').checked&&!$('#mtpEnabled').disabled){
    const raw=$('#mtpDepthNumber').value.trim(), value=Number(raw);
    if(raw===''||!Number.isInteger(value))return 'MTP draft depth must be a whole number.';
    if(value<1||value>8)return 'MTP draft depth must be between 1 and 8.';
  }
  if($('#reasoningOverrideEnabled').checked){
    const levels=$$('[data-thinking-level]:checked').map(x=>x.dataset.thinkingLevel);
    if(!levels.length)return 'Manual thinking override requires at least one enabled level.';
    if(!levels.includes($('#reasoningDefault').value))return 'Choose a default from the enabled thinking levels.';
  }
  return null;
}
async function saveModel(){
  const target=$('#targetModelName').value.trim();
  if(!target)return toast('Enter a target model name','error');
  const validationError=validateEditorNumbers();
  if(validationError)return toast(validationError,'error');
  const parameters=collectParameters();
  const mtp=collectMtp();
  const reasoning_override=collectReasoningOverride();
  if(mtp.enabled&&currentMtpCapability.status==='unsupported')return toast('MTP is blocked for this model because no embedded MTP / NextN layers were detected.','error');
  $('#saveModelBtn').disabled=true;$('#saveStatus').textContent='Writing model definition…';
  try{
    const r=await fetch('/api/manager/modify-model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:currentModel,target,parameters,mtp,reasoning_override})});
    if(!r.ok){const d=await r.json();throw new Error(d.error||'Save failed');}
    const reader=r.body.getReader(),dec=new TextDecoder();let buf='';
    while(true){const {value,done}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});let lines=buf.split('\n');buf=lines.pop();for(const line of lines){if(!line.trim())continue;let d;try{d=JSON.parse(line)}catch(_){continue}if(d.error)throw new Error(d.error);if(d.warning)toast(d.warning,'error');if(d.status)$('#saveStatus').textContent=d.status;}}
    toast(`${target} saved${mtp.enabled?` · MTP depth ${mtp.draft_n_max}`:' · MTP off'}`);closeModal('editorModal');await loadModels();
  }catch(e){toast(e.message,'error');$('#saveStatus').textContent=e.message;}finally{$('#saveModelBtn').disabled=false;}
}

function escapeHtml(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function escapeAttr(v=''){return escapeHtml(v);}
function clamp(v,a,b){return Math.min(b,Math.max(a,v));}

$$('.nav-item[data-view]').forEach(n=>n.addEventListener('click',()=>switchView(n.dataset.view)));
$$('[data-close]').forEach(b=>b.addEventListener('click',()=>closeModal(b.dataset.close)));
$$('.modal-backdrop').forEach(m=>m.addEventListener('click',e=>{if(e.target===m)closeModal(m.id)}));
$('#pullBtn').onclick=()=>{ $('#pullModelName').value='';$('#pullProgressWrap').classList.add('hidden');$('#pullProgress').style.width='0';$('#pullPercent').textContent='';openModal('pullModal'); };
$('#startPullBtn').onclick=startPull;
$$('.examples button').forEach(b=>b.onclick=()=>$('#pullModelName').value=b.dataset.model);
$('#refreshBtn').onclick=()=>{ const active=$('.view.active').id; active==='dashboardView'?(loadDashboard(),loadLive(),loadHardware()):loadModels(); };
if($('#openClearTelemetry'))$('#openClearTelemetry').onclick=()=>openModal('clearTelemetryModal');
if($('#confirmClearTelemetry'))$('#confirmClearTelemetry').onclick=clearDashboardData;
$('#hardwareRetry').onclick=loadHardware;
$('#modelSearch').addEventListener('input',renderModels);
$('#parameterSearch').addEventListener('input',filterParams);
$('#ctxRange').addEventListener('input',()=>{$('#ctxNumber').value=$('#ctxRange').value;recalcEditorMemory()});
$('#ctxNumber').addEventListener('input',()=>{const raw=$('#ctxNumber').value.trim();if(raw==='')return;const v=Number(raw),min=Number($('#ctxRange').min)||512,max=Number($('#ctxRange').max)||1048576;if(!Number.isFinite(v)||v<min||v>max)return;$('#ctxRange').value=v;recalcEditorMemory()});
$('#mtpEnabled').addEventListener('change',syncMtpControls);
$('#mtpDepthRange').addEventListener('input',()=>{$('#mtpDepthNumber').value=$('#mtpDepthRange').value;syncMtpDepthDisplay();});
$('#mtpDepthNumber').addEventListener('input',()=>{const raw=$('#mtpDepthNumber').value.trim();if(raw===''){syncMtpDepthDisplay();return}const v=Number(raw);if(Number.isFinite(v)&&v>=1&&v<=8)$('#mtpDepthRange').value=v;syncMtpDepthDisplay();});
$('#reasoningOverrideEnabled').addEventListener('change',()=>{if($('#reasoningOverrideEnabled').checked&&!$$('[data-thinking-level]:checked').length){const detected=detectedReasoningLevels(currentThinkingDetected);$$('[data-thinking-level]').forEach(b=>b.checked=detected.includes(b.dataset.thinkingLevel));updateReasoningDefault()}syncReasoningManualState()});
$$('[data-thinking-level]').forEach(b=>b.addEventListener('change',updateReasoningDefault));
$('#reasoningMethod').addEventListener('change',updateReasoningMethodHelp);
$('#saveModelBtn').onclick=saveModel;
window.addEventListener('resize',()=>{if($('#dashboardView').classList.contains('active'))loadDashboard()});
const queryParams=new URLSearchParams(location.search);const requestedView=queryParams.get('view') || (location.hash.replace('#','')==='models'?'models':'dashboard');
if(requestedView==='models'){switchView('models');const edit=queryParams.get('edit');if(edit)setTimeout(()=>openEditor(edit),350)} else {switchView('dashboard'); loadLive();}
liveTimer=setInterval(loadLive,1000);
setInterval(()=>{if($('#dashboardView').classList.contains('active'))loadHardware({silent:true})},2500);
