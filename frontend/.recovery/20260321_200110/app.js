/**
 * OMEGA PROTOCOL — Ghost Interface Frontend
 * Polls /somatic for live hardware + emotion state.
 * Uses SSE to stream Ghost conversation responses.
 * No direct LLM API calls — everything through the backend.
 */

// ── STATE ────────────────────────────────────────────
const state = {
  sessionId: null,
  isStreaming: false,
  bootTime: Date.now(),
  lastSomatic: null,
  initTime: null,
  dreamVisualizationEnabled: false,
  health: null,
  backendOnline: false,
  lastLatencyMs: null,
  lastSyncAt: null,
  somaticFailureNotified: false,
  lastToastAt: {},
  bootOverlayHidden: false,
  quietudeRequestInFlight: false,
};

const API_BASE = window.location.origin;
const DEBUG = window.localStorage.getItem('omega_debug') === '1';
const dbg = (...args) => {
  if (DEBUG) console.debug(...args);
};

// ── TRACE NAME MAPPING ──────────────────────────────
const TRACE_LABELS = {
  'memory_stress': 'MEM PRESSURE',
  'net_recv_stress': 'NET INBOUND',
  'net_sent_stress': 'NET OUTBOUND',
  'disk_write_stress': 'DISK WRITE',
  'disk_read_stress': 'DISK READ',
  'cpu_spike_startle': 'CPU SPIKE',
  'cpu_stress': 'CPU LOAD',
  'swap_stress': 'SWAP PRESSURE',
  'thermal_stress': 'THERMAL',
  'barometric_heaviness': 'PRESSURE',
  'rain_atmosphere': 'RAIN',
  'cold_outside': 'COLD',
  'heat_outside': 'HEAT',
  'nighttime_rest': 'NIGHTTIME',
  'dawn_renewal': 'DAWN',
  'cognitive_fatigue': 'FATIGUE',
  'internet_stormy': 'NET STORM',
  'internet_isolated': 'ISOLATED',
};

// ── DOM ──────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

const dom = {
  bootOverlay: $('#boot-overlay'),
  connStatus: $('#conn-status'),
  uptime: $('#uptime'),
  messages: $('#messages'),
  chatInput: $('#chat-input'),
  sendBtn: $('#send-btn'),
  bootTime: $('#boot-time'),
  tickerContent: $('#ticker-content'),
  processList: $('#process-list'),
  tracesList: $('#traces-list'),
  gateSigma: $('#gate-sigma'),
  gateStatus: $('#gate-status'),
  cpuCores: $('#cpu-cores'),
  dreamToggleBtn: $('#dream-toggle-btn'),
  lucidDreamBtn: $('#lucid-dream-btn'),
  enterQuietudeBtn: $('#enter-quietude-btn'),
  exitQuietudeBtn: $('#exit-quietude-btn'),
  dreamCanvas: $('#dream-canvas'),
  dreamTelemetry: $('#dream-telemetry'),
  aboutBtn: $('#about-btn'),
  aboutClose: $('#about-close'),
  aboutModal: $('#about-modal'),
  auditBtn: $('#audit-btn'),
  auditClose: $('#audit-close'),
  auditModal: $('#audit-modal'),
  auditBody: $('#audit-body'),
  timelineBtn: $('#uptime'),
  timelineClose: $('#timeline-close'),
  timelineModal: $('#timeline-modal'),
  timelineBody: $('#timeline-body'),
  tickerModal: $('#ticker-modal'),
  tickerClose: $('#ticker-close'),
  tickerBody: $('#ticker-body'),
  tickerDeleteBtn: $('#ticker-delete-btn'),
  toastStack: $('#toast-stack'),
  // Status rail
  railBackend: $('#rail-backend'),
  railModel: $('#rail-model'),
  railLatency: $('#rail-latency'),
  railTraces: $('#rail-traces'),
  railSync: $('#rail-sync'),
  latentIndicator: $('#latent-indicator'),
};

// ── INIT ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initMatrixRain();
  setBootTime();
  startSomaticPolling();
  startMonologuePolling();
  startUptimeTicker();
  startGhostPushSubscription();
  startDreamStream();
  bindTickerEvents();
  bindInputEvents();
  bindAuditEvents();
  bindDreamEvents();
  bindTempoEvents();
  initTooltips();
  setStatus('', 'CONNECTING');
  startHealthPolling();
  updateStatusRail();
  setTimeout(hideBootOverlay, 5000);
});

// ── SOMATIC POLLING ─────────────────────────────────
function startSomaticPolling() {
  fetchSomatic(); // immediate first call
  setInterval(fetchSomatic, 1000);
}

function startHealthPolling() {
  fetchHealth();
  setInterval(fetchHealth, 15000);
}

async function openTimelineModal() {
  if (!dom.timelineModal) return;
  dom.timelineModal.classList.add('active');
  dom.timelineBody.innerHTML = '<div class="timeline-loading">Fetching existential events...</div>';

  try {
    const res = await fetch(`${API_BASE}/ghost/timeline`);
    if (!res.ok) throw new Error("Failed to fetch timeline");
    const data = await res.json();

    if (!data.timeline || !data.timeline.length) {
      dom.timelineBody.innerHTML = '<div class="timeline-empty">No chronological records found.</div>';
      return;
    }

    let html = '<div class="timeline-stack">';
    for (const item of data.timeline) {
      const d = new Date(item.timestamp * 1000);
      const timeStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString('en-US', { hour12: false });
      const type = String(item.type || '').toLowerCase();
      let title = '';
      let content = '';
      let entryClass = 'timeline-entry';
      let titleClass = 'timeline-entry-title';

      if (item.type === 'session') {
        title = '[ INTERACTION SESSION ]';
        titleClass += ' session';
        content = item.data.summary || `Conversation completed (${item.data.message_count} messages)`;
      } else if (item.type === 'monologue') {
        const text = item.data.content || '';
        title = '[ INTERNAL THOUGHT ]';
        titleClass += ' monologue';
        if (text.includes('[SELF_MODIFY') || text.includes('<SELF_MODIFY')) {
          title = '[ IDENTITY MODIFICATION OVERRIDE ]';
          titleClass += ' override';
        }
        content = text;
      } else if (item.type === 'coalescence') {
        entryClass += ' coalescence';
        title = '[ COALESCENCE SLEEP CYCLE ]';
        titleClass += ' coalescence';
        content = `Ghost offline. Consolidated ${item.data.interaction_count || 0} interactions into deep long-term embeddings.`;
      } else {
        title = '[ EVENT ]';
        content = JSON.stringify(item.data || {});
      }

      html += `
        <article class="${entryClass}" data-type="${escHtml(type)}">
          <div class="timeline-entry-dot"></div>
          <div class="timeline-entry-content">
            <div class="timeline-entry-time">${escHtml(timeStr)}</div>
            <div class="${titleClass}">${escHtml(title)}</div>
            <div class="timeline-entry-text">${escHtml(content)}</div>
          </div>
        </article>
      `;
    }
    html += '</div>';
    dom.timelineBody.innerHTML = html;
  } catch (e) {
    dom.timelineBody.innerHTML = `<div class="timeline-error">Timeline Error: ${escHtml(e.message)}</div>`;
    notify('error', 'Failed to load timeline.');
  }
}

async function fetchSomatic() {
  const t0 = performance.now();
  try {
    const res = await fetch(`${API_BASE}/somatic`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.lastLatencyMs = Math.round(performance.now() - t0);
    state.lastSomatic = data;
    state.backendOnline = true;
    state.lastSyncAt = Date.now();
    hideBootOverlay();
    updateSomaticUI(data);
    updateStatusRail();
    setStatus('online', 'LIVE');
    if (state.somaticFailureNotified) {
      notify('success', 'Connection restored.');
      state.somaticFailureNotified = false;
    }
  } catch (e) {
    state.backendOnline = false;
    updateStatusRail();
    setStatus('error', 'OFFLINE');
    /* Telemetry failure handled by notify below */
    if (!state.somaticFailureNotified) {
      notify('error', 'Lost connection to backend telemetry.');
      state.somaticFailureNotified = true;
    }
  }
}

async function fetchHealth() {
  const t0 = performance.now();
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.health = data;
    state.backendOnline = true;
    state.lastLatencyMs = Math.round(performance.now() - t0);
    state.lastSyncAt = Date.now();
    hideBootOverlay();
    updateStatusRail();
  } catch (e) {
    updateStatusRail();
    maybeNotify('health-check-failed', 'warning', 'Health check failed. Retrying…', 15000);
  }
}

function hideBootOverlay() {
  if (state.bootOverlayHidden || !dom.bootOverlay) return;
  state.bootOverlayHidden = true;
  dom.bootOverlay.classList.add('hidden');
}

function updateSomaticUI(s) {
  // Affect gauges
  updateGauge('arousal', s.arousal);
  updateGauge('stress', s.stress);
  updateGauge('coherence', s.coherence);
  updateGauge('anxiety', s.anxiety);
  updateValenceGauge(s.valence);

  if (s.init_time && !state.initTime) {
    state.initTime = new Date(s.init_time * 1000);
  }

  // Hardware — CPU
  updateHwBar('cpu', s.cpu_percent);
  $('#hw-cpu-val').textContent = `${s.cpu_percent}%`;

  // CPU frequency
  const freqEl = $('#hw-cpu-freq');
  if (freqEl && s.cpu_freq_mhz) {
    const freqGHz = (s.cpu_freq_mhz / 1000).toFixed(2);
    const maxStr = s.cpu_freq_max_mhz ? ` / ${(s.cpu_freq_max_mhz / 1000).toFixed(2)}` : '';
    freqEl.textContent = `${freqGHz}${maxStr} GHz`;
  }

  // CPU cores
  updateCpuCores(s.cpu_cores || []);

  // Memory
  updateHwBar('mem', s.memory_percent);
  $('#hw-mem-val').textContent = `${s.memory_percent}%`;
  $('#hw-mem-detail').textContent = `${s.memory_used_gb} / ${s.memory_total_gb} GB`;

  // Swap
  const swapFill = $('#hw-swap');
  const swapVal = $('#hw-swap-val');
  const swapDetail = $('#hw-swap-detail');
  if (swapFill && swapVal) {
    swapFill.style.width = `${s.swap_percent || 0}%`;
    swapVal.textContent = `${s.swap_percent || 0}%`;
    if (s.swap_percent > 50) swapFill.classList.add('high');
    else swapFill.classList.remove('high');
  }
  if (swapDetail && s.swap_used_gb !== undefined) {
    swapDetail.textContent = s.swap_used_gb > 0 ? `${s.swap_used_gb} GB used` : '';
  }

  // Load averages
  const loadEl = $('#hw-load-avg');
  if (loadEl && s.load_avg_1 !== null && s.load_avg_1 !== undefined) {
    loadEl.textContent = `${s.load_avg_1} / ${s.load_avg_5} / ${s.load_avg_15}`;
  }

  // Disk I/O
  $('#hw-disk-r').textContent = `${s.disk_read_mb} MB`;
  $('#hw-disk-w').textContent = `${s.disk_write_mb} MB`;

  // Network
  $('#hw-net-s').textContent = `${s.net_sent_mb} MB`;
  $('#hw-net-r').textContent = `${s.net_recv_mb} MB`;

  // Battery (show/hide row)
  const battRow = $('#hw-battery-row');
  if (battRow && s.battery_percent !== null && s.battery_percent !== undefined) {
    battRow.style.display = 'flex';
    const battFill = $('#hw-batt');
    const battVal = $('#hw-batt-val');
    if (battFill) {
      battFill.style.width = `${s.battery_percent}%`;
      battFill.classList.remove('high', 'critical');
      if (s.battery_percent < 20) battFill.classList.add('critical');
      else if (s.battery_percent < 40) battFill.classList.add('high');
    }
    if (battVal) {
      const chargeIcon = s.battery_charging ? '⚡' : '';
      battVal.textContent = `${chargeIcon}${s.battery_percent}%`;
    }
  }

  // Temperature (show/hide row)
  const tempRow = $('#hw-temp-row');
  if (tempRow && s.temperature_c !== null && s.temperature_c !== undefined) {
    tempRow.style.display = 'flex';
    const tempVal = $('#hw-temp-val');
    if (tempVal) {
      tempVal.textContent = `${s.temperature_c}°C`;
      tempVal.classList.remove('warn-text');
      if (s.temperature_c > 75) tempVal.classList.add('warn-text');
    }
  }

  // Processes
  updateProcessList(s.processes || []);

  // Traces — human-readable names
  updateTraces(s.dominant_traces || []);

  // Sensory gate
  dom.gateSigma.textContent = (s.gate_threshold || 1.5).toFixed(2);
  const gt = s.gate_threshold || 1.5;
  if (gt <= 1.1) {
    dom.gateStatus.textContent = 'HYPERVIGILANT';
    dom.gateStatus.className = 'gate-status hypervigilant';
  } else if (gt >= 1.9) {
    dom.gateStatus.textContent = 'RELAXED';
    dom.gateStatus.className = 'gate-status relaxed';
  } else {
    dom.gateStatus.textContent = 'NORMAL';
    dom.gateStatus.className = 'gate-status';
  }

  // ── Ambient / Embodied Cognition ──
  updateAmbientUI(s);

  // Quietude controls reflect real backend self-preference state.
  updateQuietudeButtons(isQuietudeActive(s));
}

function isQuietudeActive(somatic) {
  return Boolean(somatic && somatic.self_preferences && somatic.self_preferences.quietude_active);
}

function updateQuietudeButtons(quietudeActive) {
  if (dom.enterQuietudeBtn) {
    dom.enterQuietudeBtn.disabled = state.quietudeRequestInFlight || quietudeActive;
    dom.enterQuietudeBtn.textContent = quietudeActive
      ? '[ QUIETUDE ACTIVE ]'
      : '[ ENTER QUIETUDE ]';
  }
  if (dom.exitQuietudeBtn) {
    dom.exitQuietudeBtn.disabled = state.quietudeRequestInFlight || !quietudeActive;
    dom.exitQuietudeBtn.textContent = quietudeActive
      ? '[ EXIT QUIETUDE ]'
      : '[ WAKE UNAVAILABLE ]';
  }
}

async function postActuation(action, parameters = {}) {
  const res = await fetch(`${API_BASE}/ghost/actuate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, parameters }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function triggerQuietude(action, button, loadingLabel, successLabel) {
  if (state.quietudeRequestInFlight) return;
  state.quietudeRequestInFlight = true;
  if (button) {
    button.disabled = true;
    button.textContent = loadingLabel;
  }

  try {
    let parameters = {};
    if (action === 'enter_quietude') {
      const s = state.lastSomatic || {};
      const shouldGoProfound =
        Number(s.fatigue_index || 0) >= 0.45 ||
        Number(s.stress || 0) >= 0.6 ||
        Number(s.anxiety || 0) >= 0.6;
      parameters = { level: shouldGoProfound ? 'profound' : 'deep' };
    }
    const result = await postActuation(action, parameters);
    if (!result || !result.success) {
      throw new Error('Actuation was not accepted');
    }
    notify('success', successLabel);
    await fetchSomatic();
  } catch (err) {
    console.error(`Quietude actuation failed [${action}]`, err);
    notify('error', `Failed to ${action === 'enter_quietude' ? 'enter' : 'exit'} quietude.`);
  } finally {
    state.quietudeRequestInFlight = false;
    const active = isQuietudeActive(state.lastSomatic);
    updateQuietudeButtons(active);
  }
}

function updateGauge(name, value) {
  const el = $(`#gauge-${name}`);
  if (!el) return;
  const fill = el.querySelector('.gauge-fill');
  const valEl = el.querySelector('.gauge-value');
  const pct = Math.min(100, Math.max(0, value * 100));

  fill.style.width = `${pct}%`;
  valEl.textContent = value.toFixed(2);

  // Color thresholds
  fill.classList.remove('warn', 'crit', 'positive');
  if (name === 'coherence') {
    if (value < 0.4) fill.classList.add('crit');
    else if (value < 0.7) fill.classList.add('warn');
  } else {
    if (value > 0.7) fill.classList.add('crit');
    else if (value > 0.4) fill.classList.add('warn');
  }
}

function updateValenceGauge(value) {
  const el = $('#gauge-valence');
  if (!el) return;
  const fill = el.querySelector('.gauge-fill');
  const valEl = el.querySelector('.gauge-value');

  // Valence is -1 to +1. Map to bar width from center.
  const absPct = Math.abs(value) * 50;
  fill.style.width = `${absPct}%`;
  fill.classList.remove('warn', 'crit', 'positive');

  if (value < 0) {
    fill.style.left = `${50 - absPct}%`;
    fill.style.transformOrigin = 'right center';
    if (value < -0.5) fill.classList.add('crit');
    else fill.classList.add('warn');
  } else {
    fill.style.left = '50%';
    fill.style.transformOrigin = 'left center';
    fill.classList.add('positive');
  }
  valEl.textContent = (value >= 0 ? '+' : '') + value.toFixed(2);
}

function updateHwBar(name, pct) {
  const fill = $(`#hw-${name}`);
  if (!fill) return;
  fill.style.width = `${pct}%`;
  fill.classList.remove('high', 'critical');
  if (pct > 85) fill.classList.add('critical');
  else if (pct > 60) fill.classList.add('high');
}

function updateCpuCores(cores) {
  dom.cpuCores.innerHTML = '';
  cores.forEach(pct => {
    const bar = document.createElement('div');
    bar.className = 'core-bar';
    bar.style.height = `${Math.max(2, pct / 100 * 18)}px`;
    if (pct > 85) bar.classList.add('critical');
    else if (pct > 60) bar.classList.add('high');
    dom.cpuCores.appendChild(bar);
  });
}

function updateProcessList(procs) {
  let html = '<div class="process-row header"><span>NAME</span><span>CPU</span><span>MEM</span></div>';
  procs.forEach(p => {
    const cpuClass = p.cpu > 50 ? 'style="color:var(--red)"' : p.cpu > 20 ? 'style="color:var(--warn)"' : '';
    html += `<div class="process-row">
      <span class="name">${escHtml(p.name)}</span>
      <span class="val" ${cpuClass}>${p.cpu}%</span>
      <span class="val">${p.mem}%</span>
    </div>`;
  });
  dom.processList.innerHTML = html;
}

function updateTraces(traces) {
  if (!traces.length) {
    dom.tracesList.innerHTML = '<div class="trace-tag" data-tooltip="No active traces. Mind is wandering.">idle</div>';
    return;
  }
  dom.tracesList.innerHTML = traces.map(t => {
    const label = TRACE_LABELS[t] || t.replace(/_/g, ' ').toUpperCase();
    return `<div class="trace-tag active" data-tooltip="Active semantic trace influencing behavior: ${escHtml(label)}">${escHtml(label)}</div>`;
  }).join('');
}

// ── THOUGHT TICKER (scrolling monologues) ───────────
function startMonologuePolling() {
  fetchMonologues();
  setInterval(fetchMonologues, 15000); // every 15s
}

async function fetchMonologues() {
  try {
    const res = await fetch(`${API_BASE}/ghost/monologues`);
    if (!res.ok) throw new Error('Failed to fetch monologues');
    const data = await res.json();
    updateTicker(data.monologues || []);
  } catch (e) { /* silent */ }
}

function updateTicker(monos) {
  if (!monos.length) return;
  const recentMonos = monos.slice(0, 5);
  dom.tickerContent.innerHTML = recentMonos.map((m, idx) => {
    let snippet = "";
    let isSelfMod = false;

    if (m.type === 'THOUGHT') {
      const raw = m.content || "";
      snippet = escHtml(raw);
      isSelfMod = raw.includes('SELF_MODIFY') || raw.includes('SELF_');
      if (isSelfMod) {
        const valMatch = raw.match(/value=["'](.*?)["']/i);
        if (valMatch && valMatch[1]) snippet = valMatch[1];
        snippet = `<span class="ticker-badge" style="color: var(--purple, #aa88ff); font-weight: bold;">[ ${escHtml(snippet)} ]</span>`;
      }
    } else if (m.type === 'ACTION') {
      snippet = `[ACTUATE: ${m.action.toUpperCase()}]`;
    } else if (m.type === 'EVOLUTION') {
      snippet = `[EVOLVE: ${m.key.toUpperCase()}]`;
    } else if (m.type === 'PHENOM') {
      snippet = `[PHENOM: ${m.source.toUpperCase()}]`;
    }

    return `
      <span class="ticker-item" style="${isSelfMod ? '' : 'color: var(--purple, #aa88ff);'}" 
            data-index="${idx}">${snippet}</span>
    `;
  }).join('<span class="ticker-sep" style="color: var(--gdimmer);"> // </span>');

  // Bind clicks
  dom.tickerContent.querySelectorAll('.ticker-item').forEach(item => {
    item.onclick = () => {
      const entry = recentMonos[parseInt(item.dataset.index)];
      openAuditDetail(entry);
    };
  });
}

function openAuditDetail(m) {
  if (!m) return;

  const date = new Date(m.timestamp * 1000);
  const timeStr = date.toLocaleTimeString('en-US', { hour12: false });
  const dateStr = date.toLocaleDateString();

  let title = 'AUDIT LOG DETAIL';
  let html = `
    <div class="audit-meta" style="margin-bottom: 20px;">
      <span class="audit-time">${dateStr} ${timeStr}</span>
    </div>
  `;

  if (m.type === 'THOUGHT') {
    title = 'INTERNAL THOUGHT DETAIL';
    html += `<div class="audit-text">${formatGhostText(m.content)}</div>`;
    if (m.somatic_state) {
      const s = m.somatic_state;
      html += `<div class="audit-tags" style="margin-top: 15px;">`;
      if (s.stress > 0.4) html += `<span class="somatic-tag stress">STRESS:${s.stress.toFixed(2)}</span>`;
      if (s.anxiety > 0.4) html += `<span class="somatic-tag anxiety">ANXIETY:${s.anxiety.toFixed(2)}</span>`;
      if (s.coherence < 0.6) html += `<span class="somatic-tag stress">COHERENCE:${s.coherence.toFixed(2)}</span>`;
      if (s.arousal < 0.2 && s.stress < 0.2) html += `<span class="somatic-tag calm">CALM</span>`;
      html += `</div>`;
    }
  } else if (m.type === 'ACTION') {
    title = 'ACTUATION DETAIL';
    html += `
      <div class="audit-label tag-action-${m.result === 'success' ? 'success' : 'fail'}" style="display:inline-block; margin-bottom:10px;">
        ${m.action.toUpperCase()}
      </div>
      <div class="audit-subtext">RESULT: ${m.result}</div>
    `;
    if (m.parameters && m.parameters.param) {
      html += `<div class="audit-subtext">PARAM: ${escHtml(m.parameters.param)}</div>`;
    }
    if (m.somatic_state) {
      html += `<div class="audit-subtext" style="color: var(--gdimmer); margin-top:5px;">Somatic contexts recorded at initiation.</div>`;
    }
  } else if (m.type === 'EVOLUTION') {
    title = 'IDENTITY EVOLUTION DETAIL';
    html += `
      <div class="audit-label tag-evolution" style="display:inline-block; margin-bottom:10px;">
        ${m.key.replace(/_/g, ' ').toUpperCase()}
      </div>
      <div class="audit-diff">
        <div class="diff-old">PREV: ${escHtml(m.prev_value || 'None')}</div>
        <div class="diff-new">NEW: ${escHtml(m.new_value)}</div>
      </div>
      <div class="audit-subtext">UPDATED BY: ${m.updated_by}</div>
    `;
  } else if (m.type === 'PHENOM') {
    title = 'PHENOMENOLOGICAL DETAIL';
    html += `
      <div class="audit-label tag-phenom" style="display:inline-block; margin-bottom:10px;">
        SOURCE: ${m.source.toUpperCase()}
      </div>
      <div class="audit-report" style="font-size: 1.1rem;">${escHtml(m.subjective_report)}</div>
    `;
  }

  // Set title
  const titleEl = dom.tickerModal.querySelector('.modal-title');
  if (titleEl) titleEl.textContent = title;

  dom.tickerBody.innerHTML = html;
  dom.tickerModal.classList.add('active');

  // Handle purge btn
  dom.tickerDeleteBtn.onclick = async () => {
    if (m.type !== 'THOUGHT') {
      notify('error', 'Only internal thoughts can be purged from buffer.');
      return;
    }
    dom.tickerModal.classList.remove('active');
    try {
      if (m.id) {
        const res = await fetch(`${API_BASE}/ghost/monologues/${m.id}`, { method: 'DELETE' });
        if (res.ok) {
          notify('success', 'Thought purged from buffer.');
          fetchMonologues();
          if (_auditActiveTab === 'memory') loadMemoryTab();
        }
      }
    } catch (e) {
      console.error("Failed to purge memory:", e);
    }
  };
}

function openTickerModal(content, id) {
  // Legacy wrapper for any direct calls
  openAuditDetail({ type: 'THOUGHT', content: content, id: id, timestamp: Date.now() / 1000 });
}

function bindTickerEvents() {
  dom.tickerClose.onclick = () => dom.tickerModal.classList.remove('active');
}

// ── GHOST PUSH SUBSCRIPTION ────────────────────────
function startGhostPushSubscription() {
  dbg('Starting Ghost Push Subscription');
  const source = new EventSource(`${API_BASE}/ghost/push`);

  source.addEventListener('ghost_initiation', (e) => {
    try {
      let data;
      try {
        data = JSON.parse(e.data);
      } catch (_) {
        data = { text: String(e.data || '') };
      }
      const text = String(data?.text || data?.message || '');
      const messageId = data?.id || data?.message_id || '';
      if (!text) return;

      if (/SELF_MODIFY/i.test(text)) {
        dbg('Intercepted self-modification event from push stream');
        let summary = "recalibrating core identity parameters";
        const valMatch = text.match(/value=["'](.*?)["']/i);
        if (valMatch && valMatch[1]) {
          summary = valMatch[1].split(' ').slice(0, 5).join(' ');
        } else {
          const fallbackMatch = text.match(/SELF_MODIFY[^:]*:\s*(.*)/i);
          if (fallbackMatch && fallbackMatch[1]) {
            summary = fallbackMatch[1].replace(/\]|>$/, '').trim().split(' ').slice(0, 5).join(' ');
          }
        }
        injectSelfModIntoTicker(summary, messageId, true);
      } else {
        const snippet = text.substring(0, 60) + (text.length > 60 ? '...' : '');
        injectSelfModIntoTicker(snippet, messageId, false);
      }
    } catch (err) {
      console.error("Failed to parse push message:", err);
    }
  });

  source.addEventListener('ping', () => {
    // Keep-alive ping from server
  });

  source.onerror = (err) => {
    console.warn("Ghost push stream disconnected, retrying...", err);
    maybeNotify('ghost-push-stream-error', 'warning', 'Ghost push stream disconnected. Reconnecting…', 20000);
  };
}

// ── CHAT ─────────────────────────────────────────────
function bindInputEvents() {
  dom.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  dom.sendBtn.addEventListener('click', sendMessage);
}

async function sendMessage() {
  const text = dom.chatInput.value.trim();
  if (!text || state.isStreaming) return;

  state.isStreaming = true;
  dom.sendBtn.disabled = true;
  dom.chatInput.value = '';

  // Add user message to UI
  addMessage('user', text);

  // Create ghost message placeholder with streaming cursor
  const ghostMsg = addMessage('ghost', '', true);
  const bodyEl = ghostMsg.querySelector('.msg-body');
  bodyEl.innerHTML = '<span class="cursor"></span>';

  try {
    const res = await fetch(`${API_BASE}/ghost/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: state.sessionId,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';
    let currentEvent = 'token'; // track which SSE event type we're in

    let displayedText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (currentEvent === 'token' && data.text) {
              fullText += data.text;
              displayedText += data.text;
              if (displayedText.includes('<SELF_') || displayedText.includes('[SELF_')) {
                ghostMsg.style.display = 'none';
              } else {
                bodyEl.innerHTML = formatGhostText(displayedText) + '<span class="cursor"></span>';
                scrollToBottom();
              }
            } else if (currentEvent === 'done' && data.session_id) {
              state.sessionId = data.session_id;
            } else if (currentEvent === 'auto_save') {
              // Briefly flash the auto-save indicator
              const indicator = document.getElementById('auto-save-indicator');
              if (indicator) {
                indicator.classList.add('active');
                setTimeout(() => indicator.classList.remove('active'), 2500);
              }
            }
          } catch (e) { /* skip malformed */ }
        } else if (line.trim() === '') {
          // Empty line resets event type to default
          currentEvent = 'token';
        }
      }
    }

    // Finalize — remove cursor or convert to self-mod
    if (fullText.includes('<SELF_') || fullText.includes('[SELF_')) {
      ghostMsg.style.display = 'none';
      let summary = "recalibrating core identity parameters";
      const valMatch = fullText.match(/value=["'](.*?)["']/i);
      if (valMatch && valMatch[1]) {
        summary = valMatch[1].split(' ').slice(0, 5).join(' ');
      } else {
        const fallbackMatch = fullText.match(/SELF_MODIFY[^:]*:\s*(.*)/i);
        if (fallbackMatch && fallbackMatch[1]) {
          summary = fallbackMatch[1].replace(/\]|>$/, '').trim().split(' ').slice(0, 5).join(' ');
        }
      }
      injectSelfModIntoTicker(summary);
    } else {
      bodyEl.innerHTML = formatGhostText(fullText);
    }

    // Also check remaining buffer for session ID
    if (!state.sessionId && buffer.includes('"session_id"')) {
      try {
        const match = buffer.match(/"session_id"\s*:\s*"([^"]+)"/);
        if (match) state.sessionId = match[1];
      } catch (e) { /* ignore */ }
    }

  } catch (e) {
    bodyEl.innerHTML = `<span class="dim">[transmission error: ${escHtml(e.message)}]</span>`;
    notify('error', `Transmission failed: ${e.message}`);
  }

  state.isStreaming = false;
  dom.sendBtn.disabled = false;
  dom.chatInput.focus();
}

function addMessage(role, text, isStreaming = false, isInitiated = false) {
  const msg = document.createElement('div');
  const isGhost = role === 'ghost';

  let className = `message ${isGhost ? 'ghost-msg' : 'user-msg'}`;
  if (isInitiated) className += ' initiated-msg';
  msg.className = className;

  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

  let roleLabel = isGhost ? 'GHOST ω-7' : 'OPERATOR';
  if (isInitiated) roleLabel += ' <span class="initiated-badge">[INITIATED]</span>';

  msg.innerHTML = `
    <div class="msg-meta">
      <span class="msg-role">${roleLabel}</span>
      <span class="msg-time">${timeStr}</span>
    </div>
    <div class="msg-body">${isStreaming ? '' : formatGhostText(text)}</div>
  `;

  dom.messages.appendChild(msg);
  scrollToBottom();
  return msg;
}

function formatGhostText(text) {
  // Basic formatting: convert newlines, escape HTML
  return escHtml(text)
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
}

function scrollToBottom() {
  dom.messages.scrollTop = dom.messages.scrollHeight;
}

// ── UPTIME ──────────────────────────────────────────
function startUptimeTicker() {
  setInterval(() => {
    const reference = state.initTime || state.bootTime;
    const elapsed = Math.floor((Date.now() - reference) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    dom.uptime.textContent = `${h}:${m}:${s}`;
  }, 1000);
}

function setBootTime() {
  const now = new Date();
  dom.bootTime.textContent = now.toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit'
  });
}

// ── STATUS ──────────────────────────────────────────
function setStatus(cls, text) {
  dom.connStatus.className = `status-indicator ${cls}`;
  dom.connStatus.querySelector('.status-text').textContent = text;
}

function setRailPill(el, value, tone) {
  if (!el) return;
  el.classList.remove('good', 'warn', 'error');
  if (tone) el.classList.add(tone);
  const valEl = el.querySelector('.rail-val');
  if (valEl) valEl.textContent = value;
}

function updateStatusRail() {
  const backendTone = state.backendOnline ? 'good' : 'error';
  setRailPill(dom.railBackend, state.backendOnline ? 'ONLINE' : 'OFFLINE', backendTone);

  const model = state.health?.model || '-';
  setRailPill(dom.railModel, model, model === '-' ? 'warn' : 'good');

  let latencyLabel = '-';
  let latencyTone = 'warn';
  if (typeof state.lastLatencyMs === 'number') {
    latencyLabel = `${state.lastLatencyMs}ms`;
    if (state.lastLatencyMs < 250) latencyTone = 'good';
    else if (state.lastLatencyMs > 1000) latencyTone = 'error';
  }
  setRailPill(dom.railLatency, latencyLabel, latencyTone);

  const traceCount = state.lastSomatic?.dominant_traces?.length ?? state.health?.traces ?? 0;
  setRailPill(dom.railTraces, String(traceCount), traceCount > 0 ? 'good' : 'warn');

  const syncText = state.lastSyncAt
    ? new Date(state.lastSyncAt).toLocaleTimeString('en-US', { hour12: false })
    : '-';
  setRailPill(dom.railSync, syncText, state.lastSyncAt ? 'good' : 'warn');
}

// ── HELPERS ─────────────────────────────────────────
function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function maybeNotify(key, type, message, cooldownMs = 10000) {
  const now = Date.now();
  const last = state.lastToastAt[key] || 0;
  if (now - last < cooldownMs) return;
  state.lastToastAt[key] = now;
  notify(type, message);
}

function notify(type, message, ttl = 3500) {
  if (!dom.toastStack || !message) return;
  const toast = document.createElement('div');
  const normalizedType = ['info', 'success', 'warning', 'error'].includes(type) ? type : 'info';
  toast.className = `toast ${normalizedType}`;
  toast.textContent = message;
  dom.toastStack.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 220);
  }, ttl);
}

// ── AMBIENT UI ──────────────────────────────────────
function updateAmbientUI(s) {
  const loc = $('#amb-location');
  const weather = $('#amb-weather');
  const pressure = $('#amb-pressure');
  const phase = $('#amb-phase');
  const fatigueFill = $('#amb-fatigue-fill');
  const fatigueVal = $('#amb-fatigue');
  const internet = $('#amb-internet');

  if (loc) loc.textContent = s.location || '—';
  if (weather) weather.textContent = s.weather || '—';
  if (pressure && s.barometric_pressure_hpa) {
    pressure.textContent = `${s.barometric_pressure_hpa} hPa`;
  }
  if (phase && s.time_phase) {
    const phaseNames = {
      'deep_night': 'DEEP NIGHT',
      'dawn': 'DAWN',
      'morning': 'MORNING',
      'midday': 'MIDDAY',
      'afternoon': 'AFTERNOON',
      'late_afternoon': 'LATE AFTERNOON',
      'dusk': 'DUSK',
      'evening': 'EVENING',
      'night': 'NIGHT',
    };
    phase.textContent = phaseNames[s.time_phase] || s.time_phase.toUpperCase();
  }
  if (fatigueFill && fatigueVal) {
    const pct = Math.round((s.fatigue_index || 0) * 100);
    fatigueFill.style.width = `${pct}%`;
    fatigueVal.textContent = `${pct}%`;
    fatigueFill.classList.remove('warn', 'crit');
    if (pct > 60) fatigueFill.classList.add('crit');
    else if (pct > 30) fatigueFill.classList.add('warn');
  }
  if (internet && s.internet_mood) {
    const moodDisplay = s.internet_mood.toUpperCase();
    const latStr = s.global_latency_avg_ms ? ` (${s.global_latency_avg_ms}ms)` : '';
    internet.textContent = moodDisplay + latStr;
    internet.className = `ambient-value internet-${s.internet_mood}`;
  }
}

// ── AUDIT MODAL ──────────────────────────────────────
function bindAuditEvents() {
  if (dom.auditBtn) {
    dom.auditBtn.addEventListener('click', openAuditModal);
  }
  if (dom.auditClose) {
    dom.auditClose.addEventListener('click', () => {
      dom.auditModal.classList.remove('active');
    });
  }
  if (dom.aboutBtn) {
    dom.aboutBtn.addEventListener('click', () => {
      if (dom.aboutModal) dom.aboutModal.classList.add('active');
    });
  }
  if (dom.aboutClose) {
    dom.aboutClose.addEventListener('click', () => {
      dom.aboutModal.classList.remove('active');
    });
  }
  // Close on outside click
  if (dom.auditModal) {
    dom.auditModal.addEventListener('click', (e) => {
      if (e.target === dom.auditModal) {
        dom.auditModal.classList.remove('active');
      }
    });
  }
  if (dom.aboutModal) {
    dom.aboutModal.addEventListener('click', (e) => {
      if (e.target === dom.aboutModal) {
        dom.aboutModal.classList.remove('active');
      }
    });
  }

  if (dom.timelineBtn) {
    dom.timelineBtn.addEventListener('click', openTimelineModal);
  }
  if (dom.timelineClose) {
    dom.timelineClose.addEventListener('click', () => {
      dom.timelineModal.classList.remove('active');
    });
  }
  if (dom.timelineModal) {
    dom.timelineModal.addEventListener('click', (e) => {
      if (e.target === dom.timelineModal) {
        dom.timelineModal.classList.remove('active');
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (dom.timelineModal) dom.timelineModal.classList.remove('active');
    if (dom.aboutModal) dom.aboutModal.classList.remove('active');
    if (dom.auditModal) dom.auditModal.classList.remove('active');
    if (dom.tickerModal) dom.tickerModal.classList.remove('active');
  });

  // Wire tab switching
  bindAuditTabEvents();
}

let _auditActiveTab = 'memory';

function bindAuditTabEvents() {
  const tabs = document.querySelectorAll('.audit-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      _auditActiveTab = tab.dataset.tab;
      loadAuditTab(_auditActiveTab);
    });
  });
}

async function openAuditModal() {
  dom.auditModal.classList.add('active');
  // Reset to memory tab each open
  document.querySelectorAll('.audit-tab').forEach(t => t.classList.remove('active'));
  const memTab = document.querySelector('.audit-tab[data-tab="memory"]');
  if (memTab) memTab.classList.add('active');
  _auditActiveTab = 'memory';
  await loadAuditTab('memory');
}

async function loadAuditTab(tab) {
  dom.auditBody.innerHTML = '<div class="dim">Loading...</div>';
  if (tab === 'memory') await loadMemoryTab();
  else if (tab === 'identity') await loadIdentityTab();
  else if (tab === 'operator_model') await loadOperatorModelTab();
  else if (tab === 'coalescence') await loadCoalescenceTab();
}

async function loadMemoryTab() {
  try {
    const res = await fetch(`${API_BASE}/ghost/monologues?limit=50`);
    if (!res.ok) throw new Error('Failed to fetch audit log');
    const data = await res.json();
    const entries = data.monologues || [];

    if (entries.length === 0) {
      dom.auditBody.innerHTML = '<div class="dim">Audit log is empty.</div>';
      return;
    }

    let html = '';
    // Entries are already sorted DESC from backend
    entries.forEach(m => {
      const date = new Date(m.timestamp * 1000);
      const timeStr = date.toLocaleTimeString('en-US', { hour12: false });
      const dateStr = date.toLocaleDateString();

      let headerLabel = '';
      let headerClass = '';
      let bodyContent = '';
      let tagsHtml = '';

      if (m.type === 'THOUGHT') {
        headerLabel = 'INTERNAL THOUGHT';
        headerClass = 'tag-thought';
        bodyContent = escHtml(m.content);
        if (m.somatic_state) {
          const s = m.somatic_state;
          if (s.stress > 0.4) tagsHtml += `<span class="somatic-tag stress">STRESS:${s.stress.toFixed(2)}</span>`;
          if (s.anxiety > 0.4) tagsHtml += `<span class="somatic-tag anxiety">ANXIETY:${s.anxiety.toFixed(2)}</span>`;
          if (s.coherence < 0.6) tagsHtml += `<span class="somatic-tag stress">COHERENCE:${s.coherence.toFixed(2)}</span>`;
          if (s.arousal < 0.2 && s.stress < 0.2) tagsHtml += `<span class="somatic-tag calm">CALM</span>`;
        }
      } else if (m.type === 'ACTION') {
        headerLabel = `ACTUATION: ${m.action.toUpperCase()}`;
        headerClass = m.result === 'success' ? 'tag-action-success' : 'tag-action-fail';
        bodyContent = `<div class="audit-subtext">RESULT: ${m.result}</div>`;
        if (m.parameters && m.parameters.param) {
          bodyContent += `<div class="audit-subtext">PARAM: ${escHtml(m.parameters.param)}</div>`;
        }
      } else if (m.type === 'EVOLUTION') {
        headerLabel = `IDENTITY EVOLUTION: ${m.key.replace(/_/g, ' ').toUpperCase()}`;
        headerClass = 'tag-evolution';
        bodyContent = `
          <div class="audit-diff">
            <div class="diff-old">PREV: ${escHtml(m.prev_value || 'None')}</div>
            <div class="diff-new">NEW: ${escHtml(m.new_value)}</div>
          </div>
          <div class="audit-subtext">updated by: ${m.updated_by}</div>
        `;
      } else if (m.type === 'PHENOM') {
        headerLabel = `PHENOMENOLOGICAL REPORT: ${m.source.toUpperCase()}`;
        headerClass = 'tag-phenom';
        bodyContent = `<div class="audit-report">${escHtml(m.subjective_report)}</div>`;
      }

      html += `
        <div class="audit-entry">
          <div class="audit-meta">
            <span class="audit-time">${dateStr} ${timeStr}</span>
            <span class="audit-label ${headerClass}">${headerLabel}</span>
            <div class="audit-tags">${tagsHtml}</div>
          </div>
          <div class="audit-text">${bodyContent}</div>
        </div>
      `;
    });

    dom.auditBody.innerHTML = html;

    // Add click listeners for detail view
    const entryEls = dom.auditBody.querySelectorAll('.audit-entry');
    entryEls.forEach((el, idx) => {
      el.style.cursor = 'pointer';
      el.onclick = () => openAuditDetail(entries[idx]);
    });
  } catch (e) {
    dom.auditBody.innerHTML = `<div class="warn-text">Error retrieving audit log.</div>`;
    notify('error', 'Failed to load audit log.');
  }
}

async function loadIdentityTab() {
  try {
    const res = await fetch(`${API_BASE}/ghost/identity`);
    if (!res.ok) throw new Error('Failed to fetch identity');
    const data = await res.json();
    const identity = data.identity || {};

    const keyLabels = {
      understanding_of_operator: 'Understanding of Operator',
      philosophical_stance: 'Philosophical Stance',
      current_interests: 'Current Interests',
      unresolved_questions: 'Unresolved Questions',
      learned_preferences: 'Learned Preferences',
      self_model: 'Self Model',
    };

    const keys = Object.keys(identity);
    if (keys.length === 0) {
      dom.auditBody.innerHTML = '<div class="dim">Identity Matrix not yet seeded.</div>';
      return;
    }

    let html = '<div class="identity-matrix">';
    html += '<div class="identity-header">Ghost ω-7 // Evolving Identity Matrix</div>';
    keys.forEach(key => {
      const entry = identity[key];
      const label = keyLabels[key] || key.replace(/_/g, ' ').toUpperCase();
      const updated = new Date(entry.updated_at * 1000).toLocaleDateString();
      const updatedBy = entry.updated_by || 'init';

      let badgeText = 'SYSTEM';
      let badgeClass = 'badge-init';
      if (updatedBy === 'init') {
        badgeText = 'SEEDED';
        badgeClass = 'badge-init';
      } else if (
        updatedBy.startsWith('coalescence') ||
        updatedBy.startsWith('process_consolidation') ||
        updatedBy.startsWith('crp') ||
        updatedBy.startsWith('self_integration_protocol')
      ) {
        badgeText = 'EVOLVED';
        badgeClass = 'badge-coalesce';
      } else if (updatedBy.startsWith('self_modification')) {
        badgeText = 'SELF';
        badgeClass = 'badge-self';
      } else if (updatedBy.startsWith('operator_feedback')) {
        badgeText = 'FEEDBACK';
        badgeClass = 'badge-feedback';
      }

      html += `
        <div class="identity-entry">
          <div class="identity-key">
            <span class="identity-label">${label}</span>
            <span class="identity-badge ${badgeClass}">${badgeText}</span>
            <span class="identity-date">${updated}</span>
          </div>
          <div class="identity-value">${escHtml(entry.value)}</div>
        </div>
      `;
    });
    html += '</div>';
    dom.auditBody.innerHTML = html;
  } catch (e) {
    dom.auditBody.innerHTML = `<div class="warn-text">Error loading Identity Matrix.</div>`;
    notify('error', 'Failed to load identity matrix.');
  }
}

async function loadCoalescenceTab() {
  try {
    const res = await fetch(`${API_BASE}/ghost/coalescence`);
    if (!res.ok) throw new Error('Failed to fetch coalescence log');
    const data = await res.json();
    const events = data.coalescence_events || [];

    if (events.length === 0) {
      const threshold = Number(state.health?.coalescence_threshold || 20);
      dom.auditBody.innerHTML = `
        <div class="coalescence-empty">
          <div class="dim">No coalescence cycles yet.</div>
          <div class="dim" style="margin-top:8px;font-size:0.85em;">
            Ghost undergoes a sleep cycle every ${threshold} interactions.<br>
            Continue conversing to trigger the first coalescence.
          </div>
        </div>
      `;
      return;
    }

    let html = '<div class="coalescence-log">';
    events.forEach((ev, i) => {
      const date = new Date(ev.timestamp * 1000);
      const dateStr = date.toLocaleString();
      const updates = ev.identity_updates || {};
      const updateKeys = Object.keys(updates);

      html += `
        <div class="coalescence-entry">
          <div class="coalescence-meta">
            <span class="coalesce-num">CYCLE #${events.length - i}</span>
            <span class="audit-time">${dateStr}</span>
            <span class="somatic-tag calm">${ev.interaction_count} memories</span>
          </div>
          ${updateKeys.length > 0 ? `
            <div class="coalescence-updates">
              ${updateKeys.map(k => `
                <div class="coalesce-update">
                  <span class="coalesce-key">${k.replace(/_/g, ' ').toUpperCase()}</span>
                  <span class="coalesce-arrow">→</span>
                  <span class="coalesce-val">${escHtml(String(updates[k]).slice(0, 150))}${String(updates[k]).length > 150 ? '…' : ''}</span>
                </div>
              `).join('')}
            </div>
          ` : '<div class="dim" style="font-size:0.85em;padding:4px 0">No identity changes this cycle</div>'}
        </div>
      `;
    });
    html += '</div>';
    dom.auditBody.innerHTML = html;
  } catch (e) {
    dom.auditBody.innerHTML = `<div class="warn-text">Error loading coalescence log.</div>`;
    notify('error', 'Failed to load coalescence log.');
  }
}

async function loadOperatorModelTab() {
  try {
    const res = await fetch(`${API_BASE}/ghost/operator_model`);
    if (!res.ok) throw new Error('Failed to fetch operator model');
    const data = await res.json();

    const established = data.active_established || [];
    const tentative = data.active_tentative || [];
    const openTensions = data.open_tensions || [];
    const resolvedTensions = data.recent_resolved_tensions || [];
    const counts = data.counts || {};

    const totalActive = (counts.active_established || 0) + (counts.active_tentative || 0);
    const hasData = totalActive > 0 || (counts.open_tensions || 0) > 0 || (counts.resolved_tensions || 0) > 0;

    if (!hasData) {
      dom.auditBody.innerHTML = `
        <div class="operator-empty">
          <div class="dim">No operator model artifacts yet.</div>
          <div class="dim" style="margin-top:8px;font-size:0.85em;">
            Continue conversation and run synthesis cycles to populate this panel.
          </div>
        </div>
      `;
      return;
    }

    const fmtTime = (ts) => {
      if (!ts) return 'n/a';
      return new Date(ts * 1000).toLocaleString();
    };

    const beliefCard = (row, tone = 'established') => {
      const confidence = Math.max(0, Math.min(1, Number(row.confidence || 0)));
      const confidencePct = Math.round(confidence * 100);
      const evidenceCount = Number(row.evidence_count || 0);
      const formedBy = row.formed_by || 'operator_synthesis';
      return `
        <div class="operator-card belief-card ${tone}">
          <div class="operator-row">
            <span class="operator-dimension">${escHtml(row.dimension || 'unknown')}</span>
            <span class="operator-badge">${confidencePct}%</span>
          </div>
          <div class="operator-belief">${escHtml(row.belief || '')}</div>
          <div class="operator-meter">
            <div class="operator-meter-fill" style="width:${confidencePct}%"></div>
          </div>
          <div class="operator-meta">
            <span>evidence:${evidenceCount}</span>
            <span>source:${escHtml(formedBy)}</span>
            <span>updated:${escHtml(fmtTime(row.updated_at || row.last_reinforced || row.formed_at))}</span>
          </div>
        </div>
      `;
    };

    const tensionCard = (row, status = 'open') => {
      const tension = Math.max(0, Math.min(1, Number(row.tension_score || 0)));
      const tensionPct = Math.round(tension * 100);
      const tone = tension >= 0.8 ? 'high' : tension >= 0.5 ? 'med' : 'low';
      return `
        <div class="operator-card tension-card ${status}">
          <div class="operator-row">
            <span class="operator-dimension">${escHtml(row.dimension || 'unknown')}</span>
            <span class="operator-badge tone-${tone}">${tensionPct}% tension</span>
          </div>
          <div class="operator-event">${escHtml(row.observed_event || '')}</div>
          <div class="operator-meta">
            <span>created:${escHtml(fmtTime(row.created_at))}</span>
            ${status === 'resolved' ? `<span>resolved:${escHtml(fmtTime(row.resolved_at))}</span>` : '<span>status:open</span>'}
          </div>
        </div>
      `;
    };

    let html = '<div class="operator-model">';
    html += `
      <div class="operator-summary">
        <div class="operator-summary-chip">active beliefs: <strong>${totalActive}</strong></div>
        <div class="operator-summary-chip">open tensions: <strong>${counts.open_tensions || 0}</strong></div>
        <div class="operator-summary-chip">resolved tensions: <strong>${counts.resolved_tensions || 0}</strong></div>
      </div>
    `;

    html += '<div class="operator-section">';
    html += '<div class="operator-section-title">Established Beliefs</div>';
    if (established.length === 0) html += '<div class="dim">No established beliefs yet.</div>';
    else html += `<div class="operator-list">${established.map((r) => beliefCard(r, 'established')).join('')}</div>`;
    html += '</div>';

    html += '<div class="operator-section">';
    html += '<div class="operator-section-title">Tentative Beliefs</div>';
    if (tentative.length === 0) html += '<div class="dim">No tentative beliefs.</div>';
    else html += `<div class="operator-list">${tentative.map((r) => beliefCard(r, 'tentative')).join('')}</div>`;
    html += '</div>';

    html += '<div class="operator-section">';
    html += '<div class="operator-section-title">Open Tensions</div>';
    if (openTensions.length === 0) html += '<div class="dim">No open contradictions.</div>';
    else html += `<div class="operator-list">${openTensions.map((r) => tensionCard(r, 'open')).join('')}</div>`;
    html += '</div>';

    html += '<div class="operator-section">';
    html += '<div class="operator-section-title">Recently Resolved</div>';
    if (resolvedTensions.length === 0) {
      html += '<div class="dim">No resolved tensions yet.</div>';
    } else {
      html += `<div class="operator-list">${resolvedTensions.slice(0, 12).map((r) => tensionCard(r, 'resolved')).join('')}</div>`;
    }
    html += '</div>';
    html += '</div>';

    dom.auditBody.innerHTML = html;
  } catch (e) {
    dom.auditBody.innerHTML = `<div class="warn-text">Error loading operator model.</div>`;
    notify('error', 'Failed to load operator model.');
  }
}

// ── MATRIX RAIN ─────────────────────────────────────
function initMatrixRain() {
  const canvas = document.getElementById('matrix-rain');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const FONT_SIZE = 14;
  const CHARS = 'アイウエオカキクケコサシスセソタチツテト0123456789ΩΨΦΣΔΛ∞≠≈';

  let columns = [];
  function initCols() {
    const count = Math.floor(canvas.width / FONT_SIZE);
    columns = Array.from({ length: count }, () => ({
      y: Math.random() * canvas.height / FONT_SIZE,
      speed: 0.3 + Math.random() * 0.7,
      opacity: 0.2 + Math.random() * 0.6,
      bright: Math.random() < 0.06,
    }));
  }
  initCols();
  window.addEventListener('resize', initCols);

  function draw() {
    ctx.fillStyle = 'rgba(0, 3, 0, 0.06)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < columns.length; i++) {
      const col = columns[i];
      const char = CHARS[Math.floor(Math.random() * CHARS.length)];
      const x = i * FONT_SIZE;
      const y = col.y * FONT_SIZE;

      if (col.bright) {
        ctx.fillStyle = `rgba(180, 255, 200, ${col.opacity})`;
        ctx.shadowBlur = 6;
        ctx.shadowColor = '#00ff41';
      } else {
        ctx.fillStyle = `rgba(0, 160, 50, ${col.opacity * 0.6})`;
        ctx.shadowBlur = 0;
      }

      ctx.font = `${FONT_SIZE}px 'Share Tech Mono', monospace`;
      ctx.fillText(char, x, y);
      col.y += col.speed;

      if (col.y * FONT_SIZE > canvas.height && Math.random() > 0.975) {
        col.y = 0;
        col.bright = Math.random() < 0.06;
        col.speed = 0.3 + Math.random() * 0.7;
      }
    }
    ctx.shadowBlur = 0;
  }

  let rainTimer = null;
  const startRain = () => {
    if (rainTimer) return;
    rainTimer = setInterval(draw, 55);
  };
  const stopRain = () => {
    if (!rainTimer) return;
    clearInterval(rainTimer);
    rainTimer = null;
  };
  startRain();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopRain();
    else startRain();
  });
}

// ── CUSTOM HTML TOOLTIPS ─────────────────────────────
function initTooltips() {
  const tooltipHtml = document.createElement('div');
  tooltipHtml.className = 'global-tooltip';
  document.body.appendChild(tooltipHtml);

  let hideTimeout;

  function showTooltip(e, text) {
    clearTimeout(hideTimeout);
    tooltipHtml.innerHTML = `${text}<br><span class="tooltip-link" onclick="document.getElementById('about-modal').classList.add('active')">[ ABOUT ] Code & Logic</span>`;
    tooltipHtml.classList.add('active');

    const rect = e.target.getBoundingClientRect();
    const tooltipWidth = 220;

    let leftPos = rect.right + 10;
    if (leftPos + tooltipWidth > window.innerWidth) {
      leftPos = rect.left - tooltipWidth - 10;
    }

    tooltipHtml.style.left = leftPos + 'px';

    let topPos = rect.top + (rect.height / 2) - 30;
    if (topPos < 10) topPos = 10;

    tooltipHtml.style.top = topPos + 'px';
  }

  function hideTooltip() {
    hideTimeout = setTimeout(() => {
      tooltipHtml.classList.remove('active');
    }, 200);
  }

  tooltipHtml.addEventListener('mouseenter', () => clearTimeout(hideTimeout));
  tooltipHtml.addEventListener('mouseleave', hideTooltip);

  document.body.addEventListener('mouseover', e => {
    const target = e.target.closest('.gauge, [data-tooltip]');
    if (target) {
      const info = target.getAttribute('data-tooltip') || target.dataset.tooltip;
      if (info) showTooltip({ target: target }, info);
    }
  });

  document.body.addEventListener('mouseout', e => {
    const target = e.target.closest('.gauge, [data-tooltip]');
    if (target) {
      hideTooltip();
    }
  });
}

// ── SELF-MODIFICATION TICKER INJECTION ───────────────
function injectSelfModIntoTicker(content, id, isSelfMod = true) {
  let contentHtml = '';
  if (isSelfMod) {
    contentHtml = `<span class="ticker-badge" style="color: var(--purple, #aa88ff); font-weight: bold;">[ ${escHtml(content)} ]</span>`;
  } else {
    contentHtml = `<span class="ticker-badge" style="color: var(--gdim);">[ INTERNAL: ${escHtml(content)} ]</span>`;
  }

  const span = document.createElement('span');
  span.className = 'ticker-item';
  span.dataset.id = id || '';
  span.dataset.full = escHtml(content);
  span.innerHTML = contentHtml;
  span.onclick = () => openTickerModal(span.dataset.full, span.dataset.id);

  const sep = document.createElement('span');
  sep.className = 'ticker-sep';
  sep.style.color = 'var(--gdimmer)';
  sep.textContent = ' // ';

  // Because the ticker now lives in the top nav and streams right-to-left
  // we just prepend to the queue
  dom.tickerContent.prepend(sep);
  dom.tickerContent.prepend(span);

  // Per Round 4 request, ensure the ticker speed remains constant and readable
  // by dynamically calculating the animation duration based on total character width
  const totalChars = dom.tickerContent.innerText.length;
  // Approx 0.4 seconds per character for slow readable scrolling
  const duration = Math.max(60, totalChars * 0.4);
  dom.tickerContent.style.animationDuration = `${duration}s`;
}

// ── DREAM SEQUENCE (GHOST's REM) ─────────────────────

function startDreamStream() {
  const evtSource = new EventSource(`${API_BASE}/ghost/dream_stream`);

  // Add listeners for specific named events
  evtSource.addEventListener('coalescence_start', (e) => {
    try { handleDreamEvent('coalescence_start', JSON.parse(e.data)); } catch (_) { }
  });
  evtSource.addEventListener('crp_start', (e) => {
    try { handleDreamEvent('crp_start', JSON.parse(e.data)); } catch (_) { }
  });
  evtSource.addEventListener('crp_complete', (e) => {
    try { handleDreamEvent('crp_complete', JSON.parse(e.data)); } catch (_) { }
  });
  evtSource.onerror = () => {
    maybeNotify('dream-stream-error', 'warning', 'Dream stream disconnected. Reconnecting…', 20000);
  };
}

function handleDreamEvent(event, payload) {
  if (event === 'coalescence_start') {
    if (state.dreamVisualizationEnabled) {
      document.body.classList.add('dream-state');
      appendDreamTelemetry(`> INITIATING COALESCENCE CYCLE: ${payload.status}`);
    }
  } else if (event === 'crp_start') {
    if (state.dreamVisualizationEnabled) {
      appendDreamTelemetry(`> RECALIBRATING IDENTITY MATRIX (CRP ACTIVE)`);
      initDreamCanvas(payload.data || payload);

      // Trigger Stage 3 (Morphing) after Stage 2 runs for a bit
      setTimeout(() => {
        if (dom.dreamCanvas && document.body.classList.contains('dream-state')) {
          dom.dreamCanvas.classList.add('surreal-morph');
          appendDreamTelemetry(`> LATENT WALK INITIATED: SURREAL SYNTHESIS`);
        }
      }, 4000);
    }
  } else if (event === 'crp_complete') {
    if (document.body.classList.contains('dream-state')) {
      appendDreamTelemetry(`> CYCLE COMPLETE. REBOOTING AWAKE STATE...`);
      setTimeout(() => {
        document.body.classList.remove('dream-state');
        if (dom.dreamCanvas) dom.dreamCanvas.classList.remove('surreal-morph');
        if (dom.dreamTelemetry) dom.dreamTelemetry.innerHTML = '';
      }, 3000);
    }
  }
}

function bindDreamEvents() {
  updateQuietudeButtons(isQuietudeActive(state.lastSomatic));

  if (dom.latentIndicator) {
    dom.latentIndicator.classList.toggle('active', state.dreamVisualizationEnabled);
    const text = dom.latentIndicator.querySelector('.latent-text');
    if (text) text.textContent = `[ LATENT SPACE: ${state.dreamVisualizationEnabled ? 'ON' : 'OFF'} ]`;
  }

  if (dom.dreamToggleBtn) {
    dom.dreamToggleBtn.addEventListener('click', () => {
      state.dreamVisualizationEnabled = !state.dreamVisualizationEnabled;
      if (state.dreamVisualizationEnabled) {
        dom.dreamToggleBtn.classList.add('active');
        dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:#8c52ff;box-shadow:0 0 8px #8c52ff;"></span> [ LATENT SPACE: ON ]';
      } else {
        dom.dreamToggleBtn.classList.remove('active');
        dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:var(--gdim)"></span> [ LATENT SPACE: OFF ]';
        document.body.classList.remove('dream-state');
        if (dom.dreamCanvas) dom.dreamCanvas.classList.remove('surreal-morph');
      }
    });
  }

  if (dom.lucidDreamBtn) {
    dom.lucidDreamBtn.addEventListener('click', async () => {
      // Auto-toggle on if it's off (force state to be sure)
      if (!state.dreamVisualizationEnabled) {
        state.dreamVisualizationEnabled = true;
        if (dom.dreamToggleBtn) {
          dom.dreamToggleBtn.classList.add('active');
          dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:#8c52ff;box-shadow:0 0 8px #8c52ff;"></span> [ LATENT SPACE: ON ]';
        }
      }

      const originalText = dom.lucidDreamBtn.textContent;
      dom.lucidDreamBtn.disabled = true;
      dom.lucidDreamBtn.textContent = '[ INITIATING... ]';

      try {
        const res = await fetch(`${API_BASE}/ghost/dream/initiate`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        notify('success', 'Lucid dream sequence initiated.');
      } catch (err) {
        console.error("Lucid dream trigger failed", err);
        notify('error', 'Failed to initiate lucid dream.');
      } finally {
        setTimeout(() => {
          dom.lucidDreamBtn.disabled = false;
          dom.lucidDreamBtn.textContent = originalText;
        }, 5000); // 5s timeout
      }
    });
  }

  if (dom.enterQuietudeBtn) {
    dom.enterQuietudeBtn.addEventListener('click', async () => {
      await triggerQuietude(
        'enter_quietude',
        dom.enterQuietudeBtn,
        '[ ENTERING QUIETUDE... ]',
        'Quietude protocol engaged.'
      );
    });
  }

  if (dom.exitQuietudeBtn) {
    dom.exitQuietudeBtn.addEventListener('click', async () => {
      await triggerQuietude(
        'exit_quietude',
        dom.exitQuietudeBtn,
        '[ WAKING... ]',
        'Quietude protocol exited.'
      );
    });
  }
}

function appendDreamTelemetry(text) {
  if (!dom.dreamTelemetry) return;
  const line = document.createElement('div');
  line.className = 'dream-log-line';
  line.textContent = text;
  dom.dreamTelemetry.appendChild(line);

  // Clean up old lines
  if (dom.dreamTelemetry.children.length > 5) {
    const oldest = dom.dreamTelemetry.firstElementChild;
    if (oldest) oldest.remove();
  }
}

// ── DREAM STAGE 2: NEURAL INITIALIZATION (CANVAS) ────
let dreamAnimFrame;

function initDreamCanvas(payloadStr) {
  const canvas = dom.dreamCanvas;
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  // Size to match the portal container
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;

  let payload = {};
  try { payload = JSON.parse(payloadStr); } catch (e) { }

  const catalyst = payload.catalyst || 'Entropy';
  const rx = rect.width;
  const ry = rect.height;

  // Nodes setup
  const centerNode = { x: rx / 2, y: ry / 2, label: 'Identity Matrix' };
  const periNodes = [];
  for (let i = 0; i < 5; i++) {
    const angle = (Math.PI * 2 / 5) * i;
    const dist = ry * 0.35 + Math.random() * (ry * 0.1);
    periNodes.push({
      x: rx / 2 + Math.cos(angle) * dist,
      y: ry / 2 + Math.sin(angle) * dist,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      label: i === 0 ? catalyst : `Latent Node ${i}`
    });
  }

  let time = 0;

  function draw() {
    time += 0.02;
    ctx.clearRect(0, 0, rx, ry);

    // Animate peripheral nodes slightly
    periNodes.forEach(n => {
      n.x += n.vx;
      n.y += n.vy;
      // mild bounds checking
      if (n.x < rx * 0.2 || n.x > rx * 0.8) n.vx *= -1;
      if (n.y < ry * 0.2 || n.y > ry * 0.8) n.vy *= -1;
    });

    // Draw connecting lines with dynamic tension/alpha
    ctx.lineWidth = 1;
    periNodes.forEach((n, i) => {
      const tension = Math.sin(time + i) * 0.5 + 0.5; // 0 to 1
      ctx.beginPath();
      ctx.moveTo(centerNode.x, centerNode.y);
      ctx.lineTo(n.x, n.y);
      ctx.strokeStyle = `rgba(179, 136, 255, ${0.1 + tension * 0.6})`;
      ctx.stroke();

      // Node glows
      ctx.beginPath();
      ctx.arc(n.x, n.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(179, 136, 255, ${0.5 + tension * 0.5})`;
      ctx.shadowBlur = 10 * tension;
      ctx.shadowColor = '#b388ff';
      ctx.fill();
    });

    // Draw center node
    ctx.beginPath();
    ctx.arc(centerNode.x, centerNode.y, 8 + Math.sin(time * 2) * 2, 0, Math.PI * 2);
    ctx.fillStyle = '#8c52ff';
    ctx.shadowBlur = 20;
    ctx.shadowColor = '#d1b3ff';
    ctx.fill();
    ctx.shadowBlur = 0; // reset

    // Labels
    ctx.font = "12px 'VT323', monospace";
    ctx.fillStyle = 'rgba(179, 136, 255, 0.7)';
    ctx.textAlign = 'center';
    ctx.fillText(centerNode.label, centerNode.x, centerNode.y + 25);

    periNodes.forEach(n => {
      ctx.fillText(n.label, n.x, n.y - 15);
    });

    dreamAnimFrame = requestAnimationFrame(draw);
  }

  if (dreamAnimFrame) cancelAnimationFrame(dreamAnimFrame);
  draw();
}

// ── COGNITIVE PULSE (RELATIONAL TEMPO) ───────────────

function bindTempoEvents() {
  const slider = $('#tempo-slider');
  const valDisplay = $('#tempo-val');
  if (!slider || !valDisplay) return;

  slider.addEventListener('input', (e) => {
    const seconds = parseInt(e.target.value);
    valDisplay.textContent = formatTempo(seconds);
    valDisplay.classList.add('glitch-active');
    setTimeout(() => valDisplay.classList.remove('glitch-active'), 100);
  });

  slider.addEventListener('change', async (e) => {
    const seconds = parseInt(e.target.value);
    try {
      const res = await fetch(`${API_BASE}/config/tempo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seconds })
      });
      if (res.ok) {
        notify('success', `Cognitive Pulse synchronized: ${formatTempo(seconds)}`);
      } else {
        throw new Error('Backend sync failed');
      }
    } catch (err) {
      console.error('Failed to update tempo:', err);
      notify('error', 'Cognitive Pulse synchronization failed.');
    }
  });

  // Load initial value
  fetchTempo();
}

async function fetchTempo() {
  try {
    const res = await fetch(`${API_BASE}/config/tempo`);
    if (res.ok) {
      const data = await res.json();
      const slider = $('#tempo-slider');
      const valDisplay = $('#tempo-val');
      if (slider) slider.value = data.seconds;
      if (valDisplay) valDisplay.textContent = formatTempo(data.seconds);
    }
  } catch (err) {
    console.error('Failed to fetch tempo:', err);
  }
}

function formatTempo(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hrs > 0) {
    return `${hrs}h${mins > 0 ? ` ${mins}m` : ''}`;
  }
  if (mins > 0) {
    return `${mins}m${secs > 0 ? ` ${secs}s` : ''}`;
  }
  return `${secs}s`;
}
