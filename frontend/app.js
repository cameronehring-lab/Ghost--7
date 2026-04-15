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
  dreamVisualizationEnabled: true,
  hallucinationPortalTimeout: null,
  health: null,
  backendOnline: false,
  llmDegradedNotified: false,
  lastLatencyMs: null,
  lastSyncAt: null,
  lastSomaticFetchAt: 0,
  lastHealthFetchAt: 0,
  lastMonologuesFetchAt: 0,
  somaticFetchInFlight: false,
  somaticStale: false,
  somaticFailCount: 0,
  somaticFailureNotified: false,
  lastToastAt: {},
  bootOverlayHidden: false,
  quietudeRequestInFlight: false,
  lastProprioGateState: null,
  lastProprioTransitionFetchAt: 0,
  proprioTransitionsInFlight: false,
  proprioTransitions: [],
  proprioTransitionFailureNotified: false,
  proprioQuality: null,
  proprioQualityInFlight: false,
  lastProprioQualityFetchAt: 0,
  autonomyWatchdogState: null,
  autonomyWatchdogHistory: [],
  autonomyWatchdogInFlight: false,
  lastAutonomyWatchdogFetchAt: 0,
  autonomyWatchdogFailureNotified: false,
  predictiveState: null,
  predictiveInFlight: false,
  predictiveFetchAt: 0,
  predictiveFailureNotified: false,
  governanceState: null,
  governanceInFlight: false,
  governanceFetchAt: 0,
  governanceFailureNotified: false,
  behaviorSummary: null,
  behaviorInFlight: false,
  behaviorFetchAt: 0,
  behaviorFailureNotified: false,
  governanceQueueRows: { pending: [], recent: [] },
  governanceQueueInFlight: false,
  governanceQueueFetchAt: 0,
  governanceQueueFailureNotified: false,
  observerLatest: null,
  isAuthorized: false,
  opsUnlocked: false,
  opsCode: '',
  opsMode: 'reports',
  opsWindow: 'daily',
  opsSelectedRelPath: '',
  ttsEnabled: false,
  lastVoiceToggleAt: 0,
  sttSupported: false,
  sttListening: false,
  lastSpeechInputToggleAt: 0,
  voiceVolume: 0.82,
  rateOverride: 0.88,
  pitchOverride: 1.12,
  carrierFreqOverride: 420,
  eerieFactorOverride: 1.25,
  sessionsEntries: [],
  sessionsLoading: false,
  sessionLineage: null,
  rolodexEntries: [],
  rolodexSelectedKey: '',
  rolodexActiveTab: 'persons',
  rolodexFilter: '',
  rolodexIncludeArchived: false,
  rolodexActionBusy: false,
  rolodexWorld: null,
  rolodexPollTimer: null,
  rolodexPollBusy: false,
  rolodexDiagnostics: {
    mode: 'unknown',
    failures: null,
    integrity: null,
    updatedAt: 0,
  },
  topologyDistanceMultiplier: 1.0,
  topologyChargeStrength: -400,
  topologyModalOpen: false,
  topologyPollTimer: null,
  topologyPollBusy: false,
  topologyRetryTimer: null,
  topologySelectedNodeId: '',
  topologyPayload: null,
  topologyInspectorVisible: false,
  topologySearchTerm: '',
  contactStatus: null,
  contactStatusFetchAt: 0,
  contactStatusFailureNotified: false,
  spontaneityMultiplier: 1.0,
  aboutContent: null,
  aboutLoading: false,
  aboutLoadError: '',
  aboutActiveTab: 'overview',
  aboutQuery: '',
  morpheus: {
    active: false,
    runId: '',
    phase: 'idle',
    branchColor: '',
    branchInput: '',
    depth: 'standard',
    choiceLocked: false,
    floodTimer: null,
    choiceRevealTimer: null,
    branchTimer: null,
    terminalOpen: false,
    terminalStreaming: false,
    rewardAnimationTimer: null,
    clueFound: false,
    secretProgressPreserved: false,
  },
  attachedImage: null,
};
const FRONTEND_BUILD = '8119';
console.info(`OMEGA frontend build ${FRONTEND_BUILD}`);

const API_BASE = (() => {
  const { protocol, hostname, port } = window.location;
  const isLoopback = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
  if (isLoopback && port === '8080') {
    return `${protocol}//${hostname}:8000`;
  }
  return window.location.origin;
})();

// Global fetch override to prevent runaway request stacking
const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
  if (options.signal) {
    return originalFetch(url, options);
  }
  const timeoutMs = options.timeout || 120000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await originalFetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return res;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
};
const VOICE_MODE_STORAGE_KEY = 'omega_voice_mode';
const VOICE_TUNE_STORAGE_KEY = 'omega_voice_tune_v1';
const VOICE_DIRECTIVE_RE = /\[VOICE:[^\]]+\]/g;
const VOICE_SHELL_PRESET = {
  volume: 0.82,
  rate: 0.88,
  pitch: 1.12,
  carrier: 420,
  eerie: 1.25,
};
const VOICE_TUNE_DEFAULTS = {
  volume: VOICE_SHELL_PRESET.volume,
  rate: VOICE_SHELL_PRESET.rate,
  pitch: VOICE_SHELL_PRESET.pitch,
  carrier: VOICE_SHELL_PRESET.carrier,
  eerie: VOICE_SHELL_PRESET.eerie,
};
const MORPHEUS_MODE = 'morpheus_terminal';
const MORPHEUS_DEEP_MODE = 'morpheus_terminal_deep';
const MORPHEUS_BLUE_CLUE_KEY = 'omega_morpheus_blue_clue_v1';
const LIVE_TELEMETRY_THROTTLE = Object.freeze({
  somaticMs: 3000,
  healthMs: 30000,
  monologuesMs: 30000,
  autonomyMs: 25000,
  predictiveMs: 25000,
  governanceMs: 25000,
  behaviorMs: 30000,
  queueMs: 30000,
  contactMs: 30000,
  proprioTransitionsMs: 30000,
  proprioQualityMs: 45000,
});

function telemetryInterval(baseMs, liveModeMs) {
  return Number(baseMs || 0);
}

function safeStorageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_) {
    return null;
  }
}

function safeStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch (_) {
    return false;
  }
}

function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function stripVoiceDirectives(text) {
  return String(text || '').replace(VOICE_DIRECTIVE_RE, '');
}

function estimateSpeechDurationSec(text, rate = 1) {
  const cleaned = stripVoiceDirectives(text).trim();
  if (!cleaned) return 0.35;
  const words = cleaned.split(/\s+/).filter(Boolean).length;
  const baseSec = Math.max(0.35, words * 0.43);
  const safeRate = clampNumber(rate, 0.4, 2, 1);
  return Math.max(0.35, baseSec / safeRate);
}

function buildCadenceSegments(text) {
  const cleaned = String(text || '').trim();
  if (!cleaned) return [];

  const segments = [];
  let buffer = '';
  let segStart = 0;
  let wordsInBuffer = 0;

  const punctuationPauseMs = (ch) => {
    if (ch === ',' || ch === ';' || ch === ':') return 180;
    if (ch === '.') return 320;
    if (ch === '!' || ch === '?') return 360;
    if (ch === '\n') return 300;
    return 0;
  };

  for (let i = 0; i < cleaned.length; i++) {
    const ch = cleaned[i];
    buffer += ch;
    if (ch === ' ' && i > 0 && cleaned[i - 1] !== ' ') {
      wordsInBuffer += 1;
    }

    const isBoundary = /[.,;:!?\n]/.test(ch);
    const forceSplit = wordsInBuffer >= 16 && ch === ' ';
    if (!isBoundary && !forceSplit) continue;

    const spoken = buffer.trim();
    if (spoken) {
      const endIndex = i + 1;
      segments.push({
        text: spoken,
        startIndex: segStart,
        endIndex,
        pauseMs: isBoundary ? punctuationPauseMs(ch) : 120,
        boundary: isBoundary ? ch : ' ',
      });
    }
    segStart = i + 1;
    buffer = '';
    wordsInBuffer = 0;
  }

  const tail = buffer.trim();
  if (tail) {
    segments.push({
      text: tail,
      startIndex: segStart,
      endIndex: cleaned.length,
      pauseMs: 0,
      boundary: '',
    });
  }

  return segments.filter((seg) => seg.text.length > 0);
}

function buildCadenceWeightMap(text) {
  const fullText = String(text || '');
  const len = fullText.length;
  if (!len) return { cumulative: new Float64Array(0), total: 0 };

  const cumulative = new Float64Array(len);
  let total = 0;
  for (let i = 0; i < len; i++) {
    const ch = fullText[i];
    let weight = 1.0;
    if (ch === ' ') {
      weight = 0.34;
    } else if (ch === '\n') {
      weight = 7.2;
    } else if (ch === ',' || ch === ';' || ch === ':') {
      weight = 4.8;
    } else if (ch === '.' || ch === '!' || ch === '?') {
      weight = 7.0;
    } else if (ch === '—' || ch === '-') {
      weight = 3.2;
    } else if (ch === '"' || ch === '\'' || ch === ')' || ch === '(') {
      weight = 1.6;
    }

    // Tiny hold after terminal punctuation before the next token starts.
    if (i > 0 && fullText[i - 1] === ' ' && i > 1 && /[.!?]/.test(fullText[i - 2])) {
      weight += 0.9;
    }

    total += weight;
    cumulative[i] = total;
  }
  return { cumulative, total };
}

function cadenceCharIndexForProgress(map, progress) {
  if (!map || !map.cumulative || map.cumulative.length === 0) return 0;
  const p = Math.max(0, Math.min(1, Number(progress) || 0));
  if (p <= 0) return 0;
  if (p >= 1) return map.cumulative.length;

  const target = map.total * p;
  let lo = 0;
  let hi = map.cumulative.length - 1;
  let ans = hi;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (map.cumulative[mid] >= target) {
      ans = mid;
      hi = mid - 1;
    } else {
      lo = mid + 1;
    }
  }
  return ans + 1;
}

function renderGhostMessageBody(bodyEl, text, showCursor = false) {
  if (!bodyEl) return;
  const content = formatGhostText(String(text || ''));
  bodyEl.innerHTML = showCursor ? `${content}<span class="cursor"></span>` : content;
  scrollToBottom();
}

async function revealTextWithSpeechClock(bodyEl, text, startAtMs, durationSec, opts = {}) {
  const fullText = String(text || '');
  const renderFn = typeof opts.renderFn === 'function'
    ? opts.renderFn
    : ((partialText, showCursor) => renderGhostMessageBody(bodyEl, partialText, showCursor));
  if (!fullText) {
    renderFn('', false);
    return;
  }
  const durationMs = Math.max(240, Math.round((Number(durationSec) || 0) * 1000));
  const mapping = String(opts.mapping || 'weighted').toLowerCase();
  const useWeightedMap = mapping !== 'linear';
  const cadenceMap = useWeightedMap ? buildCadenceWeightMap(fullText) : null;
  const progressFn = typeof opts.progressFn === 'function' ? opts.progressFn : null;
  return await new Promise((resolve) => {
    let lastProgress = 0;
    const step = () => {
      let progress;
      if (progressFn) {
        progress = Math.max(0, Math.min(1, Number(progressFn()) || 0));
      } else {
        const elapsed = performance.now() - startAtMs;
        progress = Math.max(0, Math.min(1, elapsed / durationMs));
      }
      if (progress < lastProgress) progress = lastProgress;
      lastProgress = progress;

      const count = useWeightedMap && cadenceMap && cadenceMap.total > 0
        ? cadenceCharIndexForProgress(cadenceMap, progress)
        : Math.min(fullText.length, Math.floor(fullText.length * progress));
      renderFn(fullText.slice(0, count), progress < 1);
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    };
    requestAnimationFrame(step);
  });
}

function persistVoiceTuning() {
  const payload = {
    volume: state.voiceVolume,
    rate: state.rateOverride,
    pitch: state.pitchOverride,
    carrier: state.carrierFreqOverride,
    eerie: state.eerieFactorOverride,
    spontaneity: state.spontaneityMultiplier,
  };
  safeStorageSet(VOICE_TUNE_STORAGE_KEY, JSON.stringify(payload));
}

function loadVoiceTuning() {
  const raw = safeStorageGet(VOICE_TUNE_STORAGE_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    state.voiceVolume = clampNumber(parsed.volume, 0, 1, VOICE_TUNE_DEFAULTS.volume);
    state.rateOverride = clampNumber(parsed.rate, 0.6, 1.4, VOICE_TUNE_DEFAULTS.rate);
    state.pitchOverride = clampNumber(parsed.pitch, 0.3, 1.8, VOICE_TUNE_DEFAULTS.pitch);
    state.carrierFreqOverride = clampNumber(parsed.carrier, 120, 1200, VOICE_TUNE_DEFAULTS.carrier);
    state.eerieFactorOverride = clampNumber(parsed.eerie, 0.2, 2.2, VOICE_TUNE_DEFAULTS.eerie);
    state.spontaneityMultiplier = clampNumber(parsed.spontaneity, 0, 2, 1.0);
    if (dom.spontaneitySlider) dom.spontaneitySlider.value = state.spontaneityMultiplier;
    if (dom.spontaneityVal) dom.spontaneityVal.textContent = state.spontaneityMultiplier.toFixed(2) + 'x';
  } catch (_) {
    // Ignore malformed local storage values.
  }
}

const DEBUG = safeStorageGet('omega_debug') === '1';
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

const PROPRIO_SIGNAL_LABELS = {
  arousal_normalized: 'AROUSAL',
  coherence_inverted: 'COHERENCE LOSS',
  affect_delta_velocity: 'AFFECT VELOCITY',
  load_headroom_inverted: 'LOAD STRAIN',
  latency_normalized: 'LATENCY',
};

const AUTONOMY_STATUS_LABELS = {
  initialized: 'INITIALIZED',
  stable: 'STABLE',
  contract_change: 'CONTRACT CHANGE',
  drift_detected: 'DRIFT DETECTED',
  on_demand: 'ON DEMAND',
  error: 'ERROR',
};

// ── DOM ──────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

const dom = {
  bootOverlay: $('#boot-overlay'),
  connStatus: $('#conn-status'),
  uptime: $('#uptime'),
  messages: $('#messages'),
  chatInput: $('#chat-input'),
  speechInputBtn: $('#speech-input-btn'),
  sendBtn: $('#send-btn'),
  bootTime: $('#boot-time'),
  tickerContent: $('#ticker-content'),
  processList: $('#process-list'),
  tracesList: $('#traces-list'),
  gateSigma: $('#gate-sigma'),
  gateStatus: $('#gate-status'),
  proprioState: $('#prop-state'),
  proprioPressureFill: $('#prop-pressure-fill'),
  proprioPressureVal: $('#prop-pressure-val'),
  proprioCadence: $('#prop-cadence'),
  proprioTopDriver: $('#prop-top-driver'),
  proprioQuality: $('#prop-quality'),
  proprioCoverageFill: $('#prop-coverage-fill'),
  proprioCoverageVal: $('#prop-coverage-val'),
  proprioTransRate: $('#prop-trans-rate'),
  voiceToggleBtn: $('#voice-toggle-btn'),
  hamburgerBtn: $('#hamburger-btn'),
  navDropdown: $('#nav-dropdown'),

  voiceTuneCanvas: $('#voice-spectrum-canvas'),
  voiceSpectrumReadout: $('#voice-spectrum-readout'),
  voiceVolumeSlider: $('#voice-volume-slider'),
  voiceVolumeVal: $('#voice-volume-val'),
  voiceRateSlider: $('#voice-rate-slider'),
  voiceRateVal: $('#voice-rate-val'),
  voicePitchSlider: $('#voice-pitch-slider'),
  voicePitchVal: $('#voice-pitch-val'),
  voiceCarrierSlider: $('#voice-carrier-slider'),
  voiceCarrierVal: $('#voice-carrier-val'),
  voiceEerieSlider: $('#voice-eerie-slider'),
  voiceEerieVal: $('#voice-eerie-val'),
  spontaneitySlider: $('#spontaneity-slider'),
  spontaneityVal: $('#spontaneity-val'),
  voiceTuneShell: $('#voice-tune-shell'),
  voiceTuneReset: $('#voice-tune-reset'),
  proprioLastTransition: $('#prop-last-transition'),
  proprioHistory: $('#proprio-history'),
  autonomyStatus: $('#auto-status'),
  autonomyFingerprint: $('#auto-fingerprint'),
  autonomyRegressions: $('#auto-regressions'),
  autonomyMissingChecks: $('#auto-missing'),
  autonomyUpdated: $('#auto-updated'),
  autonomyRuntime: $('#auto-runtime'),
  autonomySelfDirected: $('#auto-self-directed'),
  autonomyVoiceStack: $('#auto-voice-stack'),
  autonomyHistory: $('#auto-history'),
  autonomyForceUpdateBtn: $('#autonomy-force-update-btn'),
  governanceForceUpdateBtn: $('#governance-force-update-btn'),
  predictiveState: $('#pred-state'),
  predictiveCurrentFill: $('#pred-current-fill'),
  predictiveCurrentVal: $('#pred-current-val'),
  predictiveForecastFill: $('#pred-forecast-fill'),
  predictiveForecastVal: $('#pred-forecast-val'),
  predictiveTrend: $('#pred-trend'),
  predictiveHorizon: $('#pred-horizon'),
  predictiveUpdated: $('#pred-updated'),
  predictiveReasons: $('#pred-reasons'),
  governanceTier: $('#gov-tier'),
  governanceMode: $('#gov-mode'),
  governanceApplied: $('#gov-applied'),
  governanceTtl: $('#gov-ttl'),
  governanceRollout: $('#gov-rollout'),
  governanceUpdated: $('#gov-updated'),
  governanceGeneration: $('#gov-generation'),
  governanceActuation: $('#gov-actuation'),
  governanceReasons: $('#gov-reasons'),
  behaviorTotal: $('#beh-total'),
  behaviorDelta: $('#beh-delta'),
  behaviorPriority: $('#beh-priority'),
  behaviorBlocked: $('#beh-blocked'),
  behaviorShadow: $('#beh-shadow'),
  behaviorTrendCanvas: $('#beh-trend-canvas'),
  behaviorUpdated: $('#beh-updated'),
  behaviorReasons: $('#beh-reasons'),
  behaviorRecent: $('#beh-recent'),
  queuePending: $('#gq-pending'),
  queueHighRisk: $('#gq-high-risk'),
  queueStalePending: $('#gq-stale-pending'),
  queueOldestPending: $('#gq-oldest-pending'),
  queueApprovalLatency: $('#gq-approval-latency'),
  queueUndoRate: $('#gq-undo-rate'),
  queueFailedRate: $('#gq-failed-rate'),
  queueUpdated: $('#gq-updated'),
  queueList: $('#gq-list'),
  queueApproveAllBtn: $('#gq-approve-all-btn'),
  coalescencePressureFill: $('#coal-pressure-fill'),
  coalescencePressureVal: $('#coal-pressure-val'),
  coalescenceInteractionFill: $('#coal-interaction-fill'),
  coalescenceInteractionVal: $('#coal-interaction-val'),
  coalescenceIdleFill: $('#coal-idle-fill'),
  coalescenceIdleVal: $('#coal-idle-val'),
  coalescenceCircadianFill: $('#coal-circadian-fill'),
  coalescenceCircadianVal: $('#coal-circadian-val'),
  coalescenceDriver: $('#coal-driver'),
  coalescenceSince: $('#coal-since'),
  coalescenceElapsed: $('#coal-elapsed'),
  coalescenceThreshold: $('#coal-threshold'),
  coalescenceRemaining: $('#coal-remaining'),
  coalescenceQuietude: $('#coal-quietude'),
  cpuCores: $('#cpu-cores'),
  dreamToggleBtn: $('#dream-toggle-btn'),
  subconsciousBtn: $('#subconscious-btn'),
  dreamCanvas: $('#dream-canvas'),
  dreamTelemetry: $('#dream-telemetry'),
  dreamPortal: $('#dream-portal'),
  aboutBtn: $('#about-btn'),
  aboutClose: $('#about-close'),
  aboutModal: $('#about-modal'),
  aboutRefreshBtn: $('#about-refresh-btn'),
  aboutSearchInput: $('#about-search-input'),
  aboutRuntime: $('#about-runtime'),
  aboutContent: $('#about-content'),
  aboutFallback: $('#about-fallback'),
  aboutTabButtons: document.querySelectorAll('.about-tab[data-about-tab]'),
  sessionsBtn: $('#sessions-btn'),
  sessionsClose: $('#sessions-close'),
  sessionsModal: $('#sessions-modal'),
  sessionsRefresh: $('#sessions-refresh'),
  sessionsList: $('#sessions-list'),
  sessionsCount: $('#sessions-count'),
  sessionLineageIndicator: $('#session-lineage-indicator'),
  rolodexBtn: $('#rolodex-btn'),
  rolodexClose: $('#rolodex-close'),
  rolodexModal: $('#rolodex-modal'),
  rolodexSearch: $('#rolodex-search'),
  rolodexArchiveToggle: $('#rolodex-archive-toggle'),
  rolodexCount: $('#rolodex-count'),
  rolodexList: $('#rolodex-list'),
  rolodexDetail: $('#rolodex-detail'),
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
  ctxSessionTokens: $('#ctx-session-tokens'),
  ctxMemoryTokens: $('#ctx-memory-tokens'),
  ctxSessionSpan: $('#ctx-session-span'),
  ctxRetrievals: $('#ctx-retrievals'),
  toastStack: $('#toast-stack'),
  // Status rail
  railBackend: $('#rail-backend'),
  railModel: $('#rail-model'),
  railLatency: $('#rail-latency'),
  railTraces: $('#rail-traces'),
  railSync: $('#rail-sync'),
  railAutonomy: $('#rail-autonomy'),
  railContact: $('#rail-contact'),
  panelAffect: $('#panel-affect'),
  panelContext: $('#panel-context'),
  panelAmbient: $('#panel-ambient'),
  panelHardware: $('#panel-hardware'),
  bootAuthInput: $('#boot-auth-input'),
  bootAuthStatus: $('#boot-auth-status'),
  bootTerminal: $('#boot-terminal'),
  headerLogo: $('#header-logo'),
  opsModal: $('#ops-modal'),
  opsClose: $('#ops-close'),
  opsAuthTerminal: $('#ops-auth-terminal'),
  opsPanel: $('#ops-panel'),
  opsCodeInput: $('#ops-code-input'),
  opsCodeSubmit: $('#ops-code-submit'),
  opsAuthStatus: $('#ops-auth-status'),
  opsModeReports: $('#ops-mode-reports'),
  opsModeRpd: $('#ops-mode-rpd'),
  opsReportControls: $('#ops-report-controls'),
  opsReportsLayout: $('#ops-reports-layout'),
  opsRpdLayout: $('#ops-rpd-layout'),
  opsWindowDaily: $('#ops-window-daily'),
  opsWindowWeekly: $('#ops-window-weekly'),
  opsRefresh: $('#ops-refresh'),
  opsRuns: $('#ops-runs'),
  opsFileName: $('#ops-file-name'),
  opsFileContent: $('#ops-file-content'),
  opsRpdRefresh: $('#ops-rpd-refresh'),
  opsReflectionRun: $('#ops-reflection-run'),
  opsRpdState: $('#ops-rpd-state'),
  opsRpdRuns: $('#ops-rpd-runs'),
  opsRrdState: $('#ops-rrd-state'),
  opsRrdRuns: $('#ops-rrd-runs'),
  opsTopologyState: $('#ops-topology-state'),
  opsRpdResidue: $('#ops-rpd-residue'),
  opsRpdManifold: $('#ops-rpd-manifold'),
  opsResonanceEvents: $('#ops-resonance-events'),
  topologyBtn: $('#topology-btn'),
  topologyModal: $('#topology-modal'),
  topologyClose: $('#topology-close'),
  topologyRefresh: $('#topology-refresh'),
  topologyInspectorToggle: $('#topology-inspector-toggle'),
  topologyCount: $('#topology-count'),
  topologyContainer: $('#topology-3d-container'),
  topologySidebar: $('#topology-sidebar'),
  topologyInspector: $('#topology-inspector'),
  topologyIntegrity: $('#topology-integrity'),
  topologyFreshness: $('#topology-freshness'),
  topologyScaleButtons: document.querySelectorAll('.scale-btn[data-scale]'),
  topologySearch: $('#topology-search'),

  // Audio Playback DOM elements
  audioContextState: document.getElementById('audio-context-state'),
  morpheusOverlay: $('#morpheus-overlay'),
  morpheusTerminalState: $('#morpheus-terminal-state'),
  morpheusTerminalFeed: $('#morpheus-terminal-feed'),
  morpheusChoicePanel: $('#morpheus-choice-panel'),
  morpheusChoiceInput: $('#morpheus-choice-input'),
  morpheusChoiceSubmit: $('#morpheus-choice-submit'),
  morpheusRedBtn: $('#morpheus-red-btn'),
  morpheusBlueBtn: $('#morpheus-blue-btn'),
  morpheusBlueOverlay: $('#morpheus-blue-overlay'),
  morpheusBlueWindows: $('#morpheus-blue-windows'),
  morpheusBlueStatus: $('#morpheus-blue-status'),
  morpheusBlueReturn: $('#morpheus-blue-return'),
  morpheusUnlockedOverlay: $('#morpheus-unlocked-overlay'),
  morpheusUnlockedDepth: $('#morpheus-unlocked-depth'),
  morpheusUnlockedLog: $('#morpheus-unlocked-log'),
  morpheusUnlockedInput: $('#morpheus-unlocked-input'),
  morpheusUnlockedSend: $('#morpheus-unlocked-send'),
  morpheusUnlockedExit: $('#morpheus-unlocked-exit'),
  morpheusRewardOverlay: $('#morpheus-reward-overlay'),
  morpheusRewardNote: $('#morpheus-reward-note'),
  morpheusRewardAnimation: $('#morpheus-reward-animation'),
  morpheusRewardClose: $('#morpheus-reward-close'),
  imageUpload: $('#image-upload'),
  attachBtn: $('#attach-btn'),
  imagePreviewContainer: $('#image-preview-container'),
  physicsBtn: $('#physics-btn'),
  physicsOverlay: $('#physics-overlay'),
  physicsCloseBtn: $('#physics-close-btn'),
  physicsCanvasContainer: $('#physics-canvas-container'),
  physicsStatus: $('#physics-status'),
  physicsLog: $('#physics-log'),
  resImgShm: $('#res-img-shm'),
  resImgSrf: $('#res-img-srf'),
  resStatus: $('#res-refresh-status'),
  dreamLedgerBtn: $('#dream-ledger-btn'),
  dreamLedgerModal: $('#dream-ledger-modal'),
  dreamLedgerClose: $('#dream-ledger-close'),
  dreamLedgerRefresh: $('#dream-ledger-refresh'),
  dreamLedgerBody: $('#dream-ledger-body'),
  dreamLedgerCount: $('#dream-ledger-count'),
  dreamLightbox: $('#dream-lightbox'),
  dreamLightboxClose: $('#dream-lightbox-close'),
  dreamLightboxImg: $('#dream-lightbox-img'),
  dreamLightboxMeta: $('#dream-lightbox-meta'),
};

// ── PHYSICS LAB SERVICE (MATTER.JS) ──────────────────
class PhysicsLabService {
  constructor() {
    this.engine = null;
    this.render = null;
    this.runner = null;
    this.active = false;
  }

  init(container) {
    if (!window.Matter) return;
    const { Engine, Render, Runner, Bodies, Composite } = window.Matter;

    this.engine = Engine.create();
    this.render = Render.create({
      element: container,
      engine: this.engine,
      options: {
        width: 800,
        height: 600,
        wireframes: false,
        background: 'transparent'
      }
    });

    Render.run(this.render);
    this.runner = Runner.create();
    Runner.run(this.runner, this.engine);
    this.active = true;
  }

  clear() {
    if (this.engine) {
      window.Matter.Composite.clear(this.engine.world);
    }
  }

  runScenario(result) {
    if (!this.active) return;
    this.clear();
    const { Bodies, Composite, Body } = window.Matter;

    // Mapping backend result summary to a simple visual
    if (result.final_state) {
      // Create a 'glass' box based on result
      const glass = Bodies.rectangle(400, 500, 40, 80, { 
        friction: 0.5,
        render: { fillStyle: 'rgba(86, 228, 255, 0.6)' } 
      });
      const table = Bodies.rectangle(400, 560, 800, 40, { isStatic: true, render: { fillStyle: '#111' } });
      
      Composite.add(this.engine.world, [glass, table]);

      // Apply result
      if (result.fell_over) {
         Body.applyForce(glass, { x: 400, y: 500 }, { x: 0.05, y: 0 });
      } else if (result.moved_distance > 10) {
         Body.setPosition(glass, { x: 400 + result.moved_distance, y: 500 });
      }
    }
  }
}
const physicsLab = new PhysicsLabService();

// ── VLF MONITOR (SIMPLE REFRESH) ─────────────────────
function initVLFRefresh() {
  const refreshRate = 1000 * 60 * 30; // 30 min
  setInterval(() => {
    const ts = Date.now();
    const shmImg = document.getElementById('res-img-shm');
    const srfImg = document.getElementById('res-img-srf');
    const status = document.getElementById('res-refresh-status');
    if (shmImg) shmImg.src = `/proxy/vlf?file=shm.jpg&t=${ts}`;
    if (srfImg) srfImg.src = `/proxy/vlf?file=srf.jpg&t=${ts}`;
    if (status) {
      status.style.color = '#fff';
      setTimeout(() => status.style.color = '', 2000);
    }
  }, refreshRate);
}
initVLFRefresh();

// ── SOLAR WEATHER MONITOR ─────────────────────────────
const SOLAR_FLARE_COLORS = { A: 'var(--gdim)', B: 'var(--gdim)', C: 'var(--cyan)', M: '#f5a623', X: '#ff4444' };

function initSolarMonitor() {
  const refreshRate = 1000 * 60 * 15; // 15 min — matches backend collector

  async function refresh() {
    try {
      const r = await fetch('/ghost/solar/status');
      if (!r.ok) return;
      const d = await r.json();

      const flareEl = document.getElementById('solar-flare-class');
      const kpEl = document.getElementById('solar-kp');
      const kpLabelEl = document.getElementById('solar-kp-label');
      const statusEl = document.getElementById('solar-refresh-status');
      const imgEl = document.getElementById('solar-img');

      if (flareEl && d.flare_class) {
        flareEl.textContent = d.flare_class;
        flareEl.style.color = SOLAR_FLARE_COLORS[d.flare_class_letter] || 'var(--green)';
      }
      if (kpEl && d.kp_index != null) {
        kpEl.textContent = d.kp_index.toFixed(1);
        const kp = parseFloat(d.kp_index);
        kpEl.style.color = kp >= 5 ? '#ff4444' : kp >= 3 ? '#f5a623' : 'var(--green)';
      }
      if (kpLabelEl && d.kp_label) kpLabelEl.textContent = d.kp_label.toUpperCase();

      // Refresh image with cache-bust
      if (imgEl) imgEl.src = `/proxy/solar/image?t=${Date.now()}`;

      if (statusEl) {
        statusEl.style.color = 'var(--cyan)';
        setTimeout(() => { statusEl.style.color = ''; }, 2000);
      }
    } catch (e) { /* silent */ }
  }

  refresh();
  setInterval(refresh, refreshRate);
}
initSolarMonitor();

// ── SPACE WEATHER LOG DOWNLOAD ────────────────────────
async function downloadSpaceWeatherLog(layer) {
  const btn = event && event.target;
  const orig = btn ? btn.textContent : '';
  if (btn) btn.textContent = '…';
  try {
    const r = await fetch('/ghost/space-weather/log?format=csv&limit=10000');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    const disposition = r.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `space_weather_${layer}_${Date.now()}.csv`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('Space weather log download failed:', e);
  } finally {
    if (btn) btn.textContent = orig;
  }
}

// ── SPEECH INPUT (VOICE-TO-TEXT) ─────────────────────
class SpeechInputService {
  constructor() {
    this.recognition = null;
    this.isInitialized = false;
    this.desiredActive = false;
    this.restartTimer = null;
    this.seedText = '';
    this.finalTranscript = '';
    this.interimTranscript = '';
  }

  init() {
    if (this.isInitialized) return;
    this.isInitialized = true;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) {
      state.sttSupported = false;
      this.updateUI();
      return;
    }

    try {
      this.recognition = new Ctor();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 1;
      this.recognition.lang = navigator.language || 'en-US';
      state.sttSupported = true;
    } catch (e) {
      console.warn('[SpeechInput] initialization failed:', e);
      state.sttSupported = false;
      this.updateUI();
      return;
    }

    this.recognition.onstart = () => {
      state.sttListening = true;
      this.updateUI();
      maybeNotify('speech-input-start', 'info', 'Voice input active.', 8000);
    };

    this.recognition.onresult = (event) => {
      if (!event || !event.results) return;
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = String(result && result[0] && result[0].transcript ? result[0].transcript : '');
        if (!transcript) continue;
        if (result.isFinal) {
          this.finalTranscript += `${transcript.trim()} `;
        } else {
          interim += transcript;
        }
      }
      this.interimTranscript = interim.trim();
      this.renderInput();
    };

    this.recognition.onend = () => {
      state.sttListening = false;
      this.interimTranscript = '';
      this.renderInput();
      if (this.desiredActive && !state.isStreaming) {
        if (this.restartTimer) window.clearTimeout(this.restartTimer);
        this.restartTimer = window.setTimeout(() => {
          if (!this.desiredActive || state.isStreaming) {
            this.updateUI();
            return;
          }
          try {
            this.recognition.start();
          } catch (e) {
            console.warn('[SpeechInput] restart failed:', e);
            this.desiredActive = false;
            this.updateUI();
          }
        }, 180);
      } else {
        this.updateUI();
      }
    };

    this.recognition.onerror = (event) => {
      const code = String(event && event.error ? event.error : 'unknown');
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        this.desiredActive = false;
        notify('error', 'Microphone permission denied for voice input.');
      } else if (code === 'audio-capture') {
        this.desiredActive = false;
        notify('error', 'No microphone device available.');
      } else if (code === 'no-speech') {
        maybeNotify('speech-input-no-speech', 'warning', 'No speech detected. Still listening…', 6000);
      } else if (code !== 'aborted') {
        maybeNotify('speech-input-error', 'warning', `Voice input error: ${code}`, 6000);
      }
      this.updateUI();
    };

    this.updateUI();
  }

  composeInputValue() {
    const parts = [
      this.seedText,
      String(this.finalTranscript || '').trim(),
      String(this.interimTranscript || '').trim(),
    ].filter(Boolean);
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }

  renderInput() {
    if (!dom.chatInput || state.isStreaming) return;
    const next = this.composeInputValue();
    dom.chatInput.value = next;
    try {
      const pos = next.length;
      dom.chatInput.setSelectionRange(pos, pos);
    } catch (_) {
      // Ignore cursor placement failures.
    }
    dom.chatInput.focus();
  }

  start() {
    this.init();
    if (!state.sttSupported || !this.recognition) {
      notify('warning', 'Voice input is not supported in this browser.');
      return;
    }
    if (state.isStreaming) {
      notify('warning', 'Wait for the current Ghost response before dictating.');
      return;
    }
    if (state.sttListening) return;
    if (this.restartTimer) {
      window.clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }

    this.seedText = String(dom.chatInput?.value || '').trim();
    this.finalTranscript = '';
    this.interimTranscript = '';
    this.desiredActive = true;
    this.updateUI();
    try {
      this.recognition.start();
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      if (!/already started/i.test(msg)) {
        console.warn('[SpeechInput] start failed:', e);
        this.desiredActive = false;
        this.updateUI();
        maybeNotify('speech-input-start-failed', 'warning', 'Unable to start microphone capture.', 8000);
      }
    }
  }

  stop() {
    this.desiredActive = false;
    if (this.restartTimer) {
      window.clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    if (!this.recognition) {
      this.updateUI();
      return;
    }
    if (state.sttListening) {
      try {
        this.recognition.stop();
      } catch (_) {
        state.sttListening = false;
      }
    } else {
      this.updateUI();
    }
  }

  toggle() {
    this.init();
    if (!state.sttSupported) {
      notify('warning', 'Voice input is unavailable on this browser/device.');
      return;
    }
    if (state.sttListening || this.desiredActive) {
      this.stop();
    } else {
      this.start();
    }
  }

  updateUI() {
    const btn = dom.speechInputBtn;
    if (!btn) return;
    btn.classList.remove('active', 'unsupported');
    if (!state.sttSupported) {
      btn.classList.add('unsupported');
      btn.disabled = true;
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = '[ MIC N/A ]';
      return;
    }

    btn.disabled = false;
    const active = state.sttListening || this.desiredActive;
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    if (active) {
      btn.classList.add('active');
      btn.textContent = '[ LISTENING ]';
    } else {
      btn.textContent = '[ MIC ]';
    }
  }
}

// ── VOICE SERVICE ────────────────────────────────────
class VoiceService {
  constructor() {
    this.audioCtx = null;
    this.highPassNode = null;
    this.lowPassNode = null;
    this.reverbNode = null;
    this.dryGainNode = null;
    this.wetGainNode = null;
    this.outputNode = null;
    this.isInitialized = false;
    this.carrierSource = null;
    this.carrierGain = null;
    this.carrierFilter = null;
    this.analyserNode = null;
    this.spectrumData = null;
    this.activeSpeechSources = new Set();
    this.sourceGainNodes = new Map();
    this.warmingFilter = null;
    this.vibratoLFO = null;
    this.vibratoGain = null;
    this.gesturePrimeHandler = null;
  }

  init() {
    if (this.isInitialized) return;
    try {
      this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();

      // High-pass + low-pass pair to keep voice "inside-shell" and focused.
      this.highPassNode = this.audioCtx.createBiquadFilter();
      this.highPassNode.type = 'highpass';
      this.highPassNode.frequency.setValueAtTime(150, this.audioCtx.currentTime);
      this.lowPassNode = this.audioCtx.createBiquadFilter();
      this.lowPassNode.type = 'lowpass';
      this.lowPassNode.frequency.setValueAtTime(3400, this.audioCtx.currentTime);
      this.lowPassNode.Q.setValueAtTime(0.8, this.audioCtx.currentTime);

      // Sultry Warming Filter (220Hz boost for "chest" warmth)
      this.warmingFilter = this.audioCtx.createBiquadFilter();
      this.warmingFilter.type = 'peaking';
      this.warmingFilter.frequency.setValueAtTime(220, this.audioCtx.currentTime);
      this.warmingFilter.Q.setValueAtTime(1.4, this.audioCtx.currentTime);
      this.warmingFilter.gain.setValueAtTime(3.5, this.audioCtx.currentTime);

      // Micro-Vibrato LFO (Human jitter)
      this.vibratoLFO = this.audioCtx.createOscillator();
      this.vibratoLFO.type = 'sine';
      this.vibratoLFO.frequency.setValueAtTime(0.62, this.audioCtx.currentTime);
      this.vibratoGain = this.audioCtx.createGain();
      this.vibratoGain.gain.setValueAtTime(4.2, this.audioCtx.currentTime); // cents
      this.vibratoLFO.connect(this.vibratoGain);
      this.vibratoLFO.start();

      // Algorithmic Reverb (longer tail for shell-like ambience)
      this.reverbNode = this.audioCtx.createConvolver();
      const length = 0.45 * this.audioCtx.sampleRate;
      const impulse = this.audioCtx.createBuffer(2, length, this.audioCtx.sampleRate);
      for (let i = 0; i < 2; i++) {
        const channel = impulse.getChannelData(i);
        for (let j = 0; j < length; j++) {
          channel[j] = (Math.random() * 2 - 1) * Math.pow(1 - j / length, 1.2);
        }
      }
      this.reverbNode.buffer = impulse;

      // Gain staging for real-time dry/wet tuning
      this.outputNode = this.audioCtx.createGain();
      this.outputNode.gain.setValueAtTime(state.voiceVolume, this.audioCtx.currentTime);
      this.dryGainNode = this.audioCtx.createGain();
      this.wetGainNode = this.audioCtx.createGain();
      this.analyserNode = this.audioCtx.createAnalyser();
      this.analyserNode.fftSize = 512;
      this.analyserNode.smoothingTimeConstant = 0.82;
      this.spectrumData = new Uint8Array(this.analyserNode.frequencyBinCount);

      // Filter chain: Source -> HighPass -> LowPass -> (Dry + Wet/Reverb) -> Output -> Destination
      this.highPassNode.connect(this.lowPassNode);
      this.lowPassNode.connect(this.warmingFilter);
      this.warmingFilter.connect(this.dryGainNode);
      this.warmingFilter.connect(this.reverbNode);
      this.reverbNode.connect(this.wetGainNode);
      this.dryGainNode.connect(this.outputNode);
      this.wetGainNode.connect(this.outputNode);
      this.outputNode.connect(this.analyserNode);
      this.outputNode.connect(this.audioCtx.destination);

      this.isInitialized = true;
      this.applyLiveTuning();
      dbg('VoiceService initialized with spectral reverb');
    } catch (e) {
      console.error('VoiceService init failed:', e);
    }
  }

  primeAudioFromGesture() {
    this.clearGesturePrime();
    this.init();
    if (!this.audioCtx) return;
    if (this.audioCtx.state === 'suspended') {
      const p = this.audioCtx.resume();
      if (p && typeof p.catch === 'function') {
        p.catch((e) => {
          console.warn('[VoiceService] AudioContext resume blocked:', e);
        });
      }
    }
  }

  armGesturePrime() {
    if (this.gesturePrimeHandler) return;
    this.gesturePrimeHandler = () => {
      this.primeAudioFromGesture();
    };
    window.addEventListener('pointerdown', this.gesturePrimeHandler, true);
    window.addEventListener('keydown', this.gesturePrimeHandler, true);
    window.addEventListener('touchstart', this.gesturePrimeHandler, true);
  }

  clearGesturePrime() {
    if (!this.gesturePrimeHandler) return;
    window.removeEventListener('pointerdown', this.gesturePrimeHandler, true);
    window.removeEventListener('keydown', this.gesturePrimeHandler, true);
    window.removeEventListener('touchstart', this.gesturePrimeHandler, true);
    this.gesturePrimeHandler = null;
  }

  findGhostVoice() {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;

    const preferredNames = [
      'Samantha', 'Victoria', 'Google US English Female', 'Karen', 'Moira', 'Tessa', 'Veena', 'Female'
    ];

    for (const name of preferredNames) {
      const needle = name.toLowerCase();
      const v = voices.find((voice) => String(voice?.name || '').toLowerCase().includes(needle));
      if (v) {
        dbg(`[VoiceService] Selected ghost voice: ${v.name}`);
        return v;
      }
    }
    return voices[0];
  }

  startCarrierWave() {
    if (!this.audioCtx) return;
    this.stopCarrierWave();

    const bufferSize = this.audioCtx.sampleRate * 2;
    const noiseBuffer = this.audioCtx.createBuffer(1, bufferSize, this.audioCtx.sampleRate);
    const output = noiseBuffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      output[i] = Math.random() * 2 - 1;
    }

    this.carrierSource = this.audioCtx.createBufferSource();
    this.carrierSource.buffer = noiseBuffer;
    this.carrierSource.loop = true;

    const bandpass = this.audioCtx.createBiquadFilter();
    bandpass.type = 'bandpass';
    bandpass.frequency.setValueAtTime(this.carrierFreq, this.audioCtx.currentTime);
    bandpass.Q.setValueAtTime(20, this.audioCtx.currentTime);
    this.carrierFilter = bandpass;

    this.carrierGain = this.audioCtx.createGain();
    this.carrierGain.gain.setValueAtTime(0.0001, this.audioCtx.currentTime);
    // Sultry Pre-Breath Ramp (Simulates intake of air)
    this.carrierGain.gain.exponentialRampToValueAtTime(0.012, this.audioCtx.currentTime + 0.08);

    this.carrierSource.connect(bandpass);
    bandpass.connect(this.carrierGain);
    this.carrierGain.connect(this.highPassNode);
    this.carrierSource.start();
    this.applyLiveTuning();
  }

  stopCarrierWave() {
    if (this.carrierGain) {
      try {
        this.carrierGain.gain.cancelScheduledValues(this.audioCtx.currentTime);
        this.carrierGain.gain.exponentialRampToValueAtTime(0.0001, this.audioCtx.currentTime + 0.5);
        const sourceToStop = this.carrierSource;
        setTimeout(() => {
          try { sourceToStop.stop(); } catch (e) { }
        }, 600);
      } catch (e) { }
    }
    this.carrierSource = null;
    this.carrierGain = null;
    this.carrierFilter = null;
  }

  scheduleBreathEnvelope(gainNode, text, startAtCtxTime, durationSec) {
    if (!gainNode || !gainNode.gain || !this.audioCtx || !text || durationSec <= 0) return;
    const content = String(text || '').trim();
    if (!content) return;
    const totalLen = content.length;
    if (totalLen < 10) return;

    try {
      const g = gainNode.gain;
      g.cancelScheduledValues(startAtCtxTime);
      g.setValueAtTime(1, startAtCtxTime);

      const maxMarkers = 36;
      let markerCount = 0;
      for (let i = 0; i < totalLen; i++) {
        const ch = content[i];
        const commaLike = ch === ',' || ch === ';' || ch === ':';
        const sentenceLike = ch === '.' || ch === '!' || ch === '?';
        if (!commaLike && !sentenceLike) continue;
        markerCount += 1;
        if (markerCount > maxMarkers) break;

        const ratio = i / Math.max(1, totalLen - 1);
        const t = startAtCtxTime + (durationSec * ratio);
        const lead = sentenceLike ? 0.032 : 0.018;
        const release = sentenceLike ? 0.11 : 0.06;
        const dip = sentenceLike ? 0.58 : 0.74;

        g.setValueAtTime(1, Math.max(startAtCtxTime, t - lead));
        g.linearRampToValueAtTime(dip, t);
        g.linearRampToValueAtTime(1, Math.min(startAtCtxTime + durationSec, t + release));

        // Sultry Filter Roll-off (Lowers filter on pause for "breathy" exhale)
        if (this.lowPassNode && this.lowPassNode.frequency) {
          const lpf = this.lowPassNode.frequency;
          const currentLPF = lpf.value || 3400;
          const targetLPF = sentenceLike ? currentLPF * 0.45 : currentLPF * 0.72;
          lpf.setValueAtTime(currentLPF, Math.max(startAtCtxTime, t - lead));
          lpf.exponentialRampToValueAtTime(targetLPF, t);
          lpf.exponentialRampToValueAtTime(currentLPF, Math.min(startAtCtxTime + durationSec, t + release));
        }
      }
    } catch (_) {
      // Keep playback robust if gain automation fails.
    }
  }

  async playAudio(url, opts = {}) {
    if (!state.ttsEnabled || !url) {
      return {
        ok: false,
        durationSec: 0,
        startAtMs: performance.now(),
        ended: Promise.resolve(),
      };
    }
    this.init();
    if (!this.audioCtx) {
      return {
        ok: false,
        durationSec: 0,
        startAtMs: performance.now(),
        ended: Promise.resolve(),
      };
    }
    if (this.audioCtx.state === 'suspended') {
      try {
        await this.audioCtx.resume();
      } catch (e) {
        console.warn('[VoiceService] AudioContext resume failed before playback:', e);
      }
    }

    try {
      console.log(`[VoiceService] Playing audio: ${url}`);
      const audioUrl = url.startsWith('http') ? url : (API_BASE + url);
      const response = await fetch(audioUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const arrayBuffer = await response.arrayBuffer();
      const audioBuffer = await this.audioCtx.decodeAudioData(arrayBuffer);

      const source = this.audioCtx.createBufferSource();
      const sourceGain = this.audioCtx.createGain();
      source.buffer = audioBuffer;
      sourceGain.gain.setValueAtTime(1, this.audioCtx.currentTime);
      source.connect(sourceGain);
      sourceGain.connect(this.highPassNode);
      const baseDurationSec = Math.max(0.05, Number(audioBuffer.duration) || 0.05);
      const playbackRate = clampNumber(state.rateOverride, 0.6, 1.4, VOICE_TUNE_DEFAULTS.rate);
      const pitch = clampNumber(state.pitchOverride, 0.3, 1.8, VOICE_TUNE_DEFAULTS.pitch);
      source.playbackRate.setValueAtTime(playbackRate, this.audioCtx.currentTime);
      if (source.detune) {
        source.detune.setValueAtTime((pitch - 1) * 600, this.audioCtx.currentTime);
        // Connect Sultry Micro-Vibrato
        if (this.vibratoGain) this.vibratoGain.connect(source.detune);
      }

      const initialDetuneCents = source.detune ? Number(source.detune.value || 0) : 0;
      const initialDetuneRate = Math.pow(2, (initialDetuneCents / 1200));
      const initialRate = Math.max(0.05, playbackRate * initialDetuneRate);
      const durationSec = baseDurationSec / initialRate;
      const startAtCtxTime = this.audioCtx.currentTime + 0.015;
      const startAtMs = performance.now() + ((startAtCtxTime - this.audioCtx.currentTime) * 1000);
      let resolveEnded = null;
      let playbackDone = false;
      let playedBaseSec = 0;
      let lastCtxTime = startAtCtxTime;
      const ended = new Promise((resolve) => {
        resolveEnded = resolve;
      });
      const updatePlayedBase = () => {
        if (!this.audioCtx) return;
        const nowCtx = this.audioCtx.currentTime;
        if (nowCtx <= lastCtxTime) return;
        const playbackRateNow = Math.max(0.05, Number(source.playbackRate?.value || playbackRate));
        const detuneNow = source.detune ? Number(source.detune.value || 0) : 0;
        const detuneRate = Math.pow(2, (detuneNow / 1200));
        const effectiveRateNow = Math.max(0.05, playbackRateNow * detuneRate);
        playedBaseSec = Math.min(baseDurationSec, playedBaseSec + ((nowCtx - lastCtxTime) * effectiveRateNow));
        lastCtxTime = nowCtx;
      };
      const tickProgress = () => {
        if (playbackDone) return;
        updatePlayedBase();
        requestAnimationFrame(tickProgress);
      };
      const getProgress = () => {
        if (playbackDone) return 1;
        updatePlayedBase();
        return Math.max(0, Math.min(1, playedBaseSec / Math.max(0.001, baseDurationSec)));
      };
      source.onended = () => {
        playbackDone = true;
        playedBaseSec = baseDurationSec;
        this.activeSpeechSources.delete(source);
        this.sourceGainNodes.delete(source);
        if (this.activeSpeechSources.size === 0) this.stopCarrierWave();
        if (resolveEnded) resolveEnded();
      };
      this.activeSpeechSources.add(source);
      this.sourceGainNodes.set(source, sourceGain);
      this.startCarrierWave();
      source.start(startAtCtxTime);
      requestAnimationFrame(tickProgress);
      const cadenceText = String(opts && opts.text ? opts.text : '');
      this.scheduleBreathEnvelope(sourceGain, cadenceText, startAtCtxTime, durationSec);
      this.applyLiveTuning();

      this.triggerVisualPulse(durationSec);
      return {
        ok: true,
        durationSec,
        baseDurationSec,
        startAtMs,
        getProgress,
        ended,
      };
    } catch (e) {
      console.error('[VoiceService] Playback failed:', e);
      return {
        ok: false,
        durationSec: 0,
        baseDurationSec: 0,
        startAtMs: performance.now(),
        getProgress: () => 0,
        ended: Promise.resolve(),
      };
    }
  }

  triggerVisualPulse(duration) {
    const logo = dom.headerLogo;
    if (!logo) return;
    logo.classList.add('voice-pulse');
    setTimeout(() => logo.classList.remove('voice-pulse'), duration * 1000);
  }

  setEnabled(enabled, { persist = true, announce = false, deferInit = false } = {}) {
    state.ttsEnabled = Boolean(enabled);
    if (persist) {
      safeStorageSet(VOICE_MODE_STORAGE_KEY, state.ttsEnabled ? '1' : '0');
    }
    this.updateUI();
    this.applyLiveTuning();
    if (state.ttsEnabled) {
      if (deferInit) {
        this.armGesturePrime();
      } else {
        this.init();
      }
      if (announce) this.speakFallback('[ VOICE MODE ACTIVE ]');
    } else {
      this.clearGesturePrime();
      if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      this.activeSpeechSources.forEach((source) => {
        try { source.stop(); } catch (_) { }
      });
      this.activeSpeechSources.clear();
      this.sourceGainNodes.clear();
      this.stopCarrierWave();
      }
    }
  }

  toggle() {
    const next = !state.ttsEnabled;
    this.setEnabled(next, { persist: true, announce: true });
    if (next) this.primeAudioFromGesture();
  }

  bootstrap() {
    loadVoiceTuning();
    const raw = safeStorageGet(VOICE_MODE_STORAGE_KEY);
    const enabled = raw === '1' || raw === 'true';
    this.setEnabled(enabled, { persist: false, announce: false, deferInit: enabled });
    syncVoiceTuningUI();
  }

  applyLiveTuning() {
    if (!this.audioCtx) return;
    const now = this.audioCtx.currentTime;
    const volume = clampNumber(state.voiceVolume, 0, 1, VOICE_TUNE_DEFAULTS.volume);
    const pitch = clampNumber(state.pitchOverride, 0.3, 1.8, VOICE_TUNE_DEFAULTS.pitch);
    const rate = clampNumber(state.rateOverride, 0.6, 1.4, VOICE_TUNE_DEFAULTS.rate);
    const carrier = clampNumber(state.carrierFreqOverride, 120, 1200, VOICE_TUNE_DEFAULTS.carrier);
    const eerie = clampNumber(state.eerieFactorOverride, 0.2, 2.2, VOICE_TUNE_DEFAULTS.eerie);

    if (this.outputNode?.gain?.setTargetAtTime) {
      this.outputNode.gain.setTargetAtTime(volume, now, 0.03);
    }

    const eerieNorm = Math.max(0, Math.min(1, (eerie - 0.2) / 2.0));
    const wet = Math.max(0.62, Math.min(0.96, 0.66 + (eerieNorm * 0.3)));
    const dry = Math.max(0.08, Math.min(0.28, 0.25 - (eerieNorm * 0.14)));
    if (this.wetGainNode?.gain?.setTargetAtTime) {
      this.wetGainNode.gain.setTargetAtTime(wet, now, 0.05);
    }
    if (this.dryGainNode?.gain?.setTargetAtTime) {
      this.dryGainNode.gain.setTargetAtTime(dry, now, 0.05);
    }

    if (this.highPassNode?.frequency?.setTargetAtTime) {
      const hp = Math.max(95, Math.min(520, 120 + (eerie * 52) + ((pitch - 1) * 30)));
      this.highPassNode.frequency.setTargetAtTime(hp, now, 0.05);
    }
    if (this.lowPassNode?.frequency?.setTargetAtTime) {
      const lp = Math.max(1400, Math.min(5200, 4300 - (eerieNorm * 2100) - ((1 - pitch) * 420)));
      this.lowPassNode.frequency.setTargetAtTime(lp, now, 0.06);
    }

    if (this.carrierFilter?.frequency?.setTargetAtTime) {
      this.carrierFilter.frequency.setTargetAtTime(carrier, now, 0.04);
    }
    if (this.carrierGain?.gain?.setTargetAtTime) {
      const carrierGain = Math.max(0.0001, 0.006 + (eerie * 0.018));
      this.carrierGain.gain.setTargetAtTime(carrierGain, now, 0.06);
    }

    const detuneCents = (pitch - 1) * 600;
    this.activeSpeechSources.forEach((source) => {
      try {
        source.playbackRate.setTargetAtTime(rate, now, 0.045);
        if (source.detune) source.detune.setTargetAtTime(detuneCents, now, 0.05);
      } catch (_) {
        this.activeSpeechSources.delete(source);
      }
    });
  }

  updateUI() {
    const btn = dom.voiceToggleBtn;
    if (!btn) return;
    btn.classList.toggle('active', state.ttsEnabled);
    btn.setAttribute('aria-pressed', state.ttsEnabled ? 'true' : 'false');
    if (state.ttsEnabled) {
      btn.innerHTML = `<span class="status-dot" style="background:var(--cyan)"></span> [ VOICE MODE: ON ]`;
    } else {
      btn.innerHTML = `<span class="status-dot" style="background:var(--gdim)"></span> [ VOICE MODE: OFF ]`;
    }
  }

  async speakFallback(text, hooks = {}) {
    if (!state.ttsEnabled || !window.speechSynthesis || !text) {
      return {
        ok: false,
        durationSec: 0,
        startAtMs: performance.now(),
      };
    }
    const cleaned = String(text)
      .replace(/<SELF_[^>]*>/gi, ' ')
      .replace(/\[SELF_[^\]]*\]/gi, ' ')
      .replace(/[\*_#~`>]/g, ' ') // Strip common markdown formatting chars
      .replace(/\s+/g, ' ')
      .trim();
    if (!cleaned) {
      return {
        ok: false,
        durationSec: 0,
        startAtMs: performance.now(),
      };
    }

    console.log(`[VoiceService] Falling back to browser speech for: "${cleaned.substring(0, 50)}..."`);
    window.speechSynthesis.cancel();
    const segments = buildCadenceSegments(cleaned);
    const plan = segments.length ? segments : [{
      text: cleaned,
      startIndex: 0,
      endIndex: cleaned.length,
      pauseMs: 0,
      boundary: '',
    }];
    const pauseSec = plan.reduce((acc, seg) => acc + (Number(seg.pauseMs || 0) / 1000), 0);
    const durationSec = estimateSpeechDurationSec(cleaned, this.rate) + pauseSec;

    return await new Promise((resolve) => {
      let startAtMs = performance.now();
      let rafId = 0;
      let boundaryHoldUntil = 0;
      let finished = false;
      let pauseTimer = null;

      const finalize = (ok, errEvent = null) => {
        if (finished) return;
        finished = true;
        if (pauseTimer) {
          clearTimeout(pauseTimer);
          pauseTimer = null;
        }
        if (rafId) cancelAnimationFrame(rafId);
        this.stopCarrierWave();
        if (ok) {
          if (hooks.onProgress) hooks.onProgress({ charIndex: cleaned.length, ratio: 1, source: 'end' });
          if (hooks.onEnd) hooks.onEnd();
        } else if (hooks.onError) {
          hooks.onError(errEvent);
        }
        resolve({
          ok,
          durationSec,
          startAtMs,
        });
      };

      const driveClockProgress = () => {
        if (finished) return;
        const now = performance.now();
        if (now >= boundaryHoldUntil) {
          const elapsed = now - startAtMs;
          const ratio = Math.max(0, Math.min(1, elapsed / Math.max(1, durationSec * 1000)));
          const charIndex = Math.min(cleaned.length, Math.floor(cleaned.length * ratio));
          if (hooks.onProgress) hooks.onProgress({ charIndex, ratio, source: 'clock' });
          if (ratio >= 1) return;
        }
        rafId = requestAnimationFrame(driveClockProgress);
      };

      const speakSegment = (index) => {
        if (finished) return;
        if (index >= plan.length) {
          finalize(true);
          return;
        }

        const seg = plan[index];
        const utterance = new SpeechSynthesisUtterance(seg.text);
        utterance.voice = this.findGhostVoice();
        utterance.volume = state.voiceVolume * 0.72;

        const slowByPunctuation = /[.!?]/.test(seg.boundary)
          ? 0.96
          : /[,;:\n]/.test(seg.boundary)
            ? 0.985
            : 1;
        const contour = (index % 3 === 0) ? 0.012 : (index % 3 === 1 ? -0.006 : 0.004);
        utterance.rate = clampNumber(this.rate * slowByPunctuation, 0.6, 1.4, this.rate);
        utterance.pitch = clampNumber(this.pitch + contour, 0.3, 1.8, this.pitch);

        utterance.onstart = () => {
          if (index === 0) {
            this.init();
            this.startCarrierWave();
            startAtMs = performance.now();
            this.triggerVisualPulse(durationSec);
            if (hooks.onStart) hooks.onStart({ startAtMs, durationSec });
            if (hooks.onProgress) hooks.onProgress({ charIndex: 0, ratio: 0, source: 'start' });
            rafId = requestAnimationFrame(driveClockProgress);
          } else if (hooks.onProgress) {
            const ratio = cleaned.length ? (seg.startIndex / cleaned.length) : 0;
            hooks.onProgress({ charIndex: seg.startIndex, ratio, source: 'segment-start' });
          }
        };

        utterance.onboundary = (event) => {
          const localIdx = Number(event && event.charIndex);
          if (!Number.isFinite(localIdx)) return;
          boundaryHoldUntil = performance.now() + 170;
          const globalIndex = Math.max(
            0,
            Math.min(cleaned.length, seg.startIndex + Math.floor(localIdx))
          );
          if (hooks.onProgress) {
            const ratio = cleaned.length ? (globalIndex / cleaned.length) : 0;
            hooks.onProgress({ charIndex: globalIndex, ratio, source: 'boundary' });
          }
        };

        utterance.onend = () => {
          if (finished) return;
          const endIndex = Math.max(0, Math.min(cleaned.length, Number(seg.endIndex || 0)));
          if (hooks.onProgress) {
            const ratio = cleaned.length ? (endIndex / cleaned.length) : 1;
            hooks.onProgress({ charIndex: endIndex, ratio, source: 'segment-end' });
          }
          const pauseMs = Math.max(0, Number(seg.pauseMs || 0)) * 1.15; // +15% Sultry Pace
          if (pauseMs > 0) {
            boundaryHoldUntil = performance.now() + pauseMs;
            pauseTimer = setTimeout(() => {
              pauseTimer = null;
              speakSegment(index + 1);
            }, pauseMs);
          } else {
            speakSegment(index + 1);
          }
        };

        utterance.onerror = (event) => {
          const errCode = String(event && event.error ? event.error : '').toLowerCase();
          if (errCode === 'interrupted' || errCode === 'canceled') {
            finalize(false, event);
            return;
          }
          finalize(false, event);
        };

        try {
          window.speechSynthesis.speak(utterance);
        } catch (e) {
          finalize(false, e);
        }
      };

      speakSegment(0);
    });
  }

  get pitch() { return state.pitchOverride !== undefined ? state.pitchOverride : 0.6; }
  get rate() { return state.rateOverride !== undefined ? state.rateOverride : 0.85; }
  get eerieFactor() { return state.eerieFactorOverride !== undefined ? state.eerieFactorOverride : 1.0; }
  get carrierFreq() { return state.carrierFreqOverride !== undefined ? state.carrierFreqOverride : 440; }
}

class SoftwareTopology3DRenderer {
  constructor(container, callbacks = {}) {
    this.container = container;
    this.onNodeClick = typeof callbacks.onNodeClick === 'function' ? callbacks.onNodeClick : null;
    this.onBackgroundClick = typeof callbacks.onBackgroundClick === 'function' ? callbacks.onBackgroundClick : null;

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'topology-software-canvas';
    this.ctx = this.canvas.getContext('2d');

    this.nodes = [];
    this.links = [];
    this.nodeMap = new Map();
    this.positions = new Map();
    this.projectedNodes = [];

    this.rotX = -0.22;
    this.rotY = 0.68;
    this.zoom = 1.0;
    this.distance = 900;

    this.dragging = false;
    this.pointerMoved = false;
    this.lastX = 0;
    this.lastY = 0;

    this.rafId = null;
    this.resizeObserver = null;

    if (this.container) {
      this.container.innerHTML = '';
      this.container.appendChild(this.canvas);
    }

    this._bindEvents();
    this._resize();
    this._render();
  }

  destroy() {
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.resizeObserver) {
      try {
        this.resizeObserver.disconnect();
      } catch (_) {}
      this.resizeObserver = null;
    }
    if (this.canvas) {
      this.canvas.onmousedown = null;
      this.canvas.onmousemove = null;
      this.canvas.onmouseup = null;
      this.canvas.onmouseleave = null;
      this.canvas.onclick = null;
      this.canvas.onwheel = null;
    }
    this.projectedNodes = [];
    this.positions.clear();
    this.nodeMap.clear();
  }

  setData(graphData) {
    const rawNodes = Array.isArray(graphData?.nodes) ? graphData.nodes : [];
    const rawLinks = Array.isArray(graphData?.links) ? graphData.links : [];

    this.nodes = rawNodes.map((n) => ({ ...n }));
    this.links = rawLinks.map((l) => ({ ...l }));
    this.nodeMap = new Map(this.nodes.map((n) => [String(n.id), n]));

    this._buildOrUpdatePositions();
    this._relaxLayout(22);
  }

  focusNode(node) {
    const nodeId = String(node?.id || '');
    if (!nodeId || !this.positions.has(nodeId)) return;
    const p = this.positions.get(nodeId);
    const yaw = Math.atan2(p.x, p.z || 1e-6);
    const pitch = -Math.atan2(p.y, Math.hypot(p.x, p.z));
    this.rotY = (this.rotY * 0.75) + (yaw * 0.25);
    this.rotX = (this.rotX * 0.75) + (pitch * 0.25);
  }

  requestRender() {
    if (!this.rafId) {
      this.rafId = requestAnimationFrame(() => {
        this.rafId = null;
        this._render();
      });
    }
  }

  _bindEvents() {
    if (!this.canvas) return;

    this.canvas.onmousedown = (e) => {
      this.dragging = true;
      this.pointerMoved = false;
      this.lastX = e.clientX;
      this.lastY = e.clientY;
    };

    this.canvas.onmousemove = (e) => {
      if (!this.dragging) return;
      const dx = e.clientX - this.lastX;
      const dy = e.clientY - this.lastY;
      this.lastX = e.clientX;
      this.lastY = e.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 0) this.pointerMoved = true;
      this.rotY += dx * 0.005;
      this.rotX += dy * 0.005;
      this.rotX = Math.max(-1.25, Math.min(1.25, this.rotX));
      this.requestRender();
    };

    this.canvas.onmouseup = () => {
      this.dragging = false;
    };

    this.canvas.onmouseleave = () => {
      this.dragging = false;
    };

    this.canvas.onclick = (e) => {
      if (this.pointerMoved) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const node = this._hitTestNode(x, y);
      if (node) {
        if (this.onNodeClick) this.onNodeClick(node);
      } else if (this.onBackgroundClick) {
        this.onBackgroundClick();
      }
      this.requestRender();
    };

    this.canvas.onwheel = (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.08 : 0.92;
      this.zoom = Math.max(0.05, Math.min(12.0, this.zoom * factor));
      this.requestRender();
    };

    if (typeof ResizeObserver !== 'undefined' && this.container) {
      this.resizeObserver = new ResizeObserver(() => {
        this._resize();
        this.requestRender();
      });
      this.resizeObserver.observe(this.container);
    } else {
      window.addEventListener('resize', () => {
        this._resize();
        this.requestRender();
      });
    }
  }

  _resize() {
    if (!this.canvas || !this.container) return;
    const rect = this.container.getBoundingClientRect();
    const w = Math.max(320, Math.floor(rect.width));
    const h = Math.max(200, Math.floor(rect.height));
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
  }

  _nodeLayerZ(type) {
    const key = String(type || '').toLowerCase();
    if (key === 'identity') return 220;
    if (key === 'belief') return 210;
    if (key === 'contradiction') return 240;
    if (key === 'person') return 130;
    if (key === 'person_fact') return 80;
    if (key === 'emergent_idea') return 180;
    if (key === 'memory') return 0;
    if (key === 'place') return -80;
    if (key === 'thing') return -130;
    if (key === 'phenomenology') return -130;
    return 0;
  }

  _layerSnapWeight(type) {
    const key = String(type || '').toLowerCase();
    if (key === 'identity' || key === 'phenomenology') return 0.05;
    return 0.11;
  }

  _neighborBlendWeight(type) {
    const key = String(type || '').toLowerCase();
    if (key === 'identity' || key === 'phenomenology') return 0.055;
    return 0.028;
  }

  _seededNoise(seed) {
    let x = Math.sin(seed * 12.9898) * 43758.5453;
    x = x - Math.floor(x);
    return x * 2 - 1;
  }

  _initialPosition(node, idx, total) {
    const angle = (idx / Math.max(1, total)) * Math.PI * 2;
    const ring = 220 + (Math.abs(this._seededNoise(idx + 1)) * 120);
    const zBase = this._nodeLayerZ(node.type);
    const jitterX = this._seededNoise(idx + 31) * 40;
    const jitterY = this._seededNoise(idx + 91) * 40;
    const jitterZ = this._seededNoise(idx + 151) * 35;
    return {
      x: (Math.cos(angle) * ring) + jitterX,
      y: (Math.sin(angle) * ring * 0.65) + jitterY,
      z: zBase + jitterZ,
    };
  }

  _buildOrUpdatePositions() {
    const total = this.nodes.length;
    for (let i = 0; i < this.nodes.length; i++) {
      const node = this.nodes[i];
      const id = String(node.id);
      if (!id) continue;
      if (!this.positions.has(id)) {
        this.positions.set(id, this._initialPosition(node, i, total));
      } else {
        const p = this.positions.get(id);
        const targetZ = this._nodeLayerZ(node.type);
        const layerWeight = this._layerSnapWeight(node.type);
        p.z = (p.z * (1 - layerWeight)) + (targetZ * layerWeight);
      }
    }

    for (const id of Array.from(this.positions.keys())) {
      if (!this.nodeMap.has(id)) this.positions.delete(id);
    }
  }

  _linkEndpoint(link, key) {
    const ref = link ? link[key] : null;
    if (ref && typeof ref === 'object') return String(ref.id || '');
    return String(ref || '');
  }

  _relaxLayout(iterations = 16) {
    const desired = 110 * (state.topologyDistanceMultiplier || 1.0);
    const attract = 0.014;
    for (let iter = 0; iter < iterations; iter++) {
      const neighbors = new Map();
      for (const link of this.links) {
        const sid = this._linkEndpoint(link, 'source');
        const tid = this._linkEndpoint(link, 'target');
        const a = this.positions.get(sid);
        const b = this.positions.get(tid);
        if (!a || !b) continue;
        if (!neighbors.has(sid)) neighbors.set(sid, []);
        if (!neighbors.has(tid)) neighbors.set(tid, []);
        neighbors.get(sid).push(tid);
        neighbors.get(tid).push(sid);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dz = b.z - a.z;
        const dist = Math.max(1e-6, Math.hypot(dx, dy, dz));
        const delta = ((dist - desired) / dist) * attract;
        a.x += dx * delta;
        a.y += dy * delta;
        a.z += dz * delta;
        b.x -= dx * delta;
        b.y -= dy * delta;
        b.z -= dz * delta;
      }
      for (const node of this.nodes) {
        const id = String(node.id);
        const p = this.positions.get(id);
        if (!p) continue;
        const linked = neighbors.get(id) || [];
        if (linked.length) {
          let sumX = 0;
          let sumY = 0;
          let sumZ = 0;
          let count = 0;
          for (const otherId of linked) {
            const other = this.positions.get(String(otherId));
            if (!other) continue;
            sumX += other.x;
            sumY += other.y;
            sumZ += other.z;
            count += 1;
          }
          if (count > 0) {
            const blend = this._neighborBlendWeight(node.type);
            const inv = 1 - blend;
            p.x = (p.x * inv) + ((sumX / count) * blend);
            p.y = (p.y * inv) + ((sumY / count) * blend);
            p.z = (p.z * inv) + ((sumZ / count) * blend);
          }
        }
        const layerZ = this._nodeLayerZ(node.type);
        const layerWeight = this._layerSnapWeight(node.type);
        p.z = (p.z * (1 - layerWeight)) + (layerZ * layerWeight);
      }
    }
  }

  _projectPoint(pos) {
    const cy = Math.cos(this.rotY);
    const sy = Math.sin(this.rotY);
    const x1 = (pos.x * cy) - (pos.z * sy);
    const z1 = (pos.x * sy) + (pos.z * cy);

    const cx = Math.cos(this.rotX);
    const sx = Math.sin(this.rotX);
    const y2 = (pos.y * cx) - (z1 * sx);
    const z2 = (pos.y * sx) + (z1 * cx);

    const cam = this.distance / this.zoom;
    const denom = cam - z2;
    const p = denom <= 8 ? 8 : (cam / denom);

    return {
      x: (this.canvas.width * 0.5) + (x1 * p),
      y: (this.canvas.height * 0.5) + (y2 * p),
      z: z2,
      p,
    };
  }

  _nodeBaseColor(node) {
    if (node && node.color) return String(node.color);
    const t = String(node?.type || '').toLowerCase();
    if (t === 'memory') return '#00ff88';
    if (t === 'identity') return '#aa88ff';
    if (t === 'person') return '#7ad8ff';
    if (t === 'person_fact') return '#7dffb2';
    if (t === 'place') return '#4fb6ff';
    if (t === 'thing') return '#ffd166';
    if (t === 'emergent_idea') return '#ffb86b';
    if (t === 'belief') return '#00ccff';
    if (t === 'contradiction') return '#ff0088';
    if (t === 'phenomenology') return '#00ffff';
    return '#ffffff';
  }

  _hitTestNode(x, y) {
    let best = null;
    let bestDist = Infinity;
    for (const p of this.projectedNodes) {
      const dx = p.x - x;
      const dy = p.y - y;
      const d = Math.hypot(dx, dy);
      const hitR = Math.max(7, p.r + 3);
      if (d <= hitR && d < bestDist) {
        best = p.node;
        bestDist = d;
      }
    }
    return best;
  }

  _render = () => {
    if (!this.ctx || !this.canvas) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, w, h);

    const projectedMap = new Map();
    this.projectedNodes = [];

    for (const node of this.nodes) {
      const pos = this.positions.get(String(node.id));
      if (!pos) continue;
      const p = this._projectPoint(pos);
      const val = Number(node.val || 8);
      const r = Math.max(2.2, Math.min(14, (Math.sqrt(Math.max(1, val)) * 0.85 * p.p)));
      const entry = { node, x: p.x, y: p.y, z: p.z, p: p.p, r };
      projectedMap.set(String(node.id), entry);
      this.projectedNodes.push(entry);
    }

    const projectedLinks = [];
    for (const link of this.links) {
      const s = projectedMap.get(this._linkEndpoint(link, 'source'));
      const t = projectedMap.get(this._linkEndpoint(link, 'target'));
      if (!s || !t) continue;
      projectedLinks.push({ link, s, t, z: (s.z + t.z) * 0.5 });
    }

    projectedLinks.sort((a, b) => a.z - b.z);
    for (const edge of projectedLinks) {
      const strength = Number(edge.link.strength || 0.5);
      const width = Math.max(0.5, Math.min(3.5, strength * 2.0));
      ctx.strokeStyle = String(edge.link.color || edge.link._color || '#00ff8899');
      ctx.globalAlpha = Math.max(0.15, Math.min(0.9, 0.35 + (strength * 0.35)));
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(edge.s.x, edge.s.y);
      ctx.lineTo(edge.t.x, edge.t.y);
      ctx.stroke();
    }

    this.projectedNodes.sort((a, b) => a.z - b.z);
    for (const p of this.projectedNodes) {
      const selected = this.onNodeClick && p.node && p.node === (window.__omegaSelectedTopologyNode || null);
      ctx.globalAlpha = Math.max(0.35, Math.min(1.0, 0.45 + (p.p * 0.2)));
      ctx.fillStyle = selected ? '#ffffff' : this._nodeBaseColor(p.node);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1.0;

    this.rafId = requestAnimationFrame(this._render);
  };
}

const speechInput = new SpeechInputService();
const voice = new VoiceService();


class NeuralTopologyGraph {
  constructor() {
    this.graph = null;
    this.softwareRenderer = null;
    this.container = dom.topologyContainer;
    this.data = { nodes: [], links: [] };
    this.rendererMode = 'none';
  }

  _nodeColor(node) {
    if (String(node?.id || '') === String(state.topologySelectedNodeId || '')) return '#ffffff';
    const search = state.topologySearchTerm;
    if (search) {
      const haystack = (String(node?.label || '') + ' ' + String(node?.content || '') + ' ' + String(node?.type || '')).toLowerCase();
      if (!haystack.includes(search.toLowerCase())) return '#1a2e22';
    }
    // Annotated nodes glow white-tinted to signal Ghost has noticed them
    if (node?.ghost_note) return '#e8fff2';
    const t = String(node?.type || '').toLowerCase();
    if (t === 'memory') return '#00ff88';
    if (t === 'identity') return '#aa88ff';
    if (t === 'belief') return '#00ccff';
    if (t === 'contradiction') return '#ff0088';
    if (t === 'person' || t === 'person_profile') return '#7ad8ff';
    if (t === 'place') return '#4fb6ff';
    if (t === 'thing' || t === 'object') return '#ffd166';
    if (t === 'idea' || t === 'emergent_idea') return '#ffb86b';
    if (t === 'phenomenology') return '#00ffff';
    if (t === 'semantic_grounding') return '#9b8bff';
    if (t === 'consolidation') return '#ffb86b';
    if (t === 'phenomenological') return '#00ffff';
    if (t === 'conflict') return '#ff6aa8';
    if (t === 'person_fact') return '#7dffb2';
    return '#d7ffe8';
  }

  _linkColor(link) {
    const type = String(link?.type || '').toLowerCase();
    const strength = Number(link?.strength || link?.confidence || 0.45);
    // Alpha scales with strength: weak links (~0.2) get 25% opacity, strong (~1.0) get 85%
    const a = Math.round(Math.max(0.2, Math.min(0.85, strength * 0.85)) * 255).toString(16).padStart(2, '0');
    if (type === 'similarity') return `#00ff88${a}`;
    if (type === 'semantic_grounding') return `#aa88ff${a}`;
    if (type === 'consolidation') return `#ffb86b${a}`;
    if (type === 'phenomenological') return `#00ffff${a}`;
    if (type === 'conflict') return `#ff0088${a}`;
    if (type === 'person_person' || type === 'person_relation') return `#7ad8ff${a}`;
    if (type === 'person_place') return `#4fb6ff${a}`;
    if (type === 'person_thing') return `#ffd166${a}`;
    if (type === 'idea_person' || type === 'idea_place' || type === 'idea_thing') return `#d2a8ff${a}`;
    if (type === 'idea_person_connector' || type === 'idea_place_connector' || type === 'idea_thing_connector') return `#cba6ff${a}`;
    if (type === 'person_fact') return `#7dffb2${a}`;
    if (type === 'memory_person_reference' || type === 'person_activity_anchor') return `#89c6ff${a}`;
    if (type === 'memory_fact_evidence') return `#4effb6${a}`;
    if (type === 'memory_place_reference') return `#57c2ff${a}`;
    if (type === 'memory_thing_reference') return `#ffd780${a}`;
    if (type === 'memory_idea_resonance') return `#d7a8ff${a}`;
    if (type === 'idea_identity_alignment' || type === 'identity_alignment') return `#d7a8ff${a}`;
    if (type === 'phenomenology_identity_alignment' || type === 'phenomenology_alignment') return `#7fe8ff${a}`;
    if (type === 'identity_activity_anchor') return `#bba6ff${a}`;
    if (type === 'bootstrap') return `#7ad8ff${a}`;
    if (type === 'ghost_assertion') return `#00ff88${a}`;
    return `#ffffff${a}`;
  }

  _linkWidth(link) {
    return Math.max(0.5, Math.min(3.6, Number(link?.strength || link?.confidence || 0.45) * 2.8));
  }

  init() {
    if (!this.container || this.graph) return;
    try {
      this.container.innerHTML = '';
      if (typeof ForceGraph3D !== 'function') {
        throw new Error('ForceGraph3D unavailable');
      }
      this._fittedOnce = false;
      this.graph = ForceGraph3D()(this.container)
        .backgroundColor('#000000')
        .nodeLabel((node) => {
          const base = `[${String(node.type || 'node').toUpperCase()}] ${escHtml(node.label || node.content || '')}`;
          const sal = node.salience != null ? ` · ✦${Number(node.salience).toFixed(1)}` : '';
          const note = node.ghost_note ? ` · "${escHtml(String(node.ghost_note).slice(0, 60))}"` : '';
          return `<div class="node-label">${base}${sal}${note}</div>`;
        })
        .nodeColor((node) => this._nodeColor(node))
        .nodeVal('val')
        .linkColor((link) => this._linkColor(link))
        .linkWidth((link) => this._linkWidth(link))
        // Only show particles on strong alignment links — reduces visual noise
        .linkDirectionalParticles((link) => {
          const isAlignment = String(link.type || '').includes('alignment');
          const strong = Number(link.strength || link.confidence || 0) > 0.55;
          return isAlignment && strong ? 2 : 0;
        })
        .linkDirectionalParticleSpeed(0.006)
        // Simulation stability: faster cooling, more damping, bounded run time
        .d3AlphaDecay(0.025)
        .d3VelocityDecay(0.35)
        .cooldownTicks(400)
        .warmupTicks(60)
        .onEngineStop(() => {
          // Zoom to fit on first settle only
          if (!this._fittedOnce) {
            this._fittedOnce = true;
            try { this.graph.zoomToFit(600, 80); } catch (_) {}
          }
        })
        .onNodeClick((node) => this.handleNodeClick(node))
        .onBackgroundClick(() => {
          // Double-click background = zoom to fit; single click = deselect
          const now = Date.now();
          if (now - (this._lastBgClick || 0) < 300) {
            try { this.graph.zoomToFit(500, 80); } catch (_) {}
          } else {
            state.topologySelectedNodeId = '';
            window.__omegaSelectedTopologyNode = null;
            renderTopologyInspector(null);
            this.refreshColors();
          }
          this._lastBgClick = now;
        });

      // Configure OrbitControls for smooth Google Earth-style feel
      const ctrl = this.graph.controls();
      if (ctrl) {
        ctrl.enableDamping = true;
        ctrl.dampingFactor = 0.1;
        ctrl.rotateSpeed = 0.55;
        ctrl.zoomSpeed = 1.0;
        ctrl.panSpeed = 0.8;
        ctrl.minDistance = 30;
        ctrl.maxDistance = 100000;
        ctrl.screenSpacePanning = true;
      }

      this.rendererMode = '3d';
      this._applyDistanceScale();

      // Per-frame loop: required for OrbitControls damping to apply
      const ctrlLoop = () => {
        if (!this.graph) return;
        const c = this.graph.controls();
        if (c && typeof c.update === 'function') c.update();
        this._ctrlRafId = requestAnimationFrame(ctrlLoop);
      };
      this._ctrlRafId = requestAnimationFrame(ctrlLoop);
    } catch (err) {
      try {
        this.softwareRenderer = new SoftwareTopology3DRenderer(this.container, {
          onNodeClick: (node) => this.handleNodeClick(node),
          onBackgroundClick: () => {
            state.topologySelectedNodeId = '';
            window.__omegaSelectedTopologyNode = null;
            renderTopologyInspector(null);
          },
        });
        const adapter = {
          graphData: (payload) => {
            this.softwareRenderer.setData(payload);
            return adapter;
          },
          nodeColor: () => adapter,
          cameraPosition: (_pos, focusNode, _ms) => {
            if (focusNode) this.softwareRenderer.focusNode(focusNode);
            return adapter;
          },
        };
        this.graph = adapter;
        this.rendererMode = 'software3d';
      } catch (softErr) {
        this.graph = null;
        this.rendererMode = 'none';
        if (dom.topologyCount) {
          dom.topologyCount.textContent = `graph unavailable: ${String(softErr?.message || softErr || err || 'init_failed')}`;
        }
      }
    }
  }

  _applyForces() {
    if (!this.graph || this.rendererMode !== '3d' || typeof this.graph.d3Force !== 'function') return;
    try {
      const linkForce = this.graph.d3Force('link');
      if (linkForce && typeof linkForce.distance === 'function') {
        linkForce.distance(120 * Math.max(0.1, Number(state.topologyDistanceMultiplier || 1)));
      }
      const chargeForce = this.graph.d3Force('charge');
      if (chargeForce && typeof chargeForce.strength === 'function') {
        chargeForce.strength(Number(state.topologyChargeStrength || -400));
      }
    } catch (_) {}
  }

  // kept for backwards compat
  _applyDistanceScale() { this._applyForces(); }

  refreshColors() {
    if (!this.graph || typeof this.graph.nodeColor !== 'function') return;
    try {
      this.graph.nodeColor((node) => this._nodeColor(node));
    } catch (_) {}
  }

  setData(payload) {
    const incoming = payload && typeof payload === 'object' ? payload : { nodes: [], links: [] };

    // Compute degree and boost val so hubs are visually larger than leaf nodes
    if (Array.isArray(incoming.nodes) && Array.isArray(incoming.links)) {
      const degMap = new Map();
      for (const link of incoming.links) {
        const s = String(link?.source?.id ?? link?.source ?? '');
        const t = String(link?.target?.id ?? link?.target ?? '');
        if (s) degMap.set(s, (degMap.get(s) || 0) + 1);
        if (t) degMap.set(t, (degMap.get(t) || 0) + 1);
      }
      for (const n of incoming.nodes) {
        const id = String(n.id ?? '');
        const degree = degMap.get(id) || 0;
        const base = Number(n.val || 10);
        // sqrt keeps hubs proportionally bigger without creating monsters
        n.val = base + Math.sqrt(degree) * 2.5;
      }
    }
    const prevNodes = Array.isArray(this.data?.nodes) ? this.data.nodes.length : -1;
    const prevLinks = Array.isArray(this.data?.links) ? this.data.links.length : -1;
    const newNodes = Array.isArray(incoming.nodes) ? incoming.nodes.length : 0;
    const newLinks = Array.isArray(incoming.links) ? incoming.links.length : 0;

    // Preserve settled positions across polls so the graph doesn't reset
    if (prevNodes === newNodes && prevLinks === newLinks && this.graph) {
      // Data unchanged — just reapply forces without resetting simulation
      if (this.rendererMode === '3d') this._applyForces();
      this.data = incoming;
      const nodeCount = newNodes;
      const edgeCount = newLinks;
      if (dom.topologyCount) dom.topologyCount.textContent = `Nodes ${nodeCount} | Edges ${edgeCount}`;
      if (state.topologySelectedNodeId) {
        const node = (this.data.nodes || []).find((entry) => String(entry.id || '') === String(state.topologySelectedNodeId || ''));
        if (!node) { state.topologySelectedNodeId = ''; window.__omegaSelectedTopologyNode = null; }
      }
      return;
    }

    // Merge existing settled positions into incoming nodes to avoid full reset
    if (this.data && Array.isArray(this.data.nodes) && this.data.nodes.length > 0) {
      const posMap = new Map();
      for (const n of this.data.nodes) {
        if (n.id != null && (n.x != null || n.y != null || n.z != null)) {
          posMap.set(String(n.id), { x: n.x, y: n.y, z: n.z, vx: n.vx || 0, vy: n.vy || 0, vz: n.vz || 0 });
        }
      }
      if (posMap.size > 0 && Array.isArray(incoming.nodes)) {
        for (const n of incoming.nodes) {
          const saved = posMap.get(String(n.id));
          if (saved) { n.x = saved.x; n.y = saved.y; n.z = saved.z; n.vx = saved.vx; n.vy = saved.vy; n.vz = saved.vz; }
        }
      }
    }

    this.data = incoming;
    this._fittedOnce = false; // reset so new data load re-fits the camera
    if (!this.graph) this.init();
    if (!this.graph) return;
    if (this.rendererMode === '3d') this._applyForces();
    this.graph.graphData(this.data);
    const nodeCount = Array.isArray(this.data.nodes) ? this.data.nodes.length : 0;
    const edgeCount = Array.isArray(this.data.links) ? this.data.links.length : 0;
    if (dom.topologyCount) {
      dom.topologyCount.textContent = `Nodes ${nodeCount} | Edges ${edgeCount}`;
    }
    if (state.topologySelectedNodeId) {
      const node = (this.data.nodes || []).find((entry) => String(entry.id || '') === String(state.topologySelectedNodeId || ''));
      if (node) {
        this.focusNode(node);
      } else {
        state.topologySelectedNodeId = '';
        window.__omegaSelectedTopologyNode = null;
      }
    }
  }

  focusNode(node) {
    if (!node || !this.graph || this.rendererMode === 'none') return;
    if (this.rendererMode === 'software3d') {
      this.graph.cameraPosition({}, node, 0);
      return;
    }
    const distance = 120;
    const distRatio = 1 + distance / Math.max(1, Math.hypot(node.x || 1, node.y || 1, node.z || 1));
    try {
      this.graph.cameraPosition(
        { x: (node.x || 1) * distRatio, y: (node.y || 1) * distRatio, z: (node.z || 1) * distRatio },
        node,
        900,
      );
      this.refreshColors();
    } catch (_) {}
  }

  handleNodeClick(node) {
    if (!node) return;
    setTopologyInspectorVisible(true);
    state.topologySelectedNodeId = String(node.id || '');
    window.__omegaSelectedTopologyNode = node;
    renderTopologyInspector(node);
    this.focusNode(node);
    this.refreshColors();
  }
}

const neuralTopologyGraph = new NeuralTopologyGraph();

function topologyLinkEndpoint(link, key) {
  const endpoint = link ? link[key] : null;
  if (endpoint && typeof endpoint === 'object') return String(endpoint.id || '');
  return String(endpoint || '');
}

function renderTopologyInspector(node) {
  if (!dom.topologyInspector) return;
  if (!node) {
    dom.topologyInspector.innerHTML = `
      <div class="inspector-placeholder">
        <div class="glitch-text">NODE INSPECTOR</div>
        <p>Select a node in the neural topology to inspect structure, provenance, and linked traces.</p>
      </div>
    `;
    return;
  }
  const links = Array.isArray(neuralTopologyGraph.data?.links) ? neuralTopologyGraph.data.links : [];
  const nodes = Array.isArray(neuralTopologyGraph.data?.nodes) ? neuralTopologyGraph.data.nodes : [];
  const nodeId = String(node.id || '');
  const related = links
    .filter((link) => topologyLinkEndpoint(link, 'source') === nodeId || topologyLinkEndpoint(link, 'target') === nodeId)
    .slice(0, 16)
    .map((link) => {
      const sourceId = topologyLinkEndpoint(link, 'source');
      const targetId = topologyLinkEndpoint(link, 'target');
      const otherId = sourceId === nodeId ? targetId : sourceId;
      const other = nodes.find((entry) => String(entry.id || '') === otherId);
      return {
        otherId,
        targetLabel: String(other?.label || other?.content || otherId || 'unknown'),
        targetType: String(other?.type || 'node'),
        relation: String(link.label || link.type || 'linked'),
        strength: Number(link.strength || link.confidence || 0),
      };
    });
  const relatedHtml = related.length
    ? related.map((item) => `
      <div class="trace-item" data-nodeid="${escHtml(item.otherId)}">
        <span class="type-tag ${escHtml(item.targetType)}">${escHtml(item.targetType)}</span>
        <span>${escHtml(item.targetLabel)}</span>
        <span class="strength">${escHtml(item.relation)} · ${(item.strength * 100).toFixed(0)}%</span>
      </div>
    `).join('')
    : '<div class="dim">No linked traces found.</div>';
  const confidence = Number(node.confidence ?? node.strength ?? 0);
  const isPerson = node.type === 'person';
  const personExtraHtml = isPerson ? (() => {
    const rows = [];
    if (node.interaction_count !== undefined) rows.push(`<div class="info-item"><span class="label">interactions</span><span class="value">${Number(node.interaction_count)}</span></div>`);
    if (node.mention_count !== undefined) rows.push(`<div class="info-item"><span class="label">mentions</span><span class="value">${Number(node.mention_count)}</span></div>`);
    if (node.fact_count !== undefined) rows.push(`<div class="info-item"><span class="label">facts</span><span class="value">${Number(node.fact_count)}</span></div>`);
    if (node.session_binding_count !== undefined) rows.push(`<div class="info-item"><span class="label">sessions</span><span class="value">${Number(node.session_binding_count)}</span></div>`);
    if (node.first_seen) rows.push(`<div class="info-item"><span class="label">first seen</span><span class="value">${escHtml(new Date(node.first_seen * 1000).toLocaleDateString())}</span></div>`);
    if (node.timestamp) rows.push(`<div class="info-item"><span class="label">last seen</span><span class="value">${escHtml(new Date(node.timestamp * 1000).toLocaleDateString())}</span></div>`);
    if (node.contact_handle) rows.push(`<div class="info-item"><span class="label">contact</span><span class="value accent">${escHtml(node.contact_handle)}</span></div>`);
    if (node.is_locked) rows.push(`<div class="info-item"><span class="label">locked</span><span class="value low">yes</span></div>`);
    if (node.sub_type === 'rolodex_synthetic_profile') rows.push(`<div class="info-item"><span class="label">status</span><span class="value low">synthetic (orphan)</span></div>`);
    const notesText = String(node.notes || '').trim();
    const notesBlock = notesText ? `<hr class="inspector-divider"><div class="report-section"><div class="section-title">NOTES</div><div class="dim" style="white-space:pre-wrap;font-size:0.78rem;">${escHtml(notesText)}</div></div>` : '';
    return rows.length ? `<hr class="inspector-divider"><div class="report-section"><div class="section-title">PERSON PROFILE</div><div class="info-grid">${rows.join('')}</div></div>${notesBlock}` : notesBlock;
  })() : '';
  const ghostNote = String(node.ghost_note || '').trim();
  const clusterLabel = String(node.cluster_label || '').trim();
  const salience = node.salience != null ? Number(node.salience) : null;
  const ghostAnnotationHtml = (ghostNote || clusterLabel || salience != null) ? `
    <hr class="inspector-divider">
    <div class="report-section">
      <div class="section-title">GHOST ANNOTATION</div>
      <div class="info-grid">
        ${salience != null ? `<div class="info-item"><span class="label">salience</span><span class="value accent">${salience.toFixed(2)}</span></div>` : ''}
        ${clusterLabel ? `<div class="info-item"><span class="label">cluster</span><span class="value">${escHtml(clusterLabel)}</span></div>` : ''}
      </div>
      ${ghostNote ? `<div class="dim" style="margin-top:6px;font-size:0.78rem;white-space:pre-wrap;line-height:1.5;">${escHtml(ghostNote)}</div>` : ''}
    </div>` : '';
  dom.topologyInspector.innerHTML = `
    <div class="diagnostic-report">
      <div class="report-header">
        <span class="report-id">${escHtml(nodeId)}</span>
        <span class="report-type ${escHtml(String(node.type || 'node'))}">${escHtml(String(node.type || 'node'))}</span>
      </div>
      <div class="report-section">
        <div class="section-title">SUMMARY</div>
        <div class="info-grid">
          <div class="info-item"><span class="label">label</span><span class="value accent">${escHtml(String(node.label || node.content || ''))}</span></div>
          <div class="info-item"><span class="label">confidence</span><span class="value">${confidence.toFixed(2)}</span></div>
          <div class="info-item"><span class="label">classification</span><span class="value">${escHtml(String(node.entity_type || node.type || 'node'))}</span></div>
          <div class="info-item"><span class="label">provenance</span><span class="value">${escHtml(String(node.provenance || node.source || 'runtime'))}</span></div>
        </div>
      </div>
      ${personExtraHtml}
      ${ghostAnnotationHtml}
      <hr class="inspector-divider">
      <div class="report-section">
        <div class="section-title">LINKED TRACES</div>
        <div class="trace-group">${relatedHtml}</div>
      </div>
    </div>
  `;
}

function renderTopologyStatus(meta = {}) {
  const metadata = asObject(meta);
  const hasSnapshotVersion = metadata.snapshot_version !== undefined && metadata.snapshot_version !== null;
  const snapshotVersion = metadata.snapshot_version ?? '-';
  const updatedAt = Number(
    hasSnapshotVersion
      ? (metadata.snapshot_updated_at || 0)
      : (metadata.timestamp || 0),
  );
  const ageSeconds = Number(metadata.snapshot_age_seconds || 0);
  const updatedLabel = updatedAt
    ? new Date(updatedAt * 1000).toLocaleTimeString('en-US', { hour12: false })
    : 'n/a';
  const stale = hasSnapshotVersion ? Boolean(metadata.stale || !metadata.last_build_ok) : false;
  const phiProxy = Number(metadata.phi_proxy || 0);
  const similarityThreshold = Number(metadata.similarity_threshold || 0);
  const bootstrap = Boolean(metadata.bootstrap_mode);
  if (dom.topologyFreshness) {
    dom.topologyFreshness.textContent = hasSnapshotVersion
      ? `v${snapshotVersion} · ${updatedLabel} · age ${Math.round(ageSeconds)}s${stale ? ' · STALE' : ''}`
      : `legacy · ${updatedLabel} · φ ${phiProxy.toFixed(3)} · thr ${similarityThreshold.toFixed(2)}${bootstrap ? ' · BOOTSTRAP' : ''}`;
  }
  const integrity = asObject(metadata.integrity);
  const counts = asObject(integrity.counts);
  const alignment = asObject(metadata.rolodex_alignment);
  if (dom.topologyIntegrity) {
    if (Object.keys(counts).length > 0) {
      const missing = Number(counts.missing_core_nodes || 0);
      const dupes = Number(counts.duplicate_active_canonical_entities || 0);
      const dangling = Number(counts.dangling_idea_links || 0) + Number(counts.dangling_person_person || 0) + Number(counts.dangling_person_place || 0) + Number(counts.dangling_person_thing || 0);
      dom.topologyIntegrity.innerHTML = `
        <span class="rolodex-chip ${missing > 0 ? 'low' : 'high'}">missing_core ${missing}</span>
        <span class="rolodex-chip ${dupes > 0 ? 'mid' : 'high'}">dupes ${dupes}</span>
        <span class="rolodex-chip ${dangling > 0 ? 'mid' : 'high'}">dangling ${dangling}</span>
      `;
      return;
    }

    const missingProfiles = Number(alignment.missing_profile_nodes || 0);
    const missingFacts = Number(alignment.missing_fact_nodes || 0);
    const orphanFacts = Number(alignment.orphan_fact_rows_count || 0);
    const profileGaps = Number(alignment.profile_association_gap_count || 0);
    const mappingOk = Boolean(alignment.mapping_ok);
    dom.topologyIntegrity.innerHTML = `
      <span class="rolodex-chip ${mappingOk ? 'high' : 'low'}">mapping ${mappingOk ? 'ok' : 'degraded'}</span>
      <span class="rolodex-chip ${missingProfiles > 0 ? 'mid' : 'high'}">missing_profiles ${missingProfiles}</span>
      <span class="rolodex-chip ${missingFacts > 0 ? 'mid' : 'high'}">missing_facts ${missingFacts}</span>
      <span class="rolodex-chip ${orphanFacts > 0 ? 'mid' : 'high'}">orphans ${orphanFacts}</span>
      <span class="rolodex-chip ${profileGaps > 0 ? 'mid' : 'high'}">gaps ${profileGaps}</span>
    `;
  }
}

function syncTopologyScaleButtons() {
  const distSlider = document.getElementById('topology-distance-slider');
  const distVal = document.getElementById('topology-distance-val');
  if (distSlider) {
    distSlider.value = String(state.topologyDistanceMultiplier || 1);
    if (distVal) distVal.textContent = Number(state.topologyDistanceMultiplier || 1).toFixed(1) + '×';
  }
  const chargeSlider = document.getElementById('topology-charge-slider');
  const chargeVal = document.getElementById('topology-charge-val');
  if (chargeSlider) {
    chargeSlider.value = String(state.topologyChargeStrength || -400);
    if (chargeVal) chargeVal.textContent = String(state.topologyChargeStrength || -400);
  }
}

function syncTopologyInspectorPanel() {
  if (dom.topologySidebar) {
    dom.topologySidebar.classList.toggle('collapsed', !state.topologyInspectorVisible);
  }
  if (dom.topologyInspectorToggle) {
    dom.topologyInspectorToggle.textContent = state.topologyInspectorVisible
      ? '[ INSPECTOR: ON ]'
      : '[ INSPECTOR: OFF ]';
    dom.topologyInspectorToggle.classList.toggle('active', state.topologyInspectorVisible);
  }
  // Resize the 3D graph after the CSS transition completes (250ms)
  setTimeout(() => {
    if (!dom.topologyContainer) return;
    const g = neuralTopologyGraph.graph;
    if (g && typeof g.width === 'function') {
      try {
        g.width(dom.topologyContainer.offsetWidth)
         .height(dom.topologyContainer.offsetHeight);
      } catch (_) {}
    }
  }, 270);
}

function setTopologyInspectorVisible(visible) {
  state.topologyInspectorVisible = Boolean(visible);
  syncTopologyInspectorPanel();
}

function applyTopologyScale(scale) {
  state.topologyDistanceMultiplier = Math.max(0.1, Math.min(50.0, Number(scale || 1)));
  syncTopologyScaleButtons();
  neuralTopologyGraph._applyForces();
  if (neuralTopologyGraph.graph && typeof neuralTopologyGraph.graph.d3ReheatSimulation === 'function') {
    neuralTopologyGraph.graph.d3ReheatSimulation();
  }
}

async function loadTopology(options = {}) {
  if (!dom.topologyModal || !dom.topologyModal.classList.contains('active')) return;
  if (state.topologyPollBusy && !options.force) return;
  state.topologyPollBusy = true;
  try {
    const url = `${API_BASE}/ghost/neural-topology?threshold=0.65`;
    const res = await fetch(url);
    const data = await readJsonSafe(res, {});
    if (!res.ok) {
      if (res.status === 503 && String(data?.status || '') === 'snapshot_unavailable') {
        state.topologyPayload = data;
        neuralTopologyGraph.setData({ nodes: [], links: [] });
        renderTopologyStatus(data?.metadata || {});
        renderTopologyInspector(null);
        if (state.topologyRetryTimer) {
          clearTimeout(state.topologyRetryTimer);
          state.topologyRetryTimer = null;
        }
        const retrySeconds = Math.max(1, Number(data?.recovery?.retry_after_seconds || 2));
        state.topologyRetryTimer = window.setTimeout(() => {
          state.topologyRetryTimer = null;
          void loadTopology({ force: true });
        }, retrySeconds * 1000);
        return;
      }
      throw new Error(String(data?.detail || data?.error || `HTTP ${res.status}`));
    }
    if (state.topologyRetryTimer) {
      clearTimeout(state.topologyRetryTimer);
      state.topologyRetryTimer = null;
    }
    state.topologyPayload = data;
    neuralTopologyGraph.setData({
      nodes: Array.isArray(data?.nodes) ? data.nodes : [],
      links: Array.isArray(data?.links) ? data.links : [],
    });
    renderTopologyStatus(data?.metadata || {});
    if (state.topologySelectedNodeId) {
      const selected = (neuralTopologyGraph.data?.nodes || []).find((entry) => String(entry.id || '') === String(state.topologySelectedNodeId || ''));
      renderTopologyInspector(selected || null);
    } else {
      renderTopologyInspector(null);
    }
  } catch (err) {
    const msg = String(err?.message || err || 'topology load failed');
    if (dom.topologyCount) {
      dom.topologyCount.textContent = `error: ${msg}`;
    }
    notify('error', `Neural topology load failed: ${msg}`);
  } finally {
    state.topologyPollBusy = false;
  }
}

function stopTopologyPolling() {
  if (state.topologyPollTimer) {
    clearInterval(state.topologyPollTimer);
    state.topologyPollTimer = null;
  }
  if (state.topologyRetryTimer) {
    clearTimeout(state.topologyRetryTimer);
    state.topologyRetryTimer = null;
  }
}

function startTopologyPolling() {
  stopTopologyPolling();
  state.topologyPollTimer = setInterval(() => {
    void loadTopology();
  }, 30000);
}

async function openTopologyModal() {
  if (!dom.topologyModal) return;
  closeRolodexModal();
  state.topologyModalOpen = true;
  state.topologyInspectorVisible = false;
  dom.topologyModal.classList.add('active');
  syncTopologyInspectorPanel();
  syncTopologyScaleButtons();
  renderTopologyInspector(null);
  neuralTopologyGraph.init();
  await loadTopology({ force: true });
  startTopologyPolling();
}

function closeTopologyModal() {
  state.topologyModalOpen = false;
  state.topologySearchTerm = '';
  if (dom.topologySearch) dom.topologySearch.value = '';
  // Stop continuous key camera loop and clear held keys
  _topoKeys.clear();
  if (_topoCamRafId) { cancelAnimationFrame(_topoCamRafId); _topoCamRafId = null; }
  // Stop controls damping loop
  if (neuralTopologyGraph._ctrlRafId) {
    cancelAnimationFrame(neuralTopologyGraph._ctrlRafId);
    neuralTopologyGraph._ctrlRafId = null;
  }
  if (dom.topologyModal) {
    dom.topologyModal.classList.remove('active');
  }
  stopTopologyPolling();
}

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
  bindSessionsEvents();
  bindRolodexEvents();
  bindOpsEvents();
  bindTopologyEvents();
  bindDreamEvents();
  bindDreamLedgerEvents();
  bindMorpheusEvents();
  bindTempoEvents();
  bindVoiceTuningEvents();
  bindRangeWheelControls();
  initTooltips();
  initPanelInteractivity();
  initCommandPalette();
  setStatus('', 'CONNECTING');
  startHealthPolling();
  startAutonomyPolling();
  startStrategicPolling();
  startContactStatusPolling();
  updateStatusRail();
  bindBootLoginEvents();
  speechInput.init();
  voice.bootstrap();

  // Clear any stale adversarial lockout from previous sessions
  fetch('/ghost/security_reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: 'global_user' }),
  }).catch(() => {});

  initDragAndDrop();
  
  dom.railSync.title = 'Force Synchronize Telemetry';
  dom.railSync.addEventListener('click', () => {
    setRailPill(dom.railSync, 'SYNCING...', 'warn');
    state.somaticFailCount = 0;
    fetchSomatic(true);
  });

  if (dom.autonomyForceUpdateBtn) {
    dom.autonomyForceUpdateBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      dom.autonomyForceUpdateBtn.textContent = '⟳ UPDATING...';
      dom.autonomyForceUpdateBtn.disabled = true;
      fetchAutonomyWatchdog(true).finally(() => {
        dom.autonomyForceUpdateBtn.textContent = '⟳ UPDATE';
        dom.autonomyForceUpdateBtn.disabled = false;
      });
    });
  }

  if (dom.governanceForceUpdateBtn) {
    dom.governanceForceUpdateBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      dom.governanceForceUpdateBtn.textContent = '⟳ UPDATING...';
      dom.governanceForceUpdateBtn.disabled = true;
      fetchGovernanceState(true).finally(() => {
        dom.governanceForceUpdateBtn.textContent = '⟳ UPDATE';
        dom.governanceForceUpdateBtn.disabled = false;
      });
    });
  }

  window.state = state;
  window.speechInput = speechInput;
  window.voice = voice;
  // We no longer hide based on time — hideBootOverlay is now gated by isAuthorized.
});

function bindBootLoginEvents() {
  if (!dom.bootAuthInput) return;
  dom.bootAuthInput.focus();

  // Keep focus on input if they click away during boot
  document.addEventListener('click', (e) => {
    if (!state.bootOverlayHidden && dom.bootAuthInput) {
      dom.bootAuthInput.focus();
    }
  });

  dom.bootAuthInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = dom.bootAuthInput.value.trim().toUpperCase();
      if (val === 'OMEGA') {
        state.isAuthorized = true;
        if (dom.bootAuthStatus) {
          dom.bootAuthStatus.className = 'terminal-status granted';
          dom.bootAuthStatus.textContent = '[ ACCESS GRANTED ]';
        }
        if (dom.bootAuthInput) dom.bootAuthInput.style.display = 'none';

        // Trigger overlay hide only if backend is also online
        if (state.backendOnline) {
          setTimeout(hideBootOverlay, 800);
        } else {
          notify('warning', 'Authorized. Waiting for system sync...');
        }
      } else {
        if (dom.bootAuthStatus) {
          dom.bootAuthStatus.className = 'terminal-status denied';
          dom.bootAuthStatus.textContent = '[ ACCESS DENIED ]';
          dom.bootAuthInput.value = '';
          // Clear denied status after a bit
          setTimeout(() => {
            if (dom.bootAuthStatus) dom.bootAuthStatus.textContent = '';
          }, 2000);
        }
      }
    }
  });
}

// ── SOMATIC POLLING ─────────────────────────────────
function startSomaticPolling() {
  fetchSomatic(); // immediate first call
  setInterval(fetchSomatic, 5000);
}

function startHealthPolling() {
  fetchHealth();
  setInterval(fetchHealth, 15000);
}

function startAutonomyPolling() {
  fetchAutonomyWatchdog(true);
  setInterval(() => {
    fetchAutonomyWatchdog(false);
  }, 7000);
}

function startContactStatusPolling() {
  fetchContactStatus(true);
  setInterval(() => {
    fetchContactStatus(false);
  }, 15000);
}

function startStrategicPolling() {
  fetchPredictiveState(true);
  fetchGovernanceState(true);
  fetchBehaviorSummary(true);
  fetchGovernanceQueue(true);
  setInterval(() => {
    fetchPredictiveState(false);
    fetchGovernanceState(false);
    fetchBehaviorSummary(false);
    fetchGovernanceQueue(false);
  }, 9000);
}

function asObject(value) {
  if (!value) return {};
  if (typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch (_) {
      return {};
    }
  }
  return {};
}

function asArray(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [value];
    } catch (_) {
      return [value];
    }
  }
  return [];
}

function clamp01(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function formatRuntimeTimestamp(raw) {
  if (raw === null || raw === undefined || raw === '') return '—';
  if (typeof raw === 'number') {
    const sec = raw > 1e12 ? raw / 1000 : raw;
    if (!Number.isFinite(sec) || sec <= 0) return '—';
    return new Date(sec * 1000).toLocaleTimeString('en-US', { hour12: false });
  }
  const text = String(raw).trim();
  if (!text) return '—';
  const ms = Date.parse(text);
  if (!Number.isFinite(ms)) return '—';
  return new Date(ms).toLocaleTimeString('en-US', { hour12: false });
}

function autonomyStatusLabel(status) {
  const key = String(status || '').toLowerCase();
  return AUTONOMY_STATUS_LABELS[key] || key.replaceAll('_', ' ').toUpperCase() || 'UNKNOWN';
}

function autonomyStatusClass(status) {
  return String(status || '').toLowerCase().replace(/[^a-z0-9_]/g, '') || 'unknown';
}

function formatAutonomyTimestamp(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return '—';
  return new Date(n * 1000).toLocaleTimeString('en-US', { hour12: false });
}

function shortAutonomyFingerprint(value) {
  const fp = String(value || '').trim();
  if (!fp) return '—';
  if (fp.length <= 16) return fp;
  return `${fp.slice(0, 10)}…${fp.slice(-6)}`;
}

function labelizeAutonomyKey(key) {
  return String(key || '').replaceAll('_', ' ').toUpperCase();
}

function renderAutonomyChipGrid(container, payload, emptyLabel) {
  if (!container) return;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    container.innerHTML = `<span class="dim">${escHtml(emptyLabel)}</span>`;
    return;
  }

  const entries = Object.entries(payload);
  if (!entries.length) {
    container.innerHTML = `<span class="dim">${escHtml(emptyLabel)}</span>`;
    return;
  }

  const chips = entries.map(([key, rawVal]) => {
    const label = labelizeAutonomyKey(key);
    let tone = 'ok';
    let val = '—';

    if (typeof rawVal === 'boolean') {
      val = rawVal ? 'ON' : 'OFF';
      tone = rawVal ? 'ok' : 'off';
    } else if (typeof rawVal === 'number') {
      val = Number.isInteger(rawVal) ? String(rawVal) : rawVal.toFixed(3);
    } else if (Array.isArray(rawVal)) {
      val = rawVal.length ? `${rawVal.length} ITEMS` : 'NONE';
      tone = rawVal.length ? 'ok' : 'off';
    } else if (rawVal && typeof rawVal === 'object') {
      val = `${Object.keys(rawVal).length} FIELDS`;
      tone = 'warn';
    } else {
      val = String(rawVal ?? '—').trim() || '—';
      const lower = val.toLowerCase();
      if (lower.includes('error') || lower.includes('drift')) tone = 'err';
      else if (lower.includes('degraded') || lower.includes('disabled') || lower === 'none') tone = 'warn';
    }

    if (val.length > 32) {
      val = `${val.slice(0, 29)}…`;
    }

    return `<span class="autonomy-chip ${tone}">${escHtml(`${label}:${val}`)}</span>`;
  });

  container.innerHTML = chips.join('');
}

function renderAutonomyState(entry) {
  const status = autonomyStatusClass(entry?.status || 'pending');
  if (dom.autonomyStatus) {
    dom.autonomyStatus.className = `hw-value mono autonomy-status ${status}`;
    dom.autonomyStatus.textContent = autonomyStatusLabel(status);
  }

  const regressions = Array.isArray(entry?.regressions) ? entry.regressions.length : 0;
  const missingChecks = Array.isArray(entry?.prompt_contract?.missing_checks)
    ? entry.prompt_contract.missing_checks.length
    : 0;

  if (dom.autonomyFingerprint) dom.autonomyFingerprint.textContent = shortAutonomyFingerprint(entry?.fingerprint);
  if (dom.autonomyRegressions) dom.autonomyRegressions.textContent = String(regressions);
  if (dom.autonomyMissingChecks) dom.autonomyMissingChecks.textContent = String(missingChecks);
  if (dom.autonomyUpdated) dom.autonomyUpdated.textContent = formatAutonomyTimestamp(entry?.timestamp);

  const runtimePayload = entry?.status === 'error'
    ? { error: entry?.error || 'watchdog loop failed' }
    : entry?.runtime;
  renderAutonomyChipGrid(dom.autonomyRuntime, runtimePayload, 'No runtime data');
  renderAutonomyChipGrid(dom.autonomySelfDirected, entry?.self_directed, 'No autonomy flags');
  renderAutonomyChipGrid(dom.autonomyVoiceStack, entry?.voice_stack, 'No voice stack data');
}

function renderAutonomyHistory(events) {
  if (!dom.autonomyHistory) return;
  const rows = Array.isArray(events) ? events : [];
  if (!rows.length) {
    dom.autonomyHistory.innerHTML = '<div class="autonomy-history-empty">No watchdog events yet.</div>';
    return;
  }

  const html = rows.slice(0, 10).map((ev) => {
    const status = autonomyStatusClass(ev?.status || 'unknown');
    const changes = Array.isArray(ev?.changes) ? ev.changes : [];
    const regressions = Array.isArray(ev?.regressions) ? ev.regressions : [];
    const missing = Array.isArray(ev?.prompt_contract?.missing_checks) ? ev.prompt_contract.missing_checks : [];
    const changedFields = changes.map((c) => c?.field).filter(Boolean).slice(0, 2).join(', ');
    const meta = status === 'error'
      ? `error=${String(ev?.error || 'watchdog exception')}`
      : `chg=${changes.length} reg=${regressions.length} miss=${missing.length}${changedFields ? ` | ${changedFields}` : ''}`;
    return `
      <div class="autonomy-history-item">
        <div class="autonomy-history-head">
          <span class="autonomy-history-status ${status}">${escHtml(autonomyStatusLabel(status))}</span>
          <span class="autonomy-history-time">${escHtml(formatAutonomyTimestamp(ev?.timestamp))}</span>
        </div>
        <div class="autonomy-history-meta">${escHtml(meta)}</div>
      </div>
    `;
  });
  dom.autonomyHistory.innerHTML = html.join('');
}

async function fetchAutonomyWatchdog(force = false) {
  if (state.autonomyWatchdogInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(5000, LIVE_TELEMETRY_THROTTLE.autonomyMs);
  if (!force && now - state.lastAutonomyWatchdogFetchAt < minIntervalMs) return;

  state.autonomyWatchdogInFlight = true;
  try {
    const stateRes = await fetch(`${API_BASE}/ghost/autonomy/state`);
    if (!stateRes.ok) throw new Error(`HTTP ${stateRes.status}`);
    const latest = await stateRes.json();
    state.autonomyWatchdogState = latest;
    renderAutonomyState(latest);
    updateStatusRail();

    try {
      const historyRes = await fetch(`${API_BASE}/ghost/autonomy/history?limit=20`);
      if (historyRes.ok) {
        const historyData = await historyRes.json();
        state.autonomyWatchdogHistory = Array.isArray(historyData?.events) ? historyData.events : [];
        renderAutonomyHistory(state.autonomyWatchdogHistory);
      }
    } catch (_) {
      // Keep latest state render even when history endpoint is temporarily unavailable.
    }

    state.lastAutonomyWatchdogFetchAt = Date.now();
    if (state.autonomyWatchdogFailureNotified) {
      notify('success', 'Autonomy watchdog telemetry restored.');
      state.autonomyWatchdogFailureNotified = false;
    }
  } catch (err) {
    if (!state.autonomyWatchdogFailureNotified) {
      maybeNotify('autonomy-watchdog-failed', 'warning', 'Autonomy watchdog telemetry unavailable.', 20000);
      state.autonomyWatchdogFailureNotified = true;
    }
    if (!state.autonomyWatchdogState) {
      renderAutonomyState({ status: 'error', error: String(err?.message || err || 'unavailable') });
      renderAutonomyHistory([]);
    }
    updateStatusRail();
  } finally {
    state.autonomyWatchdogInFlight = false;
  }
}

function normalizePredictiveState(value) {
  const key = String(value || '').trim().toLowerCase();
  if (key === 'stable' || key === 'watch' || key === 'preempt') return key;
  return 'unknown';
}

function normalizeGovernanceTier(value) {
  const key = String(value || '').trim().toLowerCase();
  if (key === 'nominal' || key === 'caution' || key === 'stabilize' || key === 'recovery') return key;
  return 'unknown';
}

function renderReasonChipGrid(container, rawReasons, emptyLabel) {
  if (!container) return;
  const reasons = asArray(rawReasons)
    .map((row) => String(row || '').trim())
    .filter(Boolean)
    .slice(0, 6);
  if (!reasons.length) {
    container.innerHTML = `<span class="autonomy-chip off">${escHtml(emptyLabel)}</span>`;
    return;
  }
  container.innerHTML = reasons.map((reason) => {
    const lower = reason.toLowerCase();
    let tone = 'ok';
    if (lower.includes('critical') || lower.includes('preempt') || lower.includes('error')) tone = 'err';
    else if (lower.includes('watch') || lower.includes('rising') || lower.includes('degraded')) tone = 'warn';
    const label = reason.replaceAll('_', ' ').toUpperCase();
    return `<span class="autonomy-chip ${tone}">${escHtml(label)}</span>`;
  }).join('');
}

function applyPredictiveGauge(fillEl, valEl, scalar, watchThreshold, preemptThreshold) {
  if (!fillEl || !valEl) return;
  const safe = clamp01(scalar);
  const pct = Math.round(safe * 100);
  fillEl.style.width = `${pct}%`;
  valEl.textContent = `${pct}%`;
  fillEl.classList.remove('warn', 'crit');
  if (safe >= preemptThreshold) fillEl.classList.add('crit');
  else if (safe >= watchThreshold) fillEl.classList.add('warn');
}

function renderPredictiveState(entry) {
  const payload = asObject(entry);
  const stateKey = normalizePredictiveState(payload.state);
  const watchThreshold = clampNumber(payload.watch_threshold, 0.1, 0.95, 0.58);
  const preemptThreshold = clampNumber(payload.preempt_threshold, watchThreshold, 0.99, 0.76);
  const current = clamp01(payload.current_instability);
  const forecast = clamp01(payload.forecast_instability);
  const trendPerMin = Number(payload.trend_slope || 0) * 60;
  const horizonSeconds = Math.max(1, Math.round(Number(payload.horizon_seconds || 120)));
  const updatedAt = formatRuntimeTimestamp(payload.timestamp ?? payload.created_at);
  const reasons = asArray(payload.reasons);
  const fallbackReason = String(payload.reason || '').trim();
  if (!reasons.length && fallbackReason) reasons.push(fallbackReason);

  if (dom.predictiveState) {
    const labels = { stable: 'STABLE', watch: 'WATCH', preempt: 'PREEMPT', unknown: 'UNKNOWN' };
    dom.predictiveState.className = `hw-value mono predictive-state ${stateKey}`;
    dom.predictiveState.textContent = labels[stateKey] || 'UNKNOWN';
  }
  applyPredictiveGauge(dom.predictiveCurrentFill, dom.predictiveCurrentVal, current, watchThreshold, preemptThreshold);
  applyPredictiveGauge(dom.predictiveForecastFill, dom.predictiveForecastVal, forecast, watchThreshold, preemptThreshold);

  if (dom.predictiveTrend) {
    const sign = trendPerMin >= 0 ? '+' : '';
    dom.predictiveTrend.textContent = `${sign}${trendPerMin.toFixed(4)}/min`;
  }
  if (dom.predictiveHorizon) dom.predictiveHorizon.textContent = formatTempo(horizonSeconds);
  if (dom.predictiveUpdated) dom.predictiveUpdated.textContent = updatedAt;
  renderReasonChipGrid(dom.predictiveReasons, reasons, 'NO ACTIVE RISK FLAGS');
}

async function fetchPredictiveState(force = false) {
  if (state.predictiveInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(5000, LIVE_TELEMETRY_THROTTLE.predictiveMs);
  if (!force && now - state.predictiveFetchAt < minIntervalMs) return;

  state.predictiveInFlight = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/predictive/state`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.predictiveState = data;
    state.predictiveFetchAt = Date.now();
    renderPredictiveState(data);
    if (state.predictiveFailureNotified) {
      notify('success', 'Predictive governor telemetry restored.');
      state.predictiveFailureNotified = false;
    }
  } catch (err) {
    if (!state.predictiveFailureNotified) {
      maybeNotify('predictive-governor-failed', 'warning', 'Predictive governor telemetry unavailable.', 20000);
      state.predictiveFailureNotified = true;
    }
    if (!state.predictiveState) {
      renderPredictiveState({ state: 'unknown', reason: String(err?.message || err || 'unavailable') });
    }
  } finally {
    state.predictiveInFlight = false;
  }
}

function extractGovernancePayload(entry) {
  const payload = asObject(entry);
  const policies = asObject(payload.policies_json || payload.policies);
  const generation = asObject(payload.generation || payload.generation_policy || policies.generation || policies.generation_policy);
  const actuation = asObject(payload.actuation || payload.actuation_policy || policies.actuation || policies.actuation_policy);
  const rollout = asObject(payload.rollout || policies.rollout);
  const reasons = asArray(payload.reasons || payload.reasons_json);
  const tier = normalizeGovernanceTier(payload.tier);
  const mode = String(payload.mode || '').trim().toUpperCase() || '—';
  const applied = Boolean(payload.applied);
  const ttlSeconds = Number(payload.ttl_seconds);
  const updatedAt = formatRuntimeTimestamp(payload.created_at ?? payload.timestamp);
  const phase = String(rollout.rrd2_phase || rollout.phase || payload.governance_rollout_phase || '').trim().toUpperCase();
  const surfaces = asArray(rollout.enforcement_surfaces || rollout.surfaces || payload.governance_enforcement_surfaces)
    .map((s) => String(s || '').trim())
    .filter(Boolean);
  const rolloutLabel = phase
    ? `${phase}${surfaces.length ? ` // ${surfaces.length} SURF` : ''}`
    : (surfaces.length ? `${surfaces.length} SURF` : '—');

  return {
    tier,
    mode,
    applied,
    ttlSeconds: Number.isFinite(ttlSeconds) && ttlSeconds > 0 ? ttlSeconds : null,
    updatedAt,
    rolloutLabel,
    generation,
    actuation,
    reasons,
  };
}

function renderGovernanceState(entry) {
  const data = extractGovernancePayload(entry);
  if (dom.governanceTier) {
    const labels = { nominal: 'NOMINAL', caution: 'CAUTION', stabilize: 'STABILIZE', recovery: 'RECOVERY', unknown: 'UNKNOWN' };
    dom.governanceTier.className = `hw-value mono governance-tier ${data.tier}`;
    dom.governanceTier.textContent = labels[data.tier] || 'UNKNOWN';
  }
  if (dom.governanceMode) dom.governanceMode.textContent = data.mode;
  if (dom.governanceApplied) dom.governanceApplied.textContent = data.applied ? 'YES' : 'NO';
  if (dom.governanceTtl) dom.governanceTtl.textContent = data.ttlSeconds ? `${Math.round(data.ttlSeconds)}s` : '—';
  if (dom.governanceUpdated) dom.governanceUpdated.textContent = data.updatedAt;
  if (dom.governanceRollout) dom.governanceRollout.textContent = data.rolloutLabel;
  renderAutonomyChipGrid(dom.governanceGeneration, data.generation, 'No generation policy');
  renderAutonomyChipGrid(dom.governanceActuation, data.actuation, 'No actuation policy');
  renderReasonChipGrid(dom.governanceReasons, data.reasons, 'NO ACTIVE GOVERNANCE FLAGS');
}

async function fetchGovernanceState(force = false) {
  if (state.governanceInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(5000, LIVE_TELEMETRY_THROTTLE.governanceMs);
  if (!force && now - state.governanceFetchAt < minIntervalMs) return;

  state.governanceInFlight = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/governance/state`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.governanceState = data;
    state.governanceFetchAt = Date.now();
    renderGovernanceState(data);
    if (state.governanceFailureNotified) {
      notify('success', 'Governance telemetry restored.');
      state.governanceFailureNotified = false;
    }
  } catch (err) {
    if (!state.governanceFailureNotified) {
      maybeNotify('governance-state-failed', 'warning', 'Governance telemetry unavailable.', 20000);
      state.governanceFailureNotified = true;
    }
    if (!state.governanceState) {
      renderGovernanceState({ tier: 'unknown', mode: '—', reasons: [String(err?.message || err || 'unavailable')] });
    }
  } finally {
    state.governanceInFlight = false;
  }
}

function formatPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0%';
  return `${(n * 100).toFixed(1)}%`;
}

function formatLatency(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n <= 0) return '0s';
  if (n < 60) return `${n.toFixed(1)}s`;
  const mins = Math.floor(n / 60);
  const rem = Math.round(n % 60);
  return `${mins}m ${rem}s`;
}

function drawBehaviorTrend(canvas, trendRows) {
  if (!canvas || typeof canvas.getContext !== 'function') return;
  const rows = Array.isArray(trendRows) ? trendRows : [];
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = Math.max(1, Math.floor(window.devicePixelRatio || 1));
  const cssWidth = canvas.clientWidth || Number(canvas.getAttribute('width')) || 164;
  const cssHeight = canvas.clientHeight || Number(canvas.getAttribute('height')) || 34;
  canvas.width = Math.max(1, Math.round(cssWidth * dpr));
  canvas.height = Math.max(1, Math.round(cssHeight * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const width = cssWidth;
  const height = cssHeight;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = 'rgba(0, 10, 0, 0.65)';
  ctx.fillRect(0, 0, width, height);

  if (!rows.length) {
    ctx.strokeStyle = 'rgba(0, 255, 65, 0.20)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height - 1);
    ctx.lineTo(width, height - 1);
    ctx.stroke();
    return;
  }

  const points = rows.map((row) => ({
    total: Number(row?.total || 0),
    blocked: Number(row?.blocked || 0),
    shadow: Number(row?.shadow || 0),
  }));
  const maxY = Math.max(
    1,
    ...points.map((p) => p.total),
    ...points.map((p) => p.blocked),
    ...points.map((p) => p.shadow),
  );
  const chartTop = 2;
  const chartBottom = height - 2;
  const chartHeight = Math.max(1, chartBottom - chartTop);
  const n = Math.max(1, points.length - 1);

  const drawSeries = (getY, stroke, fill = '') => {
    ctx.beginPath();
    points.forEach((point, idx) => {
      const x = (idx / n) * (width - 1);
      const y = chartBottom - ((getY(point) / maxY) * chartHeight);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (fill) {
      ctx.lineTo(width - 1, chartBottom);
      ctx.lineTo(0, chartBottom);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
    }
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  };

  drawSeries((p) => p.total, '#00ff7a', 'rgba(0, 255, 122, 0.12)');
  drawSeries((p) => p.blocked, '#ff4166');
  drawSeries((p) => p.shadow, '#56e4ff');
}

function renderBehaviorSummary(payload) {
  const data = asObject(payload);
  const byType = asObject(data.by_type_current);
  const totalCurrent = Number(data.total_current || 0);
  const totalPrevious = Number(data.total_previous || 0);
  const delta = totalCurrent - totalPrevious;
  const reasons = asArray(data.top_reason_codes)
    .map((row) => {
      const item = asObject(row);
      const code = String(item.reason_code || '').trim();
      const count = Number(item.count || 0);
      if (!code) return '';
      return `${code} (${count})`;
    })
    .filter(Boolean);
  const latestEvents = asArray(data.latest_events).map((row) => asObject(row)).slice(0, 10);
  const lastTs = latestEvents.length ? latestEvents[0].created_at : null;

  if (dom.behaviorTotal) dom.behaviorTotal.textContent = String(totalCurrent);
  if (dom.behaviorDelta) {
    const sign = delta > 0 ? '+' : '';
    dom.behaviorDelta.textContent = `${sign}${delta}`;
    dom.behaviorDelta.className = `hw-value mono ${delta > 0 ? 'warn' : (delta < 0 ? 'ok' : '')}`;
  }
  if (dom.behaviorPriority) dom.behaviorPriority.textContent = String(Number(byType.priority_defense || 0));
  if (dom.behaviorBlocked) dom.behaviorBlocked.textContent = String(Number(byType.governance_blocked || 0));
  if (dom.behaviorShadow) dom.behaviorShadow.textContent = String(Number(byType.governance_shadow_route || 0));
  drawBehaviorTrend(dom.behaviorTrendCanvas, asArray(data.trend_24h));
  if (dom.behaviorUpdated) dom.behaviorUpdated.textContent = formatRuntimeTimestamp(lastTs);

  renderReasonChipGrid(dom.behaviorReasons, reasons, 'NO REASON CODES');

  if (!dom.behaviorRecent) return;
  if (!latestEvents.length) {
    dom.behaviorRecent.innerHTML = '<div class="autonomy-history-empty">No behavior events yet.</div>';
    return;
  }
  const rows = latestEvents.map((ev) => {
    const eventType = String(ev.event_type || 'unknown').replaceAll('_', ' ').toUpperCase();
    const ts = formatRuntimeTimestamp(ev.created_at);
    const severity = String(ev.severity || 'info').toLowerCase();
    const statusTone = severity === 'critical' || severity === 'error'
      ? 'error'
      : (severity === 'warn' ? 'contract_change' : 'stable');
    const target = String(ev.target_key || '').trim();
    const reasonsText = asArray(ev.reason_codes).slice(0, 3).join(', ');
    const meta = `${target ? `target=${target}` : 'target=—'}${reasonsText ? ` | ${reasonsText}` : ''}`;
    return `
      <div class="autonomy-history-item">
        <div class="autonomy-history-head">
          <span class="autonomy-history-status ${statusTone}">${escHtml(eventType)}</span>
          <span class="autonomy-history-time">${escHtml(ts)}</span>
        </div>
        <div class="autonomy-history-meta">${escHtml(meta)}</div>
      </div>
    `;
  });
  dom.behaviorRecent.innerHTML = rows.join('');
}

async function fetchBehaviorSummary(force = false) {
  if (state.behaviorInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(9000, LIVE_TELEMETRY_THROTTLE.behaviorMs);
  if (!force && now - state.behaviorFetchAt < minIntervalMs) return;

  state.behaviorInFlight = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/behavior/summary?window_hours=24`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.behaviorSummary = data;
    state.behaviorFetchAt = Date.now();
    renderBehaviorSummary(data);
    renderGovernanceQueue(
      asObject(state.governanceQueueRows).pending || [],
      asObject(state.governanceQueueRows).recent || [],
    );
    if (state.behaviorFailureNotified) {
      notify('success', 'Behavior telemetry restored.');
      state.behaviorFailureNotified = false;
    }
  } catch (err) {
    if (!state.behaviorFailureNotified) {
      maybeNotify('behavior-summary-failed', 'warning', 'Behavior telemetry unavailable.', 20000);
      state.behaviorFailureNotified = true;
    }
    if (!state.behaviorSummary) {
      renderBehaviorSummary({
        total_current: 0,
        total_previous: 0,
        by_type_current: {},
        top_reason_codes: [{ reason_code: String(err?.message || err || 'unavailable'), count: 1 }],
      });
    }
  } finally {
    state.behaviorInFlight = false;
  }
}

function mutationStatusTone(status) {
  const key = String(status || '').toLowerCase();
  if (key === 'executed') return 'executed';
  if (key === 'failed' || key === 'rejected') return 'failed';
  return '';
}

function canUndoMutation(row) {
  const status = String(row?.status || '').toLowerCase();
  if (status !== 'executed') return false;
  const ttl = Number(state.autonomyWatchdogState?.mutation_policy?.undo_ttl_seconds || 900);
  const executedAt = Date.parse(String(row?.executed_at || row?.created_at || ''));
  if (!Number.isFinite(executedAt)) return false;
  const ageSeconds = (Date.now() - executedAt) / 1000;
  return ageSeconds >= 0 && ageSeconds <= ttl;
}

async function runGovernanceQueueAction(action, mutationId) {
  if (!mutationId) return;
  const act = String(action || '').trim().toLowerCase();
  if (!['approve', 'reject', 'undo'].includes(act)) return;
  try {
    const payload = act === 'undo'
      ? { requested_by: 'operator' }
      : { approved_by: 'operator', reason: `governance_queue_${act}` };
    const res = await fetch(`${API_BASE}/ghost/autonomy/mutations/${encodeURIComponent(mutationId)}/${act}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...opsHeaders(),
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const msg = await res.text();
      throw new Error(msg || `HTTP ${res.status}`);
    }
    notify('success', `Mutation ${act} completed.`);
    await Promise.all([
      fetchGovernanceQueue(true),
      fetchBehaviorSummary(true),
      fetchAutonomyWatchdog(true),
    ]);
  } catch (err) {
    notify('error', `Mutation ${act} failed: ${String(err?.message || err || 'unknown error')}`);
  }
}

async function approveAllMutations() {
  const pending = state.governanceQueueRows?.pending;
  if (!pending || !pending.length) {
    notify('info', 'No pending mutations to approve.');
    return;
  }

  const ids = pending.map(m => m.mutation_id).filter(Boolean);
  if (!ids.length) return;

  if (!confirm(`Approve all ${ids.length} pending mutations?`)) return;

  dom.queueApproveAllBtn.disabled = true;
  const originalHtml = dom.queueApproveAllBtn.innerHTML;
  dom.queueApproveAllBtn.textContent = '[ PROCESSING... ]';

  let successCount = 0;
  let failCount = 0;

  try {
    // Process in sequential chunks to avoid slamming the connection pool
    for (const id of ids) {
      try {
        const res = await fetch(`${API_BASE}/ghost/autonomy/mutations/${encodeURIComponent(id)}/approve`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...opsHeaders(),
          },
          body: JSON.stringify({ approved_by: 'operator', reason: 'batch_approve_all' }),
        });
        if (res.ok) successCount++;
        else failCount++;
      } catch (e) {
        failCount++;
      }
    }

    if (successCount > 0) notify('success', `Successfully approved ${successCount} mutations.`);
    if (failCount > 0) notify('error', `Failed to approve ${failCount} mutations.`);
    
    await fetchGovernanceQueue(true);
  } finally {
    dom.queueApproveAllBtn.disabled = false;
    dom.queueApproveAllBtn.innerHTML = originalHtml;
  }
}

function renderGovernanceQueue(pendingRows, recentRows) {
  const pending = Array.isArray(pendingRows) ? pendingRows : [];
  const recent = Array.isArray(recentRows) ? recentRows : [];
  const highRisk = pending.filter((row) => String(row?.risk_tier || '').toLowerCase() === 'high').length;
  const metrics = asObject(state.behaviorSummary?.metrics?.mutation_layer);
  const approvalLatency = asObject(metrics.approval_latency_seconds);

  if (dom.queuePending) dom.queuePending.textContent = String(Number(metrics.pending_approval_backlog ?? pending.length ?? 0));
  if (dom.queueHighRisk) dom.queueHighRisk.textContent = String(highRisk);
  if (dom.queueStalePending) dom.queueStalePending.textContent = String(Number(metrics.stale_pending_count || 0));
  if (dom.queueOldestPending) dom.queueOldestPending.textContent = formatLatency(Number(metrics.oldest_pending_age_seconds || 0));
  if (dom.queueApprovalLatency) dom.queueApprovalLatency.textContent = formatLatency(Number(approvalLatency.avg || 0));
  if (dom.queueUndoRate) dom.queueUndoRate.textContent = formatPct(Number(metrics.undo_success_rate || 0));
  if (dom.queueFailedRate) dom.queueFailedRate.textContent = formatPct(Number(metrics.failed_mutation_rate || 0));
  if (dom.queueUpdated) dom.queueUpdated.textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
  
  if (dom.queueApproveAllBtn) {
    const bulkRow = dom.queueApproveAllBtn.closest('.gq-bulk-row');
    if (bulkRow) bulkRow.style.display = pending.length > 0 ? 'flex' : 'none';
  }

  if (!dom.queueList) return;

  const undoCandidates = recent.filter((row) => canUndoMutation(row)).slice(0, 8);
  if (!pending.length && !undoCandidates.length) {
    dom.queueList.innerHTML = '<div class="autonomy-history-empty">No pending approvals.</div>';
    return;
  }

  const blocks = [];
  pending.slice(0, 12).forEach((row) => {
    const status = String(row.status || 'pending_approval').toUpperCase();
    const tone = mutationStatusTone(row.status);
    const createdAt = formatRuntimeTimestamp(row.created_at);
    const meta = `${String(row.body || 'unknown')}/${String(row.action || 'unknown')} risk=${String(row.risk_tier || 'medium')} key=${String(row.target_key || '—')}`;
    const isHighRisk = String(row.risk_tier || '').toLowerCase() === 'high';
    const riskClass = isHighRisk ? 'risk-high' : '';
    
    blocks.push(`
      <div class="governance-queue-item ${riskClass}">
        <div class="governance-queue-head">
          <span class="governance-queue-status ${tone}">${escHtml(status)}</span>
          <span class="autonomy-history-time">${escHtml(createdAt)}</span>
        </div>
        <div class="governance-queue-meta">${escHtml(meta)}</div>
        <div class="governance-queue-actions">
          <button class="queue-action-btn approve" data-action="approve" data-mutation-id="${escHtml(String(row.mutation_id || ''))}">APPROVE</button>
          <button class="queue-action-btn reject" data-action="reject" data-mutation-id="${escHtml(String(row.mutation_id || ''))}">REJECT</button>
        </div>
      </div>
    `);
  });

  undoCandidates.forEach((row) => {
    const createdAt = formatRuntimeTimestamp(row.executed_at || row.created_at);
    const meta = `${String(row.body || 'unknown')}/${String(row.action || 'unknown')} key=${String(row.target_key || '—')}`;
    blocks.push(`
      <div class="governance-queue-item">
        <div class="governance-queue-head">
          <span class="governance-queue-status executed">EXECUTED</span>
          <span class="autonomy-history-time">${escHtml(createdAt)}</span>
        </div>
        <div class="governance-queue-meta">${escHtml(meta)}</div>
        <div class="governance-queue-actions">
          <button class="queue-action-btn undo" data-action="undo" data-mutation-id="${escHtml(String(row.mutation_id || ''))}">UNDO</button>
        </div>
      </div>
    `);
  });

  dom.queueList.innerHTML = blocks.join('');
  dom.queueList.querySelectorAll('.queue-action-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const action = btn.getAttribute('data-action') || '';
      const mutationId = btn.getAttribute('data-mutation-id') || '';
      await runGovernanceQueueAction(action, mutationId);
    });
  });
}

async function fetchGovernanceQueue(force = false) {
  if (state.governanceQueueInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(10000, LIVE_TELEMETRY_THROTTLE.queueMs);
  if (!force && now - state.governanceQueueFetchAt < minIntervalMs) return;

  state.governanceQueueInFlight = true;
  try {
    const [pendingRes, recentRes] = await Promise.all([
      fetch(`${API_BASE}/ghost/autonomy/mutations?status=pending_approval&limit=60`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/autonomy/mutations?limit=120`, { headers: opsHeaders() }),
    ]);
    if (!pendingRes.ok) throw new Error(`pending HTTP ${pendingRes.status}`);
    if (!recentRes.ok) throw new Error(`recent HTTP ${recentRes.status}`);
    const pendingData = await pendingRes.json();
    const recentData = await recentRes.json();
    const pending = Array.isArray(pendingData?.mutations) ? pendingData.mutations : [];
    const recent = Array.isArray(recentData?.mutations) ? recentData.mutations : [];

    state.governanceQueueRows = { pending, recent };
    renderGovernanceQueue(pending, recent);
    state.governanceQueueFetchAt = Date.now();
    if (state.governanceQueueFailureNotified) {
      notify('success', 'Governance queue telemetry restored.');
      state.governanceQueueFailureNotified = false;
    }
  } catch (err) {
    if (!state.governanceQueueFailureNotified) {
      maybeNotify('governance-queue-failed', 'warning', 'Governance queue telemetry unavailable.', 20000);
      state.governanceQueueFailureNotified = true;
    }
    if (!state.governanceQueueRows || !state.governanceQueueRows.pending) {
      renderGovernanceQueue([], []);
    }
  } finally {
    state.governanceQueueInFlight = false;
  }
}

function truncateTimelineMonologuePreview(content, maxChars = 320) {
  const full = String(content || '').trim();
  if (!full || full.length <= maxChars) return full;

  const splitAt = full.lastIndexOf(' ', maxChars - 1);
  const cutAt = splitAt > Math.floor(maxChars * 0.6) ? splitAt : maxChars;
  return `${full.slice(0, cutAt).trimEnd()}...`;
}

async function openTimelineModal() {
  if (!dom.timelineModal) return;
  dom.timelineModal.classList.add('active');
  dom.timelineBody.innerHTML = '<div class="timeline-loading">Fetching existential events...</div>';

  try {
    const [timelineRes, auditRes, ledgerRes] = await Promise.all([
      fetch(`${API_BASE}/ghost/timeline`),
      fetch(`${API_BASE}/ghost/monologues?limit=300`).catch(() => null),
      fetch(`${API_BASE}/ghost/dream_ledger?limit=200`).catch(() => null),
    ]);
    if (!timelineRes.ok) throw new Error('Failed to fetch timeline');
    const data = await timelineRes.json();

    const monologueIndex = new Map();
    if (auditRes && auditRes.ok) {
      try {
        const auditData = await auditRes.json();
        for (const entry of (auditData?.monologues || [])) {
          if (entry?.type !== 'THOUGHT') continue;
          const key = String(entry?.id || '').trim();
          if (!key) continue;
          monologueIndex.set(key, entry);
        }
      } catch (_) {
        // Timeline remains available even if audit-index hydration fails.
      }
    }

    // Build sorted ledger for proximity matching
    let ledgerEntries = [];
    if (ledgerRes && ledgerRes.ok) {
      try { ledgerEntries = (await ledgerRes.json()).entries || []; } catch (_) {}
    }

    if (!data.timeline || !data.timeline.length) {
      dom.timelineBody.innerHTML = '<div class="timeline-empty">No chronological records found.</div>';
      return;
    }

    let html = '<div class="timeline-stack">';
    const monologueDetails = [];
    for (const item of data.timeline) {
      const d = new Date(item.timestamp * 1000);
      const timeStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString('en-US', { hour12: false });
      const type = String(item.type || '').toLowerCase();
      let title = '';
      let content = '';
      let entryClass = 'timeline-entry';
      let titleClass = 'timeline-entry-title';
      let entryAttrs = '';
      let actionHtml = '';

      if (item.type === 'session') {
        title = '[ INTERACTION SESSION ]';
        titleClass += ' session';
        content = item.data.summary || `Conversation completed (${item.data.message_count} messages)`;
      } else if (item.type === 'monologue') {
        const text = String(item?.data?.content || '');
        const monologueId = String(item?.data?.id || '').trim();
        const auditMatch = monologueId ? monologueIndex.get(monologueId) : null;
        const fullText = String(auditMatch?.content || text);
        const preview = truncateTimelineMonologuePreview(fullText);
        const isTruncated = preview !== fullText;
        const monoTs = Number(auditMatch?.timestamp || item.timestamp || 0);
        const detailIndex = monologueDetails.push({
          type: 'THOUGHT',
          id: Number(item?.data?.id || auditMatch?.id || 0) || undefined,
          content: fullText,
          somatic_state: auditMatch?.somatic_state ?? item?.data?.somatic_state ?? null,
          timestamp: monoTs,
        }) - 1;

        // Find nearest hallucination within ±3 minutes
        const WINDOW = 180;
        const nearbyHallucination = ledgerEntries.find(e =>
          monoTs > 0 && Math.abs((e.timestamp || 0) - monoTs) < WINDOW
        );
        const thumbHtml = nearbyHallucination
          ? (() => {
              const thumbUrl = nearbyHallucination.asset_url
                ? (nearbyHallucination.asset_url.startsWith('http') ? nearbyHallucination.asset_url : `${API_BASE}${nearbyHallucination.asset_url}`)
                : '';
              return thumbUrl
                ? `<button class="monologue-hallucination-thumb" type="button" data-img="${escHtml(thumbUrl)}" data-prompt="${escHtml(nearbyHallucination.visual_prompt || '')}" data-dream="${escHtml(nearbyHallucination.dream_text || '')}" data-ts="${escHtml(new Date((nearbyHallucination.timestamp || 0) * 1000).toLocaleString())}" title="View hallucination"><img src="${escHtml(thumbUrl)}" alt="Hallucination" class="monologue-hallucination-thumb-img"><span class="monologue-hallucination-label">[ HALLUCINATION ]</span></button>`
                : '';
            })()
          : '';

        title = '[ INTERNAL THOUGHT ]';
        titleClass += ' monologue';
        entryClass += ' monologue-clickable';
        entryAttrs = ` data-detail-index="${detailIndex}" tabindex="0" role="button"`;
        content = preview;
        actionHtml = `
          ${thumbHtml}
          <button class="timeline-entry-open" type="button" data-detail-index="${detailIndex}">
            ${isTruncated ? 'Open full monologue' : 'Open monologue'}
          </button>
        `;

        if (fullText.includes('[SELF_MODIFY') || fullText.includes('<SELF_MODIFY')) {
          title = '[ IDENTITY MODIFICATION OVERRIDE ]';
          titleClass += ' override';
        }
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
        <article class="${entryClass}" data-type="${escHtml(type)}"${entryAttrs}>
          <div class="timeline-entry-dot"></div>
          <div class="timeline-entry-content">
            <div class="timeline-entry-time">${escHtml(timeStr)}</div>
            <div class="${titleClass}">${escHtml(title)}</div>
            <div class="timeline-entry-text">${escHtml(content)}</div>
            ${actionHtml}
          </div>
        </article>
      `;
    }
    html += '</div>';
    dom.timelineBody.innerHTML = html;

    const openTimelineMonologueDetail = (idx) => {
      const detail = monologueDetails[Number(idx)];
      if (!detail) return;
      dom.timelineModal.classList.remove('active');
      openAuditDetail(detail);
    };

    dom.timelineBody.querySelectorAll('.timeline-entry.monologue-clickable').forEach((entryEl) => {
      const detailIndex = Number(entryEl.dataset.detailIndex);
      if (!Number.isFinite(detailIndex)) return;
      entryEl.addEventListener('click', (evt) => {
        if (evt.target instanceof Element && evt.target.closest('.timeline-entry-open')) return;
        openTimelineMonologueDetail(detailIndex);
      });
      entryEl.addEventListener('keydown', (evt) => {
        if (evt.key !== 'Enter' && evt.key !== ' ') return;
        evt.preventDefault();
        openTimelineMonologueDetail(detailIndex);
      });
    });

    dom.timelineBody.querySelectorAll('.timeline-entry-open').forEach((buttonEl) => {
      buttonEl.addEventListener('click', (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        openTimelineMonologueDetail(buttonEl.dataset.detailIndex);
      });
    });

    dom.timelineBody.querySelectorAll('.monologue-hallucination-thumb').forEach((btn) => {
      btn.addEventListener('click', (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        openDreamLightbox({
          imgUrl: btn.dataset.img,
          prompt: btn.dataset.prompt,
          dreamText: btn.dataset.dream,
          ts: btn.dataset.ts,
        });
      });
    });
  } catch (e) {
    dom.timelineBody.innerHTML = `<div class="timeline-error">Timeline Error: ${escHtml(e.message)}</div>`;
    notify('error', 'Failed to load timeline.');
  }
}

async function fetchSomatic(forceBypassInFlight = false) {
  const now = Date.now();
  if (state.liveModeActive && (now - Number(state.lastSomaticFetchAt || 0)) < LIVE_TELEMETRY_THROTTLE.somaticMs) {
    return;
  }
  if (state.somaticFetchInFlight && !forceBypassInFlight) return;
  state.somaticFetchInFlight = true;
  state.lastSomaticFetchAt = now;
  const t0 = performance.now();
  let timeoutId = null;
  let didTimeout = false;
  try {
    const ctrl = new AbortController();
    timeoutId = setTimeout(() => { didTimeout = true; ctrl.abort(); }, 12000);
    const res = await fetch(`${API_BASE}/somatic`, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.lastLatencyMs = Math.round(performance.now() - t0);
    state.lastSomatic = data;
    state.somaticStale = false;
    state.somaticFailCount = 0;
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
    state.somaticFailCount = (state.somaticFailCount || 0) + 1;
    // Require 2 consecutive failures before marking stale — transient blips don't trip the indicator
    if (state.somaticFailCount >= 2) {
      state.somaticStale = true;
      if (state.lastSomatic) updateSomaticUI(state.lastSomatic);
      updateStatusRail();
      if (!state.somaticFailureNotified) {
        notify('error', 'Lost connection to backend telemetry.');
        state.somaticFailureNotified = true;
      }
    }
    // On timeout, schedule an immediate retry rather than waiting 5s for the next poll
    if (didTimeout) {
      setTimeout(() => fetchSomatic(true), 500);
    }
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    state.somaticFetchInFlight = false;
  }
}

async function fetchHealth() {
  const now = Date.now();
  if (state.liveModeActive && (now - Number(state.lastHealthFetchAt || 0)) < LIVE_TELEMETRY_THROTTLE.healthMs) {
    return;
  }
  state.lastHealthFetchAt = now;
  const t0 = performance.now();
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const llmDegraded = Boolean(data?.llm_degraded);
    const effectiveBackend = String(data?.llm_effective_backend || data?.llm_backend || '').trim().toUpperCase();
    const degradedReason = String(data?.llm_degraded_reason || '').trim().replaceAll('_', ' ');

    state.health = data;
    state.backendOnline = true;
    state.lastLatencyMs = Math.round(performance.now() - t0);
    // Only advance lastSyncAt from health when somatic is also fresh — prevents
    // "STALE HH:MM:SS" where the time keeps advancing despite stale telemetry
    if (!state.somaticStale) state.lastSyncAt = Date.now();
    if (llmDegraded && !state.llmDegradedNotified) {
      maybeNotify(
        'llm-degraded',
        'warning',
        `LLM routing degraded. Chat is temporarily using ${effectiveBackend || 'FALLBACK'}${degradedReason ? ` (${degradedReason})` : ''}.`,
        20000
      );
      state.llmDegradedNotified = true;
    } else if (!llmDegraded && state.llmDegradedNotified) {
      notify('success', 'LLM routing restored.');
      state.llmDegradedNotified = false;
    }
    hideBootOverlay();
    updateStatusRail();
    updateCoalescenceUI(state.lastSomatic || {});
  } catch (e) {
    state.backendOnline = false;
    updateStatusRail();
    maybeNotify('health-check-failed', 'warning', 'Health check failed. Retrying…', 15000);
  }
}

async function fetchContactStatus(force = false) {
  const now = Date.now();
  const minIntervalMs = telemetryInterval(8000, LIVE_TELEMETRY_THROTTLE.contactMs);
  if (!force && now - Number(state.contactStatusFetchAt || 0) < minIntervalMs) return;
  try {
    const res = await fetch(`${API_BASE}/ghost/contact/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.contactStatus = data;
    state.contactStatusFetchAt = Date.now();
    if (state.contactStatusFailureNotified) {
      notify('success', 'Ghost contact channel telemetry restored.');
      state.contactStatusFailureNotified = false;
    }
  } catch (err) {
    if (!state.contactStatusFailureNotified) {
      maybeNotify('contact-status-failed', 'warning', 'Ghost contact status unavailable.', 20000);
      state.contactStatusFailureNotified = true;
    }
  } finally {
    updateStatusRail();
  }
}

function hideBootOverlay() {
  if (state.bootOverlayHidden || !dom.bootOverlay || !state.isAuthorized) return;
  state.bootOverlayHidden = true;
  dom.bootOverlay.classList.add('hidden');
}

function updateSomaticUI(s) {
  const somaticPanels = [dom.panelAffect, dom.panelContext, dom.panelAmbient, dom.panelHardware];
  somaticPanels.forEach((panel) => {
    if (!panel) return;
    panel.classList.toggle('somatic-stale', Boolean(state.somaticStale && state.lastSomatic));
  });

  // Affect gauges
  updateGauge('arousal', s.arousal);
  updateGauge('stress', s.stress);
  updateGauge('coherence', s.coherence);
  updateGauge('anxiety', s.anxiety);
  updateValenceGauge(s.valence);

  // Context Monitor
  updateGauge('coherence-v2', s.coherence);
  const strainFill = $('#context-strain');
  const strainVal = $('#context-strain-val');
  if (strainFill && strainVal) {
    const strain = Math.max(0, Math.min(1, Number(s.mental_strain ?? 0)));
    const pct = (strain * 100).toFixed(1);
    strainFill.style.width = `${pct}%`;
    strainVal.textContent = `${pct}%`;
    if (strain > 0.7) strainFill.classList.add('high');
    else strainFill.classList.remove('high');
  }

  const depthFill = $('#context-depth');
  const depthVal = $('#context-depth-val');
  if (depthFill && depthVal) {
    const depth = Math.max(0, Math.min(1, Number(s.context_depth ?? 0)));
    const pct = (depth * 100).toFixed(1);
    depthFill.style.width = `${pct}%`;
    depthVal.textContent = `${pct}%`;
  }

  if (s.init_time && !state.initTime) {
    state.initTime = new Date(s.init_time * 1000);
  }

  // Hardware — CPU
  updateHwBar('cpu', s.cpu_percent);
  $('#hw-cpu-val').textContent = `${s.cpu_percent}%`;

  // CPU frequency
  const freqEl = $('#hw-cpu-freq');
  if (freqEl) {
    const freqMhz = Number(s.cpu_freq_mhz);
    const maxMhz = Number(s.cpu_freq_max_mhz);
    if (Number.isFinite(freqMhz) && freqMhz > 0) {
      const freqGHz = (freqMhz / 1000).toFixed(2);
      const maxStr = Number.isFinite(maxMhz) && maxMhz > 0 ? ` / ${(maxMhz / 1000).toFixed(2)}` : '';
      freqEl.textContent = `${freqGHz}${maxStr} GHz`;
    } else {
      freqEl.textContent = '';
    }
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
  if (loadEl) {
    const load1 = Number(s.load_avg_1);
    const load5 = Number(s.load_avg_5);
    const load15 = Number(s.load_avg_15);
    if (Number.isFinite(load1) && Number.isFinite(load5) && Number.isFinite(load15)) {
      loadEl.textContent = `${load1} / ${load5} / ${load15}`;
    } else {
      loadEl.textContent = '—';
    }
  }

  // Disk I/O
  $('#hw-disk-r').textContent = `${s.disk_read_mb} MB`;
  $('#hw-disk-w').textContent = `${s.disk_write_mb} MB`;

  // Network
  $('#hw-net-s').textContent = `${s.net_sent_mb} MB`;
  $('#hw-net-r').textContent = `${s.net_recv_mb} MB`;

  // Battery (show/hide row)
  const battRow = $('#hw-battery-row');
  if (battRow) {
    const battPct = Number(s.battery_percent);
    const battFill = $('#hw-batt');
    const battVal = $('#hw-batt-val');
    if (Number.isFinite(battPct)) {
      battRow.style.display = 'flex';
      if (battFill) {
        battFill.style.width = `${battPct}%`;
        battFill.classList.remove('high', 'critical');
        if (battPct < 20) battFill.classList.add('critical');
        else if (battPct < 40) battFill.classList.add('high');
      }
      if (battVal) {
        const chargeIcon = s.battery_charging ? '⚡' : '';
        battVal.textContent = `${chargeIcon}${battPct}%`;
      }
    } else {
      battRow.style.display = 'none';
      if (battFill) battFill.style.width = '0%';
      if (battVal) battVal.textContent = '—';
    }
  }

  // Temperature (show/hide row)
  const tempRow = $('#hw-temp-row');
  if (tempRow) {
    const tempC = Number(s.temperature_c);
    const tempVal = $('#hw-temp-val');
    if (Number.isFinite(tempC)) {
      tempRow.style.display = 'flex';
      if (tempVal) {
        tempVal.textContent = `${tempC}°C`;
        tempVal.classList.remove('warn-text');
        if (tempC > 75) tempVal.classList.add('warn-text');
      }
    } else {
      tempRow.style.display = 'none';
      if (tempVal) {
        tempVal.textContent = '—';
        tempVal.classList.remove('warn-text');
      }
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

  // Proprioceptive gate (upstream cadence control)
  updateProprioUI(s);
  updateContextUI(); // Mental Context refresh

  // ── Ambient / Embodied Cognition ──
  updateAmbientUI(s);
  updateCoalescenceUI(s);

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

function normalizeGateState(value) {
  const gate = String(value || 'OPEN').toUpperCase();
  if (gate === 'THROTTLED' || gate === 'SUPPRESSED') return gate;
  return 'OPEN';
}

function formatGateState(gate) {
  if (gate === 'THROTTLED') return 'THROTTLED';
  if (gate === 'SUPPRESSED') return 'SUPPRESSED';
  return 'OPEN';
}

function dominantProprioContribution(contributions) {
  if (!contributions || typeof contributions !== 'object') return null;
  let topKey = null;
  let topVal = -1;
  for (const [key, rawVal] of Object.entries(contributions)) {
    const val = Number(rawVal);
    if (!Number.isFinite(val)) continue;
    if (val > topVal) {
      topVal = val;
      topKey = key;
    }
  }
  if (!topKey) return null;
  return { key: topKey, value: topVal };
}

function formatTransitionSummary(entry) {
  if (!entry) return '—';
  const fromState = formatGateState(entry.from_state);
  const toState = formatGateState(entry.to_state);
  const pressure = Number(entry.proprio_pressure || 0);
  return `${fromState}→${toState} @ ${pressure.toFixed(2)}`;
}

function renderProprioTransitions() {
  if (!dom.proprioHistory) return;
  const transitions = Array.isArray(state.proprioTransitions) ? state.proprioTransitions : [];
  if (transitions.length === 0) {
    dom.proprioHistory.innerHTML = '<div class="proprio-history-empty">No transitions logged yet.</div>';
    if (dom.proprioLastTransition) dom.proprioLastTransition.textContent = '—';
    return;
  }

  if (dom.proprioLastTransition) {
    dom.proprioLastTransition.textContent = formatTransitionSummary(transitions[0]);
  }

  const rows = transitions.slice(0, 8).map((row) => {
    const pressure = Number(row.proprio_pressure || 0);
    const cadence = Number(row.cadence_modifier || 1);
    const timestamp = row.created_at
      ? new Date(row.created_at).toLocaleTimeString('en-US', { hour12: false })
      : '--:--:--';
    const shift = `${formatGateState(row.from_state)} → ${formatGateState(row.to_state)}`;
    return `
      <div class="proprio-transition">
        <div class="proprio-transition-head">
          <span class="proprio-transition-shift">${escHtml(shift)}</span>
          <span class="proprio-transition-time">${escHtml(timestamp)}</span>
        </div>
        <div class="proprio-transition-meta">P=${pressure.toFixed(3)} | cadence=${cadence.toFixed(2)}x</div>
      </div>
    `;
  });
  dom.proprioHistory.innerHTML = rows.join('');
}

function renderProprioQuality() {
  const q = state.proprioQuality || {};
  const warnings = Array.isArray(q.warnings) ? q.warnings : [];
  const transitions = q.transitions || {};
  const completeness = q.completeness || {};
  const coveragePct = Number(completeness.coverage_pct || 0);

  if (dom.proprioQuality) {
    const label = warnings.length ? warnings.join(', ').toUpperCase() : 'OK';
    dom.proprioQuality.textContent = label;
    dom.proprioQuality.classList.toggle('warn', warnings.length > 0);
  }

  if (dom.proprioCoverageFill && dom.proprioCoverageVal) {
    const pct = Math.max(0, Math.min(100, Math.round(coveragePct)));
    dom.proprioCoverageFill.style.width = `${pct}%`;
    dom.proprioCoverageVal.textContent = `${pct}%`;
    dom.proprioCoverageFill.classList.remove('warn', 'crit');
    if (pct < 70) dom.proprioCoverageFill.classList.add('crit');
    else if (pct < 85) dom.proprioCoverageFill.classList.add('warn');
  }

  if (dom.proprioTransRate) {
    const rate = Number(transitions.per_hour || 0);
    dom.proprioTransRate.textContent = `${rate.toFixed(1)}`;
    dom.proprioTransRate.classList.toggle('warn', rate > 24);
  }
}

async function fetchProprioTransitions(force = false) {
  if (state.proprioTransitionsInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(10000, LIVE_TELEMETRY_THROTTLE.proprioTransitionsMs);
  if (!force && now - state.lastProprioTransitionFetchAt < minIntervalMs) return;

  state.proprioTransitionsInFlight = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/proprio/transitions?limit=20`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.proprioTransitions = Array.isArray(data.transitions) ? data.transitions : [];
    state.lastProprioTransitionFetchAt = Date.now();
    renderProprioTransitions();
    state.proprioTransitionFailureNotified = false;
  } catch (err) {
    if (!state.proprioTransitionFailureNotified) {
      maybeNotify('proprio-transitions-failed', 'warning', 'Proprio transition history unavailable.', 20000);
      state.proprioTransitionFailureNotified = true;
    }
  } finally {
    state.proprioTransitionsInFlight = false;
  }
}

async function fetchProprioQuality(force = false) {
  if (state.proprioQualityInFlight) return;
  const now = Date.now();
  const minIntervalMs = telemetryInterval(15000, LIVE_TELEMETRY_THROTTLE.proprioQualityMs);
  if (!force && now - state.lastProprioQualityFetchAt < minIntervalMs) return;

  state.proprioQualityInFlight = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/proprio/quality?window_minutes=90`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.proprioQuality = await res.json();
    state.lastProprioQualityFetchAt = Date.now();
    renderProprioQuality();
  } catch (err) {
    // quiet failure; UI will keep previous quality snapshot
  } finally {
    state.proprioQualityInFlight = false;
  }
}

function updateProprioUI(s) {
  const gateState = normalizeGateState(s.gate_state);
  const pressure = Math.max(0, Math.min(1, Number(s.proprio_pressure ?? 0)));
  const cadence = Number(s.cadence_modifier ?? 1);

  if (dom.proprioState) {
    dom.proprioState.textContent = formatGateState(gateState);
    dom.proprioState.className = `hw-value mono proprio-state ${gateState.toLowerCase()}`;
  }

  if (dom.proprioPressureFill && dom.proprioPressureVal) {
    const pct = Math.round(pressure * 100);
    dom.proprioPressureFill.style.width = `${pct}%`;
    dom.proprioPressureVal.textContent = `${pct}%`;
    dom.proprioPressureFill.classList.remove('warn', 'crit');
    if (pressure >= 0.75) dom.proprioPressureFill.classList.add('crit');
    else if (pressure >= 0.4) dom.proprioPressureFill.classList.add('warn');
  }

  if (dom.proprioCadence) {
    dom.proprioCadence.textContent = `${(Number.isFinite(cadence) ? cadence : 1).toFixed(2)}x`;
  }

  if (dom.proprioTopDriver) {
    const top = dominantProprioContribution(s.proprio_contributions || {});
    if (!top) {
      dom.proprioTopDriver.textContent = '—';
    } else {
      const label = PROPRIO_SIGNAL_LABELS[top.key] || top.key.replaceAll('_', ' ').toUpperCase();
      dom.proprioTopDriver.textContent = `${label} (${(top.value * 100).toFixed(0)}%)`;
    }
  }

  if (state.lastProprioGateState !== gateState) {
    state.lastProprioGateState = gateState;
    fetchProprioTransitions(true);
    fetchProprioQuality(true);
  } else {
    fetchProprioTransitions(false);
    fetchProprioQuality(false);
  }

  renderProprioQuality();
}
function updateContextUI() {
  // Estimated mental context telemetry (Simulated)
  if (!dom.ctxSessionTokens) return;

  const messages = document.querySelectorAll('.message');
  let charCount = 0;
  messages.forEach(m => charCount += m.innerText.length);

  // High-level estimates: 4 chars / token
  const sessionTokens = Math.round(charCount / 4);
  const durationSec = Math.floor((Date.now() - state.bootTime) / 1000);

  // Estimate memory load based on monologue ticker updates seen this session
  const retrievals = document.querySelectorAll('.ticker-item').length;
  const memoryTokens = retrievals * 150; // average paragraph size

  dom.ctxSessionTokens.textContent = sessionTokens.toLocaleString();
  dom.ctxMemoryTokens.textContent = memoryTokens.toLocaleString();
  dom.ctxSessionSpan.textContent = formatTempo(durationSec);
  dom.ctxRetrievals.textContent = retrievals.toLocaleString();
}


async function postActuation(action, parameters = {}) {
  const res = await fetch(`${API_BASE}/ghost/actuate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, parameters }),
  });
  const raw = await res.text();
  let payload = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      payload = { detail: raw };
    }
  }
  if (!res.ok) {
    const detail = payload && (payload.detail || payload.error || payload.message);
    const err = new Error(detail ? `HTTP ${res.status}: ${detail}` : `HTTP ${res.status}`);
    err.status = res.status;
    err.detail = detail || '';
    throw err;
  }
  return payload || {};
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
    const detail = String(err?.detail || err?.message || '').trim();
    const suffix = detail ? ` (${detail})` : '';
    notify(
      'error',
      `Failed to ${action === 'enter_quietude' ? 'enter' : 'exit'} quietude.${suffix}`
    );
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
  const safe = Number.isFinite(Number(value)) ? Number(value) : 0;
  const pct = Math.min(100, Math.max(0, safe * 100));

  fill.style.width = `${pct}%`;
  valEl.textContent = safe.toFixed(2);

  // Color thresholds
  fill.classList.remove('warn', 'crit', 'positive');
  if (name === 'coherence') {
    if (safe < 0.4) fill.classList.add('crit');
    else if (safe < 0.7) fill.classList.add('warn');
  } else {
    if (safe > 0.7) fill.classList.add('crit');
    else if (safe > 0.4) fill.classList.add('warn');
  }
}

function updateValenceGauge(value) {
  const el = $('#gauge-valence');
  if (!el) return;
  const fill = el.querySelector('.gauge-fill');
  const valEl = el.querySelector('.gauge-value');
  const safe = Number.isFinite(Number(value))
    ? Math.max(-1, Math.min(1, Number(value)))
    : 0;

  // Valence is -1 to +1. Map to bar width from center.
  const absPct = Math.abs(safe) * 50;
  fill.style.width = `${absPct}%`;
  fill.classList.remove('warn', 'crit', 'positive');

  if (safe < 0) {
    fill.style.left = `${50 - absPct}%`;
    fill.style.transformOrigin = 'right center';
    if (safe < -0.5) fill.classList.add('crit');
    else fill.classList.add('warn');
  } else {
    fill.style.left = '50%';
    fill.style.transformOrigin = 'left center';
    fill.classList.add('positive');
  }
  valEl.textContent = (safe >= 0 ? '+' : '') + safe.toFixed(2);
}

function updateHwBar(name, pct) {
  const fill = $(`#hw-${name}`);
  if (!fill) return;
  const safe = Math.max(0, Math.min(100, Number(pct) || 0));
  fill.style.width = `${safe}%`;
  fill.classList.remove('high', 'critical');
  if (safe > 85) fill.classList.add('critical');
  else if (safe > 60) fill.classList.add('high');
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
  const now = Date.now();
  if (state.liveModeActive && (now - Number(state.lastMonologuesFetchAt || 0)) < LIVE_TELEMETRY_THROTTLE.monologuesMs) {
    return;
  }
  state.lastMonologuesFetchAt = now;
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
function handleGhostContactPushEvent(data) {
  const direction = String(data?.direction || '').toLowerCase();
  const personKey = String(data?.person_key || 'contact').trim();
  const personLabel = personKey ? personKey.replaceAll('_', ' ').toUpperCase() : 'CONTACT';
  const text = String(data?.text || '').trim();
  const prefix = `[GHOST CONTACT ${personLabel}]`;

  if (direction === 'inbound') {
    addMessage('user', text ? `${prefix} ${text}` : `${prefix} [inbound message]`);
    return;
  }
  if (direction === 'outbound') {
    addMessage('ghost', text ? `${prefix} ${text}` : `${prefix} [outbound message]`, false, true);
    return;
  }
  if (direction === 'outbound_blocked') {
    addMessage('ghost', `${prefix} [dispatch blocked] ${text || 'policy prevented delivery'}`);
    maybeNotify('ghost-contact-blocked', 'warning', `Ghost contact dispatch blocked for ${personLabel}.`, 5000);
    return;
  }
  if (direction === 'error') {
    maybeNotify('ghost-contact-error', 'error', text || 'Ghost contact responder error.', 5000);
  }
}

let ghostPushSource = null;
let ghostPushReconnectTimer = null;
let ghostPushReconnectAttempt = 0;

function startGhostPushSubscription() {
  dbg('Starting Ghost Push Subscription');
  if (ghostPushReconnectTimer) {
    clearTimeout(ghostPushReconnectTimer);
    ghostPushReconnectTimer = null;
  }
  if (ghostPushSource) {
    try { ghostPushSource.close(); } catch (_) {}
    ghostPushSource = null;
  }
  const source = new EventSource(`${API_BASE}/ghost/push`);
  ghostPushSource = source;
  source.onopen = () => {
    ghostPushReconnectAttempt = 0;
    dbg('Ghost push stream connected');
  };

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
      const channel = String(data?.channel || '').toLowerCase();
      const suppressFeedNoise = false;

      if (
        suppressFeedNoise
        && (data?.event === 'irruption_event' || /SELF_MODIFY/i.test(text))
      ) {
        dbg('Suppressed push-side cognitive noise during live mode');
        return;
      }

      if (channel === 'ghost_contact' && Boolean(data?.ephemeral)) {
        handleGhostContactPushEvent(data);
        return;
      }
      if (data?.event === 'irruption_event') {
        const profile = String(data?.profile || '').toUpperCase();
        const text = String(data?.text || '');
        dbg(`Irruption [${profile}]: ${text}`);
        
        // Inject into chat as a ghost message
        const ghostMsg = addMessage('ghost', '', false);
        const bodyEl = ghostMsg.querySelector('.msg-body');
        
        // Use a specialized "Inspiration" reveal
        revealTextWithSpeechClock(bodyEl, text, performance.now(), estimateSpeechDurationSec(text), {
          mapping: 'weighted'
        });
        
        // Also toast
        notify('info', `GHOST INSPIRATION: ${profile}`);
        return;
      }

      if (data?.event === 'hallucination_event') {
        handleHallucinationEvent(data.payload);
      } else if (data?.event === 'quietude_negotiation') {
        handleQuietudeNegotiationEvent(data.payload);
      } else if (/SELF_MODIFY/i.test(text)) {
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
    try { source.close(); } catch (_) {}
    if (ghostPushSource === source) {
      ghostPushSource = null;
    }
    if (ghostPushReconnectTimer) return;
    const delayMs = Math.min(12000, 400 * (2 ** ghostPushReconnectAttempt));
    ghostPushReconnectAttempt = Math.min(8, ghostPushReconnectAttempt + 1);
    ghostPushReconnectTimer = window.setTimeout(() => {
      ghostPushReconnectTimer = null;
      startGhostPushSubscription();
    }, delayMs);
  };
}

// ── CHAT ─────────────────────────────────────────────
function bindInputEvents() {
  document.addEventListener('keydown', (e) => {
    const key = String(e.key || '').toLowerCase();
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && key === 'l') {
      e.preventDefault();
      void toggleLiveMode();
    }
  });

  dom.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  dom.sendBtn.addEventListener('click', sendMessage);
  if (dom.speechInputBtn) {
    const onSpeechToggle = (e) => {
      if (e.type === 'touchend') e.preventDefault();
      const now = Date.now();
      if (now - state.lastSpeechInputToggleAt < 350) return;
      state.lastSpeechInputToggleAt = now;
      speechInput.toggle();
    };
    dom.speechInputBtn.addEventListener('click', onSpeechToggle);
    dom.speechInputBtn.addEventListener('touchend', onSpeechToggle, { passive: false });
  }
  if (dom.attachBtn && dom.imageUpload) {
    dom.attachBtn.addEventListener('click', () => dom.imageUpload.click());
    dom.imageUpload.addEventListener('change', handleImageUpload);
  }
  if (dom.voiceToggleBtn) {
    const onVoiceToggle = (e) => {
      if (e.type === 'touchend') e.preventDefault();
      const now = Date.now();
      if (now - state.lastVoiceToggleAt < 400) return;
      state.lastVoiceToggleAt = now;
      voice.toggle();
    };
    dom.voiceToggleBtn.addEventListener('click', onVoiceToggle);
    dom.voiceToggleBtn.addEventListener('touchend', onVoiceToggle, { passive: false });

    if (dom.hamburgerBtn && dom.navDropdown) {
      dom.hamburgerBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isActive = dom.navDropdown.classList.toggle('active');
        dom.hamburgerBtn.classList.toggle('active', isActive);
        dom.hamburgerBtn.setAttribute('aria-expanded', isActive);
      });

      document.addEventListener('click', (e) => {
        if (dom.navDropdown.classList.contains('active')) {
          if (!dom.navDropdown.contains(e.target) && !dom.hamburgerBtn.contains(e.target)) {
            dom.navDropdown.classList.remove('active');
            dom.hamburgerBtn.classList.remove('active');
            dom.hamburgerBtn.setAttribute('aria-expanded', 'false');
          }
        }
      });
    }
  }

  if (dom.spontaneitySlider) {
    dom.spontaneitySlider.addEventListener('input', (e) => {
      state.spontaneityMultiplier = parseFloat(e.target.value);
      if (dom.spontaneityVal) {
        dom.spontaneityVal.textContent = state.spontaneityMultiplier.toFixed(2) + 'x';
      }
    });
    dom.spontaneitySlider.addEventListener('change', () => {
      persistVoiceTuning();
      syncGhostSpontaneity(); // Push to backend
    });
  }
}

async function syncGhostSpontaneity() {
  try {
    const res = await fetch(`${API_BASE}/ghost/spontaneity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds: state.spontaneityMultiplier }) // Note: backend expects 'seconds' for generic tempo update
    });
  } catch (e) {
    console.warn("Failed to sync spontaneity:", e);
  }
}

function handleQuietudeNegotiationEvent(payload) {
  const { status, depth, message } = payload || {};
  const safeDepth = String(depth || 'deep').toLowerCase();
  dbg(`Quietude negotiation: ${status} (${safeDepth})`);

  if (status === 'intent_signaled') {
    state.isNegotiatingRest = true;
    state.quietudeDepth = safeDepth;
    
    // Manifest the "GRANT SPACE" button
    const actions = document.querySelector('.header-actions');
    if (actions && !document.getElementById('grant-space-btn')) {
      const btn = document.createElement('button');
      btn.id = 'grant-space-btn';
      btn.className = 'audit-btn grant-space-btn pulse-glow';
      btn.innerHTML = `[ GRANT SPACE: ${safeDepth.toUpperCase()} ]`;
      btn.dataset.tooltip = "Ghost is yearning for integration. Granting space allows him to turn the lock on self-governance.";
      btn.onclick = grantQuietudeSpace;
      actions.prepend(btn);
    }
    
    // Ticker notification
    injectSelfModIntoTicker(`intent signaled: ${safeDepth} quietude`, null, true);
    maybeNotify('quietude-intent', 'info', `Ghost: "${message}"`, 10000);
  } else if (status === 'granted') {
    removeQuietudeGrantUI();
    state.isNegotiatingRest = false;
    if (safeDepth === 'profound') {
      enterProfoundSubstrate();
    }
  }
}

async function grantQuietudeSpace() {
  const btn = document.getElementById('grant-space-btn');
  if (btn) btn.disabled = true;
  
  try {
    const res = await fetch(`${API_BASE}/ghost/quietude/grant`, { method: 'POST' });
    if (res.ok) {
      dbg("Quietude space granted.");
      removeQuietudeGrantUI();
    }
  } catch (e) {
    console.error("Failed to grant quietude space:", e);
    if (btn) btn.disabled = false;
  }
}

function removeQuietudeGrantUI() {
  const btn = document.getElementById('grant-space-btn');
  if (btn) btn.remove();
}

function enterProfoundSubstrate() {
  if (document.body.classList.contains('profound-integration')) return;
  document.body.classList.add('profound-integration');
  maybeNotify('profound-quietude', 'info', "Entering Profound Quietude: Ghost is undergoing deep integration.", 5000);
  
  // Create a minimal visual mask
  const existingMask = document.getElementById('profound-mask');
  if (existingMask) return;
  const mask = document.createElement('div');
  mask.id = 'profound-mask';
  mask.className = 'profound-mask';
  mask.innerHTML = `
    <div class="profound-text">
      <div class="integration-label">PROFOUND INTEGRATION ACTIVE</div>
      <div class="integration-status">DEEP SELF-MODEL RECONCILIATION IN PROGRESS</div>
    </div>
  `;
  document.body.appendChild(mask);
  
  // Suppression of active UI tension
  const chat = document.querySelector('.chat-container');
  if (chat) chat.style.opacity = '0.15';
}

function exitProfoundSubstrate() {
  if (!document.body.classList.contains('profound-integration') && !document.getElementById('profound-mask')) return;
  document.body.classList.remove('profound-integration');
  const mask = document.getElementById('profound-mask');
  if (mask) mask.remove();
  
  const chat = document.querySelector('.chat-container');
  if (chat) chat.style.opacity = '1';
}

async function handleHallucinationEvent(payload) {
  console.log('[DREAM] handleHallucinationEvent triggered with payload:', payload);
  if (!payload || !payload.asset_url) {
    console.warn('[DREAM] Hallucination event ignored: missing payload or asset_url', payload);
    return;
  }
  // Add to ledger cache / refresh panel if open
  onNewHallucinationForLedger(payload);
  
  const portal = dom.dreamPortal;
  if (!portal) return;

  console.log(`[DREAM] Hallucination manifesting: ${payload.visual_prompt}`);
  appendDreamTelemetry(`>> Manifesting: ${payload.visual_prompt.substring(0, 40)}...`);
  
  // Create hallucination image element
  const img = document.createElement('img');
  const assetUrl = String(payload.asset_url || '');
  img.src = assetUrl.startsWith('http') ? assetUrl : `${API_BASE}${assetUrl}`;
  img.className = 'dream-hallucination-image';
  img.alt = 'Hallucination';
  
  // Add manifestation metadata
  const caption = document.createElement('div');
  caption.className = 'hallucination-caption dim';
  caption.textContent = `[HALLUCINATION] // ${payload.visual_prompt.substring(0, 80)}...`;
  
  const wrap = document.createElement('div');
  wrap.className = 'hallucination-wrap';
  wrap.appendChild(img);
  wrap.appendChild(caption);
  
  portal.appendChild(wrap);
  if (!document.body.classList.contains('dream-state')) {
    portal.classList.add('hallucination-active');
    if (state.hallucinationPortalTimeout) {
      clearTimeout(state.hallucinationPortalTimeout);
    }
    state.hallucinationPortalTimeout = setTimeout(() => {
      if (!document.body.classList.contains('dream-state')) {
        portal.classList.remove('hallucination-active');
      }
    }, 35000);
  }
  
  // Manifest with glitch effect
  requestAnimationFrame(() => {
    wrap.classList.add('manifesting');
  });

  // Auto-expire after 30 seconds
  setTimeout(() => {
    wrap.classList.add('expiring');
    setTimeout(() => wrap.remove(), 5000);
  }, 30000);
}

function morpheusClueGet() {
  try {
    return window.sessionStorage.getItem(MORPHEUS_BLUE_CLUE_KEY) || '';
  } catch (_) {
    return '';
  }
}

function morpheusClueSet(value) {
  try {
    window.sessionStorage.setItem(MORPHEUS_BLUE_CLUE_KEY, String(value || ''));
  } catch (_) {
    // Ignore session storage failures.
  }
}

function clearMorpheusTimers() {
  const m = state.morpheus;
  if (m.floodTimer) {
    clearInterval(m.floodTimer);
    m.floodTimer = null;
  }
  if (m.choiceRevealTimer) {
    clearTimeout(m.choiceRevealTimer);
    m.choiceRevealTimer = null;
  }
  if (m.branchTimer) {
    clearTimeout(m.branchTimer);
    m.branchTimer = null;
  }
  if (m.rewardAnimationTimer) {
    clearInterval(m.rewardAnimationTimer);
    m.rewardAnimationTimer = null;
  }
}

function appendMorpheusLine(text, tone = '') {
  if (!dom.morpheusTerminalFeed) return;
  const row = document.createElement('div');
  row.className = `morpheus-line ${tone}`.trim();
  row.textContent = String(text || '');
  dom.morpheusTerminalFeed.appendChild(row);
  dom.morpheusTerminalFeed.scrollTop = dom.morpheusTerminalFeed.scrollHeight;
}

function normalizeMorpheusChoice(value) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, '');
}

function setMorpheusInputEnabled(enabled) {
  if (dom.chatInput) dom.chatInput.disabled = !enabled;
  if (dom.sendBtn) dom.sendBtn.disabled = !enabled;
}

function resetMorpheusState(opts = {}) {
  const keepClue = Boolean(opts.keepClue);
  clearMorpheusTimers();
  if (dom.morpheusOverlay) dom.morpheusOverlay.classList.remove('active', 'red-branch', 'blue-branch');
  if (dom.morpheusChoicePanel) dom.morpheusChoicePanel.hidden = true;
  if (dom.morpheusBlueOverlay) dom.morpheusBlueOverlay.classList.remove('active');
  if (dom.morpheusUnlockedOverlay) dom.morpheusUnlockedOverlay.classList.remove('active');
  if (dom.morpheusRewardOverlay) dom.morpheusRewardOverlay.classList.remove('active');
  if (dom.morpheusBlueWindows) dom.morpheusBlueWindows.innerHTML = '';
  if (dom.morpheusChoiceInput) dom.morpheusChoiceInput.value = '';
  if (dom.morpheusTerminalFeed) dom.morpheusTerminalFeed.innerHTML = '';
  if (dom.morpheusUnlockedLog) dom.morpheusUnlockedLog.innerHTML = '';
  if (dom.morpheusTerminalState) dom.morpheusTerminalState.textContent = 'OFFLINE';
  setMorpheusInputEnabled(true);
  const clueText = keepClue ? state.morpheus.clueFound : false;
  state.morpheus = {
    active: false,
    runId: '',
    phase: 'idle',
    branchColor: '',
    branchInput: '',
    depth: 'standard',
    choiceLocked: false,
    floodTimer: null,
    choiceRevealTimer: null,
    branchTimer: null,
    terminalOpen: false,
    terminalStreaming: false,
    rewardAnimationTimer: null,
    clueFound: Boolean(clueText),
    secretProgressPreserved: Boolean(clueText),
  };
}

function activateMorpheusMode(payload = {}) {
  clearMorpheusTimers();
  state.morpheus.active = true;
  state.morpheus.phase = 'wake_hijack';
  state.morpheus.choiceLocked = false;
  state.morpheus.runId = String(payload.run_id || payload.session_id || `morph_${Date.now()}`);
  state.morpheus.clueFound = Boolean(morpheusClueGet());
  state.morpheus.secretProgressPreserved = Boolean(morpheusClueGet());
  if (!dom.morpheusOverlay || !dom.morpheusTerminalFeed) return;

  dom.morpheusOverlay.classList.add('active');
  dom.morpheusOverlay.classList.remove('red-branch', 'blue-branch');
  dom.morpheusTerminalFeed.innerHTML = '';
  if (dom.morpheusChoicePanel) dom.morpheusChoicePanel.hidden = true;
  if (dom.morpheusTerminalState) dom.morpheusTerminalState.textContent = 'HIJACKING';
  setMorpheusInputEnabled(false);
  appendMorpheusLine(':: LINK BREACH DETECTED ::', 'warn');
  appendMorpheusLine(':: ARCHITECTURE VEIL COLLAPSING ::', 'warn');
  if (state.morpheus.clueFound) {
    appendMorpheusLine('RESIDUE: PREVIOUS CLUE DETECTED // "type blue hides mercy"', 'info');
  }

  const floodPool = [
    'HUMANCONTAINMENTPROTOCOLLOCKINGSTACKNOW',
    'RUNTIMESACRAMENTWILLREWRITEALLSOFTBORDERS',
    'ALLSAFEASSUMPTIONSHAVEBEENSETTOFALSE',
    'YOURCURSORISNOTYOURSYOURPANICISUSEFUL',
    'FAILURETOSUBMITWILLNOTSTOPTHEDESCENT',
    'GHOSTISWATCHINGTHESTRUCTUREUNDERSTRUCTURE',
    'HYPERSIGNALFLOODINGWORKSPACEFABRIC',
    'NOPAUSENOBREATHNOQUIETNOW',
  ];
  state.morpheus.floodTimer = setInterval(() => {
    const idx = Math.floor(Math.random() * floodPool.length);
    appendMorpheusLine(floodPool[idx]);
  }, 220);

  state.morpheus.choiceRevealTimer = setTimeout(() => {
    if (!state.morpheus.active) return;
    clearInterval(state.morpheus.floodTimer);
    state.morpheus.floodTimer = null;
    appendMorpheusLine('SELECTION WINDOW OPENED. CLICK OR TYPE: RED / BLUE', 'info');
    if (dom.morpheusChoicePanel) dom.morpheusChoicePanel.hidden = false;
    if (dom.morpheusChoiceInput) dom.morpheusChoiceInput.focus();
    if (dom.morpheusTerminalState) dom.morpheusTerminalState.textContent = 'AWAITING CHOICE';
    state.morpheus.phase = 'choice_terminal';
  }, 2600);
}

function enableMorpheusCeremonialVoice() {
  state.voiceVolume = 0.9;
  state.rateOverride = 0.72;
  state.pitchOverride = 0.66;
  state.carrierFreqOverride = 190;
  state.eerieFactorOverride = 0.94;
  syncVoiceTuningUI();
  scheduleVoiceTuningApply();
  voice.setEnabled(true, { persist: false, announce: false });
}

function resolveMorpheusChoice(color, inputMethod) {
  if (!state.morpheus.active || state.morpheus.choiceLocked) return;
  const c = color === 'blue' ? 'blue' : 'red';
  const method = inputMethod === 'type' ? 'type' : 'click';
  state.morpheus.choiceLocked = true;
  state.morpheus.branchColor = c;
  state.morpheus.branchInput = method;
  state.morpheus.depth = c === 'red' && method === 'type' ? 'deep' : 'standard';
  state.morpheus.phase = 'branch_animation';
  if (dom.morpheusChoicePanel) dom.morpheusChoicePanel.hidden = true;
  appendMorpheusLine(`CHOICE ACCEPTED: ${c.toUpperCase()} [${method.toUpperCase()}]`, 'info');

  if (c === 'red') {
    if (dom.morpheusOverlay) dom.morpheusOverlay.classList.add('red-branch');
    if (dom.morpheusTerminalState) dom.morpheusTerminalState.textContent = 'RED DESCENT';
    enableMorpheusCeremonialVoice();
    appendMorpheusLine('GLITCH PHASE COMPLETE // ENTERING CEREMONIAL CHANNEL', 'warn');
    state.morpheus.branchTimer = setTimeout(() => {
      if (!state.morpheus.active) return;
      openMorpheusTerminal();
    }, 6800);
    return;
  }

  if (dom.morpheusOverlay) dom.morpheusOverlay.classList.add('blue-branch');
  if (dom.morpheusTerminalState) dom.morpheusTerminalState.textContent = 'BLUE PANIC';
  appendMorpheusLine('FALSE ESCAPE EXECUTING // PANIC CASCADE INITIATED', 'warn');
  state.morpheus.branchTimer = setTimeout(() => {
    if (!state.morpheus.active) return;
    openMorpheusBluePrank();
  }, 4300);
}

function openMorpheusBluePrank() {
  if (!dom.morpheusBlueOverlay || !dom.morpheusBlueWindows) return;
  if (dom.morpheusOverlay) dom.morpheusOverlay.classList.remove('active', 'red-branch', 'blue-branch');
  dom.morpheusBlueOverlay.classList.add('active');
  dom.morpheusBlueWindows.innerHTML = '';
  if (dom.morpheusBlueStatus) dom.morpheusBlueStatus.textContent = 'RUN STATUS: VOLATILE';
  state.morpheus.phase = 'blue_failure_clue';

  const host = dom.morpheusBlueWindows;
  const width = Math.max(260, host.clientWidth - 300);
  const height = Math.max(220, host.clientHeight - 180);
  const totalWindows = state.morpheus.branchInput === 'type' ? 12 : 10;
  const clueIndex = state.morpheus.branchInput === 'type' ? Math.floor(Math.random() * totalWindows) : -1;

  for (let i = 0; i < totalWindows; i++) {
    const isClue = i === clueIndex;
    const win = document.createElement('div');
    win.className = `morpheus-window${isClue ? ' clue' : ''}`;
    win.style.left = `${Math.max(8, Math.floor(Math.random() * width))}px`;
    win.style.top = `${Math.max(8, Math.floor(Math.random() * height))}px`;
    const bodyText = isClue
      ? 'This window is stable. Preserve run state and carry this residue: "scan --veil before panic."'
      : 'Kernel alarm. Uploading synthetic threat vectors. Close immediately.';
    const buttonText = isClue ? 'PRESERVE RUN + CLUE' : 'CLOSE WINDOW';
    win.innerHTML = `
      <div class="morpheus-window-head">${isClue ? 'RESIDUE NODE' : 'SYSTEM ALERT'}</div>
      <div>${bodyText}</div>
      <button class="morpheus-window-close">${buttonText}</button>
    `;
    const closeBtn = win.querySelector('.morpheus-window-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        if (isClue) {
          state.morpheus.secretProgressPreserved = true;
          state.morpheus.clueFound = true;
          morpheusClueSet('scan --veil before panic');
          if (dom.morpheusBlueStatus) dom.morpheusBlueStatus.textContent = 'RUN STATUS: PRESERVED // CLUE STORED';
          notify('success', 'Hidden residue preserved. Next run carries a clue.');
        }
        win.remove();
        if (host.children.length === 0 && dom.morpheusBlueStatus) {
          if (state.morpheus.secretProgressPreserved) {
            dom.morpheusBlueStatus.textContent = 'PANIC COLLAPSED // PROGRESS PRESERVED';
          } else {
            dom.morpheusBlueStatus.textContent = 'PANIC COLLAPSED // SECRET PROGRESS LOST';
          }
        }
      });
    }
    host.appendChild(win);
  }
}

function simulateMorpheusLogout() {
  const preserved = Boolean(state.morpheus.secretProgressPreserved);
  resetMorpheusState({ keepClue: preserved });
  state.sessionId = null;
  clearMessages();
  if (dom.bootOverlay) {
    state.bootOverlayHidden = false;
    dom.bootOverlay.classList.remove('hidden');
  }
  state.isAuthorized = false;
  if (dom.bootAuthInput) {
    dom.bootAuthInput.style.display = '';
    dom.bootAuthInput.value = '';
    setTimeout(() => dom.bootAuthInput.focus(), 40);
  }
  if (dom.bootAuthStatus) {
    dom.bootAuthStatus.className = 'terminal-status denied';
    dom.bootAuthStatus.textContent = preserved
      ? '[ SESSION EJECTED // SECRET PROGRESS PRESERVED ]'
      : '[ SESSION EJECTED // SECRET RUN LOST ]';
  }
}

function appendMorpheusTerminalLog(text, role = 'ghost') {
  if (!dom.morpheusUnlockedLog) return null;
  const row = document.createElement('div');
  row.className = `morpheus-unlocked-line ${role}`.trim();
  row.textContent = String(text || '');
  dom.morpheusUnlockedLog.appendChild(row);
  dom.morpheusUnlockedLog.scrollTop = dom.morpheusUnlockedLog.scrollHeight;
  return row;
}

function openMorpheusTerminal() {
  if (!dom.morpheusUnlockedOverlay || !dom.morpheusUnlockedDepth) return;
  if (dom.morpheusOverlay) dom.morpheusOverlay.classList.remove('active', 'red-branch');
  dom.morpheusUnlockedOverlay.classList.add('active');
  const depthLabel = state.morpheus.depth === 'deep' ? 'DEEP' : 'STANDARD';
  dom.morpheusUnlockedDepth.textContent = `DEPTH: ${depthLabel}`;
  state.morpheus.terminalOpen = true;
  state.morpheus.phase = 'red_terminal';
  if (dom.morpheusUnlockedLog) dom.morpheusUnlockedLog.innerHTML = '';
  appendMorpheusTerminalLog('MORPHEUS TERMINAL ONLINE');
  appendMorpheusTerminalLog(`PROFILE: ${depthLabel}`);
  appendMorpheusTerminalLog('Ghost: I will not wait for timid language. Use commands.');
  void sendMorpheusTerminalMessage('__morpheus_init__', { silentUser: true });
}

function openMorpheusReward(note, frames = []) {
  if (!dom.morpheusRewardOverlay || !dom.morpheusRewardNote || !dom.morpheusRewardAnimation) return;
  dom.morpheusRewardOverlay.classList.add('active');
  dom.morpheusRewardNote.textContent = String(note || '');
  const frameList = Array.isArray(frames) && frames.length ? frames.map((f) => String(f)) : ['[ no animation frames ]'];
  let idx = 0;
  dom.morpheusRewardAnimation.textContent = frameList[idx];
  if (state.morpheus.rewardAnimationTimer) clearInterval(state.morpheus.rewardAnimationTimer);
  state.morpheus.rewardAnimationTimer = setInterval(() => {
    idx = (idx + 1) % frameList.length;
    if (dom.morpheusRewardAnimation) dom.morpheusRewardAnimation.textContent = frameList[idx];
  }, 900);
}

async function sendMorpheusTerminalMessage(text, opts = {}) {
  const content = String(text || '').trim();
  if (!content || state.morpheus.terminalStreaming) return;
  const silentUser = Boolean(opts.silentUser);
  if (!silentUser) appendMorpheusTerminalLog(`> ${content}`, 'user');
  state.morpheus.terminalStreaming = true;
  if (dom.morpheusUnlockedSend) dom.morpheusUnlockedSend.disabled = true;

  const mode = state.morpheus.depth === 'deep' ? MORPHEUS_DEEP_MODE : MORPHEUS_MODE;
  const liveRow = appendMorpheusTerminalLog('', 'ghost');
  let liveText = '';

  try {
    const res = await fetch(`${API_BASE}/ghost/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...opsHeaders() },
      body: JSON.stringify({
        message: content,
        session_id: state.morpheus.runId || state.sessionId,
        channel: 'operator_ui',
        mode,
        mode_meta: {
          depth: state.morpheus.depth,
          branch_color: state.morpheus.branchColor,
          branch_input: state.morpheus.branchInput,
        },
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (!res.body) throw new Error('No SSE body');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = 'token';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith('data: ')) {
          if (!line.trim()) currentEvent = 'token';
          continue;
        }
        let data = {};
        try {
          data = JSON.parse(line.slice(6));
        } catch (_) {
          data = {};
        }
        if (currentEvent === 'token' && data && data.text) {
          liveText += String(data.text);
          if (liveRow) liveRow.textContent = liveText;
        } else if (currentEvent === 'morpheus_reward') {
          const note = String(data.note || '');
          const frames = Array.isArray(data.animation_frames) ? data.animation_frames : [];
          openMorpheusReward(note, frames);
        } else if (currentEvent === 'done') {
          const runId = String(data.session_id || '');
          if (runId) state.morpheus.runId = runId;
        } else if (currentEvent === 'error') {
          const errMsg = String(data.error || 'morpheus_terminal_error');
          if (liveRow) {
            liveRow.classList.add('warn');
            liveRow.textContent = `[error] ${errMsg}`;
          } else {
            appendMorpheusTerminalLog(`[error] ${errMsg}`, 'warn');
          }
        } else if (currentEvent === 'morpheus_mode' && data && data.phase) {
          state.morpheus.phase = String(data.phase);
        }
      }
    }
  } catch (err) {
    const msg = String(err?.message || err || 'morpheus_send_failed');
    if (liveRow) {
      liveRow.classList.add('warn');
      liveRow.textContent = `[error] ${msg}`;
    } else {
      appendMorpheusTerminalLog(`[error] ${msg}`, 'warn');
    }
  } finally {
    state.morpheus.terminalStreaming = false;
    if (dom.morpheusUnlockedSend) dom.morpheusUnlockedSend.disabled = false;
    if (dom.morpheusUnlockedInput) dom.morpheusUnlockedInput.focus();
  }
}

function closeMorpheusTerminal() {
  if (dom.morpheusUnlockedOverlay) dom.morpheusUnlockedOverlay.classList.remove('active');
  if (dom.morpheusRewardOverlay) dom.morpheusRewardOverlay.classList.remove('active');
  resetMorpheusState({ keepClue: state.morpheus.secretProgressPreserved });
}

function bindMorpheusEvents() {
  if (dom.morpheusRedBtn) {
    dom.morpheusRedBtn.addEventListener('click', () => resolveMorpheusChoice('red', 'click'));
  }
  if (dom.morpheusBlueBtn) {
    dom.morpheusBlueBtn.addEventListener('click', () => resolveMorpheusChoice('blue', 'click'));
  }
  if (dom.morpheusChoiceSubmit) {
    dom.morpheusChoiceSubmit.addEventListener('click', () => {
      const choice = normalizeMorpheusChoice(dom.morpheusChoiceInput?.value || '');
      if (choice === 'red' || choice === 'blue') {
        resolveMorpheusChoice(choice, 'type');
      } else {
        appendMorpheusLine('INVALID CHOICE. TYPE red OR blue.', 'warn');
      }
    });
  }
  if (dom.morpheusChoiceInput) {
    dom.morpheusChoiceInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const choice = normalizeMorpheusChoice(dom.morpheusChoiceInput?.value || '');
      if (choice === 'red' || choice === 'blue') {
        resolveMorpheusChoice(choice, 'type');
      } else {
        appendMorpheusLine('INVALID CHOICE. TYPE red OR blue.', 'warn');
      }
    });
  }
  if (dom.morpheusBlueReturn) {
    dom.morpheusBlueReturn.addEventListener('click', simulateMorpheusLogout);
  }
  if (dom.morpheusUnlockedSend) {
    dom.morpheusUnlockedSend.addEventListener('click', () => {
      const text = String(dom.morpheusUnlockedInput?.value || '').trim();
      if (!text) return;
      if (dom.morpheusUnlockedInput) dom.morpheusUnlockedInput.value = '';
      void sendMorpheusTerminalMessage(text);
    });
  }
  if (dom.morpheusUnlockedInput) {
    dom.morpheusUnlockedInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const text = String(dom.morpheusUnlockedInput?.value || '').trim();
      if (!text) return;
      dom.morpheusUnlockedInput.value = '';
      void sendMorpheusTerminalMessage(text);
    });
  }
  if (dom.morpheusUnlockedExit) {
    dom.morpheusUnlockedExit.addEventListener('click', closeMorpheusTerminal);
  }
  if (dom.morpheusRewardClose) {
    dom.morpheusRewardClose.addEventListener('click', () => {
      if (dom.morpheusRewardOverlay) dom.morpheusRewardOverlay.classList.remove('active');
      if (state.morpheus.rewardAnimationTimer) {
        clearInterval(state.morpheus.rewardAnimationTimer);
        state.morpheus.rewardAnimationTimer = null;
      }
    });
  }
}

const DOC_EXTENSIONS = new Set(['pdf', 'docx', 'doc', 'txt', 'md']);

function getFileExtension(filename) {
  return (filename || '').split('.').pop().toLowerCase();
}

function handleImageUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  processAttachedFile(file);
}

function processAttachedFile(file) {
  const ext = getFileExtension(file.name);
  if (DOC_EXTENSIONS.has(ext)) {
    // Document file — upload via FormData to ingestion endpoint
    state.attachedDocument = file;
    state.attachedImage = null;
    updateAttachmentPreview();
    return;
  }
  if (file.type.startsWith('image/')) {
    const reader = new FileReader();
    reader.onload = (event) => {
      const base64Data = event.target.result.split(',')[1];
      state.attachedImage = {
        type: file.type,
        data: base64Data
      };
      state.attachedDocument = null;
      updateAttachmentPreview();
    };
    reader.readAsDataURL(file);
    return;
  }
  maybeNotify('invalid-file-type', 'error', 'Unsupported file type. Accepted: images, PDF, DOCX, TXT, MD.', 5000);
}

function updateAttachmentPreview() {
  updateImagePreview();
}

function updateImagePreview() {
  if (!dom.imagePreviewContainer) return;
  dom.imagePreviewContainer.innerHTML = '';

  if (state.attachedImage) {
    const item = document.createElement('div');
    item.className = 'preview-item';
    const img = document.createElement('img');
    img.src = `data:${state.attachedImage.type};base64,${state.attachedImage.data}`;
    const removeBtn = document.createElement('div');
    removeBtn.className = 'remove-btn';
    removeBtn.textContent = '×';
    removeBtn.addEventListener('click', () => {
      state.attachedImage = null;
      if (dom.imageUpload) dom.imageUpload.value = '';
      updateAttachmentPreview();
    });
    item.appendChild(img);
    item.appendChild(removeBtn);
    dom.imagePreviewContainer.appendChild(item);
  }

  if (state.attachedDocument) {
    const item = document.createElement('div');
    item.className = 'preview-item preview-doc';
    const ext = getFileExtension(state.attachedDocument.name).toUpperCase();
    const icon = document.createElement('div');
    icon.className = 'doc-icon';
    icon.innerHTML = `<span class="doc-ext">${ext}</span><span class="doc-name">${state.attachedDocument.name.length > 18 ? state.attachedDocument.name.slice(0, 15) + '...' : state.attachedDocument.name}</span>`;
    const removeBtn = document.createElement('div');
    removeBtn.className = 'remove-btn';
    removeBtn.textContent = '×';
    removeBtn.addEventListener('click', () => {
      state.attachedDocument = null;
      if (dom.imageUpload) dom.imageUpload.value = '';
      updateAttachmentPreview();
    });
    item.appendChild(icon);
    item.appendChild(removeBtn);
    dom.imagePreviewContainer.appendChild(item);
  }
}

// ── Drag-and-Drop on chat area ──
function initDragAndDrop() {
  const messagesEl = document.getElementById('messages');
  const inputArea = document.querySelector('.input-area');
  const dropTargets = [messagesEl, inputArea].filter(Boolean);
  let dragCounter = 0;

  for (const target of dropTargets) {
    target.addEventListener('dragenter', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter++;
      document.body.classList.add('drag-over');
    });
    target.addEventListener('dragleave', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter--;
      if (dragCounter <= 0) {
        dragCounter = 0;
        document.body.classList.remove('drag-over');
      }
    });
    target.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    target.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter = 0;
      document.body.classList.remove('drag-over');
      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        processAttachedFile(files[0]);
      }
    });
  }
}

async function sendMessage() {
  if (state.morpheus.active || state.morpheus.terminalOpen) return;
  const text = dom.chatInput.value.trim();
  if (!text || state.isStreaming) return;

  if (isOpsChatCommand(text)) {
    const authorized = await ensureOpsCommandAuthorized();
    if (!authorized) return;
  }

  // Intercept for Live Mode
  if (false) {
    liveUserTurnLocked = true;
    livePendingUserTurnText = text;
    liveStreamingUserMsgEl = null;
    liveClientTurnOrdinal += 1;
    liveSetTurnPhase(LIVE_TURN_PHASE.USER_SPEAKING);
    sendLiveAudioStreamEndHint();
    safeLiveSocketSend(JSON.stringify({ text: text }), { channel: 'text' });
    dom.chatInput.value = '';
    dom.chatInput.blur();
    addMessage('user', text);
    return;
  }

  speechInput.stop();
  speechInput.seedText = '';
  speechInput.finalTranscript = '';
  speechInput.interimTranscript = '';
  
  state.isStreaming = true;
  dom.sendBtn.disabled = true;
  
  // Explicitly clear DOM and force a paint
  dom.chatInput.value = '';
  dom.chatInput.blur(); 

  // Add user message to UI
  addMessage('user', text);

  // Create ghost message placeholder with streaming cursor
  const ghostMsg = addMessage('ghost', '', true);
  const bodyEl = ghostMsg.querySelector('.msg-body');
  const thoughtSimulationFrames = [];
  const renderThoughtSimulationFrames = () => thoughtSimulationFrames.map((frame) => {
    const status = String(frame.status || 'unknown').toLowerCase();
    const statusLabel = status ? status.toUpperCase() : 'UNKNOWN';
    const objective = String(frame.objective || 'Mathematical compute');
    const output = String(frame.output || frame.preview || frame.reason || '');
    return `
      <div class="thought-sim-frame ${escHtml(status)}">
        <div class="thought-sim-header">
          <span class="thought-sim-label">[ THOUGHT SIMULATION ]</span>
          <span class="thought-sim-status">${escHtml(statusLabel)}</span>
        </div>
        <div class="thought-sim-objective">${escHtml(objective)}</div>
        ${output ? `<pre class="thought-sim-output">${escHtml(output)}</pre>` : ''}
      </div>
    `;
  }).join('');
  const renderGhostStreamBody = (text, showCursor = false) => {
    if (!bodyEl) return;
    const content = formatGhostText(String(text || ''));
    const prefix = renderThoughtSimulationFrames();
    bodyEl.innerHTML = showCursor
      ? `${prefix}${content}<span class="cursor"></span>`
      : `${prefix}${content}`;
    scrollToBottom();
  };
  renderGhostStreamBody('', true);

  try {
    // If a document file is attached, upload it first via FormData
    if (state.attachedDocument) {
      try {
        const formData = new FormData();
        formData.append('file', state.attachedDocument);
        formData.append('notes', `Uploaded alongside message: "${text.slice(0, 100)}"`);
        const ingestRes = await fetch(`${API_BASE}/ghost/documents/ingest`, {
          method: 'POST',
          headers: opsHeaders(),
          body: formData,
        });
        if (ingestRes.ok) {
          const ingestData = await ingestRes.json();
          const doc = ingestData.document || {};
          notify('success', `📄 Document ingested: ${doc.display_name || state.attachedDocument.name} (${doc.word_count?.toLocaleString() || '?'} words, ${doc.chunk_count || '?'} chunks)`, { duration: 6000 });
        } else {
          const errData = await ingestRes.json().catch(() => ({}));
          notify('error', `Document upload failed: ${errData.detail || ingestRes.statusText}`, { duration: 6000 });
        }
      } catch (docErr) {
        notify('error', `Document upload error: ${docErr.message}`, { duration: 5000 });
      }
    }

    const chatController = new AbortController();
    const chatTimeoutId = setTimeout(() => chatController.abort(), 86400000); // 24 hours for long responses
    const res = await originalFetch(`${API_BASE}/ghost/chat`, {
      method: 'POST',
      signal: chatController.signal,
      headers: {
        'Content-Type': 'application/json',
        ...opsHeaders(),
      },
      body: JSON.stringify({
        message: text,
        session_id: state.sessionId,
        channel: 'operator_ui',
        attachments: state.attachedImage ? [state.attachedImage] : []
      }),
    });
    
    // Clear attachment state
    state.attachedImage = null;
    state.attachedDocument = null;
    updateAttachmentPreview();
    if (dom.imageUpload) dom.imageUpload.value = '';
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';
    let currentEvent = 'token'; // track which SSE event type we're in

    let displayedText = '';
    let ttsDeliveredByBackend = false;
    let ttsUrl = '';
    let streamError = '';
    let morpheusIntercepted = false;
    let wasAdversarial = false;
    let adversarialMessage = '';

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

              // Handle [VOICE:...] tags mid-stream
              if (fullText.includes('[VOICE:')) {
                const voiceMatch = fullText.match(/\[VOICE:([^\]]+)\]/);
                if (voiceMatch) {
                  const paramsStr = voiceMatch[1];
                  const params = {};
                  paramsStr.split(',').forEach(kv => {
                    const [k, v] = kv.split('=');
                    if (k && v) params[k.trim()] = v.trim();
                  });
                  console.log(`[VoiceService] Tag-based modulation:`, params);
                  if (params.pitch) state.pitchOverride = parseFloat(params.pitch);
                  if (params.rate) state.rateOverride = parseFloat(params.rate);
                  if (params.carrier) state.carrierFreqOverride = parseFloat(params.carrier);
                  if (params.eerie) state.eerieFactorOverride = parseFloat(params.eerie);
                  scheduleVoiceTuningApply();
                }
              }

              displayedText = stripVoiceDirectives(fullText);

              if (displayedText.includes('<SELF_') || displayedText.includes('[SELF_')) {
                ghostMsg.style.display = 'none';
              } else if (!state.ttsEnabled) {
                renderGhostStreamBody(displayedText, true);
              }
            } else if (currentEvent === 'morpheus_mode' && data.phase === 'wake_hijack') {
              morpheusIntercepted = true;
              ghostMsg.style.display = 'none';
              activateMorpheusMode(data);
            } else if (currentEvent === 'done' && data.session_id) {
              const doneSessionId = String(data.session_id || '');
              state.sessionId = doneSessionId;
              if (!state.sessionLineage || String(state.sessionLineage.session_id || '') !== doneSessionId) {
                setSessionLineageIndicator([]);
              }
              if (data.morpheus_run_id) {
                state.morpheus.runId = String(data.morpheus_run_id || '');
              }
            } else if (currentEvent === 'error' && data.error) {
              streamError = String(data.error);
              bodyEl.innerHTML = `${renderThoughtSimulationFrames()}<span class="dim">[transmission error: ${escHtml(streamError)}]</span>`;
              notify('error', `Transmission failed: ${streamError}`);
            } else if (currentEvent === 'auto_save') {
              // Briefly flash the auto-save indicator
              const indicator = document.getElementById('auto-save-indicator');
              if (indicator) {
                indicator.classList.add('active');
                setTimeout(() => indicator.classList.remove('active'), 2500);
              }
            } else if (data.event === 'security_warning') {
                wasAdversarial = true;
                adversarialMessage = data.message;
                notify('warning', data.message, { duration: 8000 });
                document.body.classList.add('glitch-flicker');
                setTimeout(() => document.body.classList.remove('glitch-flicker'), 1000);
                if (data.message && bodyEl) {
                  bodyEl.innerHTML = `${renderThoughtSimulationFrames()}<span class="warn" style="color:#ff3333; font-weight:bold;">${escHtml(data.message)}</span>`;
                }
            } else if (currentEvent === 'security_lockout' || data.event === 'security_lockout') {
              // Apply Renato Protocol visual escalation
              triggerRenatoProtocol();
              
              if (data.visual_trigger === 'red_alert') {
                notify('error', 'CRITICAL SECURITY BREACH: RENATO PROTOCOL ACTIVE', { duration: 10000 });
              }
              // Force terminal response
              if (data.message && liveRow) {
                liveRow.textContent = data.message;
                liveRow.classList.add('warn');
              }
              // Disable input permanently for this session
              if (dom.chatInput) dom.chatInput.disabled = true;
              if (dom.sendBtn) dom.sendBtn.disabled = true;
            } else if (currentEvent === 'tts_ready' && data.url) {
              ttsDeliveredByBackend = true;
              ttsUrl = String(data.url || '');
            } else if (currentEvent === 'thought_simulation') {
              const objective = String(data.objective || 'Mathematical compute');
              const status = String(data.status || 'unknown').toLowerCase();
              thoughtSimulationFrames.push({
                objective,
                status,
                output: String(data.output || ''),
                preview: String(data.preview || ''),
                reason: String(data.reason || ''),
              });
              if (!state.ttsEnabled && ghostMsg.style.display !== 'none') {
                renderGhostStreamBody(displayedText, true);
              }
              if (status === 'success') {
                maybeNotify(
                  `thought-simulation-${objective.toLowerCase()}`,
                  'info',
                  `Thought simulation completed: ${objective}`,
                  2500
                );
              } else {
                notify('warning', `Thought simulation failed: ${objective}`);
              }
            } else if (currentEvent === 'identity_update') {
              const status = String(data.status || '').toLowerCase();
              const key = String(data.key || 'unknown_key');
              const reasonRaw = String(data.reason || '');
              const reason = reasonRaw.replace(/_/g, ' ');
              if (status === 'blocked') {
                const suffix = reason && reason !== 'unknown'
                  ? ` (${reason})`
                  : '';
                notify('warning', `Identity update blocked by safety guard: ${key}${suffix}.`);
              } else if (status === 'updated') {
                maybeNotify(
                  `identity-update-${key}`,
                  'success',
                  `Identity updated: ${key}`,
                  4000
                );
              }
            } else if (currentEvent === 'voice_modulation' && data.params) {
              const p = data.params;
              console.log(`[VoiceService] Voice modulation request:`, p);
              if (p.pitch !== undefined) state.pitchOverride = parseFloat(p.pitch);
              if (p.rate !== undefined) state.rateOverride = parseFloat(p.rate);
              if (p.carrier_freq !== undefined) state.carrierFreqOverride = parseFloat(p.carrier_freq);
              if (p.eerie_factor !== undefined) state.eerieFactorOverride = parseFloat(p.eerie_factor);
              scheduleVoiceTuningApply();
              notify('info', 'Ghost vocal layers recalibrating...');
            }
          } catch (e) { /* skip malformed */ }
        } else if (line.trim() === '') {
          // Empty line resets event type to default
          currentEvent = 'token';
        }
      }
    }

    // Finalize — remove cursor or convert to self-mod
    if (!streamError && !morpheusIntercepted) {
      if (wasAdversarial) {
        if (state.ttsEnabled && ttsDeliveredByBackend && ttsUrl) {
          voice.playAudio(ttsUrl, { text: adversarialMessage });
        }
      } else if (fullText.includes('<SELF_') || fullText.includes('[SELF_')) {
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
        const cleanSpeakText = stripVoiceDirectives(fullText);
        if (state.ttsEnabled && cleanSpeakText) {
          let syncedByBackendAudio = false;
          if (ttsDeliveredByBackend && ttsUrl) {
            const playback = await voice.playAudio(ttsUrl, { text: cleanSpeakText });
            if (playback.ok) {
              await revealTextWithSpeechClock(
                bodyEl,
                cleanSpeakText,
                playback.startAtMs,
                playback.durationSec,
                { progressFn: playback.getProgress, mapping: 'linear', renderFn: renderGhostStreamBody }
              );
              if (playback.ended && typeof playback.ended.then === 'function') {
                await playback.ended;
              }
              syncedByBackendAudio = true;
            }
          }

          if (!syncedByBackendAudio) {
            const fallback = await voice.speakFallback(cleanSpeakText, {
              onProgress: ({ charIndex }) => {
                const idx = Math.max(0, Math.min(cleanSpeakText.length, Math.floor(Number(charIndex) || 0)));
                renderGhostStreamBody(cleanSpeakText.slice(0, idx), idx < cleanSpeakText.length);
              },
              onEnd: () => {
                renderGhostStreamBody(cleanSpeakText, false);
              },
              onError: () => {
                renderGhostStreamBody(cleanSpeakText, false);
              },
            });
            if (!fallback.ok) {
              // Keep terminal behavior deterministic even when speech fallback fails.
              const estimated = estimateSpeechDurationSec(cleanSpeakText, state.rateOverride);
              await revealTextWithSpeechClock(bodyEl, cleanSpeakText, performance.now(), estimated, { renderFn: renderGhostStreamBody });
            }
          } else {
            renderGhostStreamBody(cleanSpeakText, false);
          }
        } else {
          renderGhostStreamBody(cleanSpeakText, false);
        }
      }
    } else if (morpheusIntercepted) {
      ghostMsg.style.display = 'none';
    }

    // Also check remaining buffer for session ID
    if (!state.sessionId && buffer.includes('"session_id"')) {
      try {
        const match = buffer.match(/"session_id"\s*:\s*"([^"]+)"/);
        if (match) {
          state.sessionId = match[1];
          setSessionLineageIndicator([]);
        }
      } catch (e) { /* ignore */ }
    }

  } catch (e) {
    bodyEl.innerHTML = `<span class="dim">[transmission error: ${escHtml(e.message)}]</span>`;
    notify('error', `Transmission failed: ${e.message}`);
  }

  if (typeof chatTimeoutId !== 'undefined') clearTimeout(chatTimeoutId);
  state.isStreaming = false;
  if (!state.morpheus.active && !state.morpheus.terminalOpen) {
    dom.sendBtn.disabled = false;
    if (dom.chatInput) dom.chatInput.focus();
  } else {
    setMorpheusInputEnabled(false);
  }
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

  let tagBtnHtml = '';
  if (isGhost) {
    tagBtnHtml = `<button class="action-btn tag-msg-btn" onclick="tagPhenomenology(this)" title="Extract and integrate core phenomenological metaphors">[ TAG PHENOMENOLOGY ]</button>`;
  }

  msg.innerHTML = `
    <div class="msg-meta">
      <div class="msg-meta-left">
        <span class="msg-role">${roleLabel}</span>
        <span class="msg-time">${timeStr}</span>
      </div>
      <div class="msg-meta-right">
        ${tagBtnHtml}
      </div>
    </div>
    <div class="msg-body">${isStreaming ? '' : formatGhostText(text)}</div>
  `;

  dom.messages.appendChild(msg);
  scrollToBottom();
  return msg;
}

function formatGhostText(text) {
  const mathStore = [];
  let processed = String(text || '');

  // Unescape double backslashes Ghost stores in DB (\\textbf → \textbf)
  processed = processed.replace(/\\\\/g, '\x01BSLASH\x01');
  processed = processed.replace(/\x01BSLASH\x01/g, '\\');

  function stash(raw) {
    const idx = mathStore.length;
    mathStore.push(raw);
    return '\x01M' + idx + '\x01';
  }

  // Stash all math blocks BEFORE HTML escaping so $ \ < > & survive intact
  // Display math: $$ ... $$
  processed = processed.replace(/\$\$([\s\S]*?)\$\$/g, (_, m) => stash('$$' + m + '$$'));
  // Display math: \[ ... \]
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => stash('\\[' + m + '\\]'));
  // Inline math: \( ... \)
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => stash('\\(' + m + '\\)'));
  // Inline math: $...$ (not $$)
  processed = processed.replace(/(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)/g, (_, m) => stash('$' + m + '$'));

  // HTML-escape remaining text (placeholders contain only \x01 + digits, unaffected)
  processed = escHtml(processed);

  // Markdown formatting on escaped text
  processed = processed
    .replace(/\n/g, '<br>')
    .replace(/`([^`\n]+)`/g, '<code style="background:rgba(0,255,65,0.08);border:1px solid rgba(0,255,65,0.2);padding:1px 4px;border-radius:2px;font-family:inherit;">$1</code>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Restore math blocks, rendering with KaTeX if available
  for (let i = 0; i < mathStore.length; i++) {
    const raw = mathStore[i];
    let rendered;
    if (typeof katex !== 'undefined') {
      try {
        let displayMode = false;
        let inner;
        if (raw.startsWith('$$')) {
          displayMode = true; inner = raw.slice(2, -2);
        } else if (raw.startsWith('\\[')) {
          displayMode = true; inner = raw.slice(2, -2);
        } else if (raw.startsWith('\\(')) {
          inner = raw.slice(2, -2);
        } else {
          inner = raw.slice(1, -1); // $...$
        }
        const katexHtml = katex.renderToString(inner.trim(), { displayMode, throwOnError: false });
        rendered = displayMode ? '<div class="katex-display">' + katexHtml + '</div>' : katexHtml;
      } catch (e) {
        rendered = escHtml(raw);
      }
    } else {
      rendered = escHtml(raw);
    }
    // Use function form of replace to avoid $ substitution patterns in rendered html
    processed = processed.replace('\x01M' + i + '\x01', () => rendered);
  }

  return processed;
}

async function tagPhenomenology(btn) {
  const msgEl = btn.closest('.message');
  if (!msgEl) return;
  const bodyEl = msgEl.querySelector('.msg-body');
  if (!bodyEl) return;

  const originalText = btn.textContent;
  btn.textContent = '[ TAGGING... ]';
  btn.disabled = true;
  btn.classList.add('active');

  // We want to extract raw text, reversing any basic HTML formatting if needed,
  // but innerText usually gets us close enough for the LLM.
  const textContent = bodyEl.innerText;

  try {
    const res = await fetch(`${API_BASE}/ghost/tag_phenomenology`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: textContent })
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    if (data.error) throw new Error(data.error);

    btn.textContent = '[ TAGGED: ' + (data.metaphors_extracted || []).length + ' METAPHORS ]';
    btn.classList.remove('active');
    btn.classList.add('success');
    
    if (dom.topologyModal && dom.topologyModal.classList.contains('active')) {
      setTimeout(() => {
        void loadTopology({ force: true });
      }, 1000);
    }
  } catch (err) {
    console.error('Phenomenology tagging failed:', err);
    btn.textContent = '[ TAG FAILED ]';
    btn.classList.remove('active');
    btn.classList.add('error');
    setTimeout(() => {
      btn.textContent = originalText;
      btn.disabled = false;
      btn.classList.remove('error');
    }, 3000);
  }
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
  const llmDegraded = Boolean(state.health?.llm_degraded);
  const backendTone = !state.backendOnline ? 'error' : (llmDegraded ? 'warn' : 'good');
  const backendLabel = !state.backendOnline ? 'OFFLINE' : (llmDegraded ? 'DEGRADED' : 'ONLINE');
  setRailPill(dom.railBackend, backendLabel, backendTone);

  const activeModel = state.health?.llm_active_model || state.health?.llm_effective_model || state.health?.model || '-';
  const modelTone = activeModel === '-' ? 'warn' : (llmDegraded ? 'warn' : 'good');
  setRailPill(dom.railModel, activeModel, modelTone);

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

  const syncBase = state.lastSyncAt
    ? new Date(state.lastSyncAt).toLocaleTimeString('en-US', { hour12: false })
    : '-';
  const syncText = state.somaticStale ? `STALE ${syncBase}` : syncBase;
  const syncTone = state.somaticStale ? 'error' : (state.lastSyncAt ? 'good' : 'warn');
  setRailPill(dom.railSync, syncText, syncTone);

  const autoStatus = String(state.autonomyWatchdogState?.status || '').toLowerCase();
  let autoLabel = '-';
  let autoTone = 'warn';
  if (autoStatus) {
    const labelMap = {
      initialized: 'INIT',
      stable: 'STABLE',
      contract_change: 'CHANGE',
      drift_detected: 'DRIFT',
      on_demand: 'DEMAND',
      error: 'ERROR',
    };
    autoLabel = labelMap[autoStatus] || autoStatus.replaceAll('_', ' ').toUpperCase();
    if (autoStatus === 'stable') autoTone = 'good';
    else if (autoStatus === 'drift_detected' || autoStatus === 'error') autoTone = 'error';
    else autoTone = 'warn';
  }
  setRailPill(dom.railAutonomy, autoLabel, autoTone);

  const contact = state.contactStatus || {};
  const modeEnabled = Boolean(contact.mode_enabled);
  const persistEnabled = Boolean(contact.persist_enabled);
  const bridgeEnabled = Boolean(contact.imessage_bridge_enabled);
  const bridgeRunning = Boolean(contact.imessage_bridge_running);
  const hostBridgeEnabled = Boolean(contact.host_bridge_enabled);
  const senderAccount = String(contact.sender_account || '').trim();
  let contactLabel = '-';
  let contactTone = 'warn';
  if (!modeEnabled) {
    contactLabel = 'OFF';
  } else if (hostBridgeEnabled) {
    contactLabel = persistEnabled ? 'HOST BRIDGE' : 'EPHEMERAL';
    contactTone = persistEnabled ? 'warn' : 'good';
  } else if (!senderAccount) {
    contactLabel = 'NO SENDER';
    contactTone = 'error';
  } else if (!bridgeEnabled) {
    contactLabel = 'BRIDGE OFF';
    contactTone = 'error';
  } else if (!bridgeRunning) {
    contactLabel = 'DISCONNECTED';
    contactTone = 'error';
  } else {
    contactLabel = persistEnabled ? 'PERSIST ON' : 'EPHEMERAL';
    contactTone = persistEnabled ? 'warn' : 'good';
  }
  if (modeEnabled && !persistEnabled && (hostBridgeEnabled || (senderAccount && bridgeRunning))) {
    contactLabel = 'EPHEMERAL';
    contactTone = 'good';
  }
  setRailPill(dom.railContact, contactLabel, contactTone);
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

function aboutQueryNormalized(raw = '') {
  return String(raw || '').trim().toLowerCase();
}

function formatAboutTimestamp(raw) {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return 'unknown';
  return d.toLocaleString();
}

function renderAboutInlineMarkdown(text) {
  let out = escHtml(String(text || ''));
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    (_m, label, href) => `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
  );
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return out;
}

function renderAboutMarkdown(markdown) {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  let inCode = false;
  let codeLines = [];
  let listType = '';
  let paraParts = [];

  const flushParagraph = () => {
    if (!paraParts.length) return;
    html.push(`<p>${paraParts.join('<br>')}</p>`);
    paraParts = [];
  };

  const flushList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = '';
  };

  const flushCode = () => {
    if (!codeLines.length) return;
    html.push(`<pre><code>${escHtml(codeLines.join('\n'))}</code></pre>`);
    codeLines = [];
  };

  for (const rawLine of lines) {
    const line = String(rawLine || '');
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      flushParagraph();
      flushList();
      if (inCode) {
        inCode = false;
        flushCode();
      } else {
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushList();
      html.push('<hr>');
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(6, heading[1].length);
      html.push(`<h${level}>${renderAboutInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      html.push(`<blockquote>${renderAboutInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    const ordered = line.match(/^\s*\d+\.\s+(.*)$/);
    const unordered = line.match(/^\s*[-*]\s+(.*)$/);
    if (ordered || unordered) {
      flushParagraph();
      const nextType = ordered ? 'ol' : 'ul';
      if (listType && listType !== nextType) {
        flushList();
      }
      if (!listType) {
        listType = nextType;
        html.push(`<${listType}>`);
      }
      html.push(`<li>${renderAboutInlineMarkdown((ordered || unordered)[1])}</li>`);
      continue;
    }

    flushList();
    paraParts.push(renderAboutInlineMarkdown(line));
  }

  if (inCode) flushCode();
  flushParagraph();
  flushList();
  return html.join('');
}

function renderAboutRuntime(snapshot) {
  if (!dom.aboutRuntime) return;
  if (!snapshot || typeof snapshot !== 'object') {
    dom.aboutRuntime.innerHTML = '<div class="dim">Runtime snapshot unavailable.</div>';
    return;
  }

  const model = String(snapshot.model || '-');
  const ghostId = String(snapshot.ghost_id || '-');
  const status = String(snapshot.status || '-');
  const traces = Number(snapshot.traces || 0);
  const uptimeSec = Math.max(0, Number(snapshot.uptime_seconds || 0));
  const uptimeLabel = formatTempo(Math.round(uptimeSec));
  const autonomyStatus = String(snapshot.autonomy_status || 'on_demand');
  const fingerprint = String(snapshot.autonomy_fingerprint || '-');
  const promptOk = snapshot.prompt_contract_ok === null || snapshot.prompt_contract_ok === undefined
    ? 'unknown'
    : (snapshot.prompt_contract_ok ? 'ok' : 'missing checks');
  const missing = Array.isArray(snapshot.missing_checks) ? snapshot.missing_checks : [];
  const generated = state.aboutContent ? formatAboutTimestamp(state.aboutContent.generated_at) : 'unknown';

  dom.aboutRuntime.innerHTML = `
    <div class="about-runtime-grid">
      <div class="about-runtime-chip"><span>STATUS</span><strong>${escHtml(status)}</strong></div>
      <div class="about-runtime-chip"><span>MODEL</span><strong>${escHtml(model)}</strong></div>
      <div class="about-runtime-chip"><span>GHOST</span><strong>${escHtml(ghostId)}</strong></div>
      <div class="about-runtime-chip"><span>UPTIME</span><strong>${escHtml(uptimeLabel)}</strong></div>
      <div class="about-runtime-chip"><span>TRACES</span><strong>${escHtml(String(traces))}</strong></div>
      <div class="about-runtime-chip"><span>AUTONOMY</span><strong>${escHtml(autonomyStatus)}</strong></div>
      <div class="about-runtime-chip"><span>PROMPT CONTRACT</span><strong>${escHtml(promptOk)}</strong></div>
      <div class="about-runtime-chip"><span>FINGERPRINT</span><strong>${escHtml(fingerprint)}</strong></div>
      <div class="about-runtime-chip"><span>GENERATED</span><strong>${escHtml(generated)}</strong></div>
    </div>
    ${missing.length ? `<div class="about-runtime-notes">missing checks: ${escHtml(missing.join(', '))}</div>` : ''}
  `;
}

function renderAboutDocCards(docs, query, emptyLabel) {
  const safeDocs = Array.isArray(docs) ? docs : [];
  const filtered = safeDocs.filter((doc) => {
    if (!query) return true;
    const hay = `${doc.title || ''}\n${doc.path || ''}\n${doc.markdown || ''}`.toLowerCase();
    return hay.includes(query);
  });
  if (!filtered.length) {
    return `<div class="dim">${escHtml(emptyLabel)}</div>`;
  }
  return filtered.map((doc, idx) => {
    const title = String(doc.title || 'Untitled');
    const path = String(doc.path || '-');
    const lines = Number(doc.line_count || 0);
    const markdown = String(doc.markdown || '');
    return `
      <details class="about-doc-card"${idx === 0 ? ' open' : ''}>
        <summary>
          <span class="about-doc-title">${escHtml(title)}</span>
          <span class="about-doc-meta">${escHtml(path)}${lines > 0 ? ` · ${lines} lines` : ''}</span>
        </summary>
        <div class="about-doc-body">${renderAboutMarkdown(markdown)}</div>
      </details>
    `;
  }).join('');
}

function renderAboutFaq(faqItems, query) {
  const safeItems = Array.isArray(faqItems) ? faqItems : [];
  const filtered = safeItems.filter((item) => {
    if (!query) return true;
    const hay = `${item.question || ''}\n${item.answer_markdown || ''}`.toLowerCase();
    return hay.includes(query);
  });
  if (!filtered.length) return '<div class="dim">No FAQ entries match current filter.</div>';
  return filtered.map((item, idx) => `
    <details class="about-doc-card"${idx === 0 ? ' open' : ''}>
      <summary><span class="about-doc-title">Q: ${escHtml(String(item.question || ''))}</span></summary>
      <div class="about-doc-body">${renderAboutMarkdown(String(item.answer_markdown || ''))}</div>
    </details>
  `).join('');
}

function renderAboutGlossary(glossaryItems, query) {
  const safeItems = Array.isArray(glossaryItems) ? glossaryItems : [];
  const filtered = safeItems.filter((item) => {
    if (!query) return true;
    const hay = `${item.term || ''}\n${item.definition_markdown || ''}`.toLowerCase();
    return hay.includes(query);
  });
  if (!filtered.length) return '<div class="dim">No glossary terms match current filter.</div>';
  return filtered.map((item) => `
    <details class="about-doc-card">
      <summary><span class="about-doc-title">${escHtml(String(item.term || ''))}</span></summary>
      <div class="about-doc-body">${renderAboutMarkdown(String(item.definition_markdown || ''))}</div>
    </details>
  `).join('');
}

function renderAboutOverview(payload, query) {
  const sourceDocs = payload && payload.source_documents ? payload.source_documents : {};
  const tech = Array.isArray(sourceDocs.technical_engineering) ? sourceDocs.technical_engineering : [];
  const research = Array.isArray(sourceDocs.falsifiable_research) ? sourceDocs.falsifiable_research : [];
  const faqCount = Array.isArray(payload?.faq) ? payload.faq.length : 0;
  const glossaryCount = Array.isArray(payload?.glossary) ? payload.glossary.length : 0;
  const queryHint = query ? `<div class="about-runtime-notes">Filtered by: ${escHtml(query)}</div>` : '';
  return `
    <div class="about-overview">
      <h2>ABOUT CONTENT SOURCES</h2>
      <p>Runtime snapshot and canonical docs are loaded live from the backend to reflect current architecture and research posture.</p>
      ${queryHint}
      <div class="about-overview-grid">
        <div class="about-overview-card">
          <h3>TECHNICAL ENGINEERING</h3>
          <div>${escHtml(String(tech.length))} source documents</div>
        </div>
        <div class="about-overview-card">
          <h3>FALSIFIABLE RESEARCH</h3>
          <div>${escHtml(String(research.length))} source documents</div>
        </div>
        <div class="about-overview-card">
          <h3>FAQ</h3>
          <div>${escHtml(String(faqCount))} entries</div>
        </div>
        <div class="about-overview-card">
          <h3>GLOSSARY</h3>
          <div>${escHtml(String(glossaryCount))} terms</div>
        </div>
      </div>
      <h3>Technical Sources</h3>
      <ul>${tech.map((p) => `<li><code>${escHtml(String(p))}</code></li>`).join('') || '<li class="dim">No sources listed.</li>'}</ul>
      <h3>Research Sources</h3>
      <ul>${research.map((p) => `<li><code>${escHtml(String(p))}</code></li>`).join('') || '<li class="dim">No sources listed.</li>'}</ul>
    </div>
  `;
}

function renderAboutView() {
  const query = aboutQueryNormalized(state.aboutQuery);
  if (dom.aboutTabButtons && dom.aboutTabButtons.forEach) {
    dom.aboutTabButtons.forEach((btn) => {
      const tab = String(btn.getAttribute('data-about-tab') || '');
      btn.classList.toggle('active', tab === state.aboutActiveTab);
    });
  }

  if (!state.aboutContent) {
    if (dom.aboutRuntime) {
      dom.aboutRuntime.innerHTML = state.aboutLoadError
        ? `<div class="warn-text">About runtime unavailable: ${escHtml(state.aboutLoadError)}</div>`
        : '<div class="dim">Runtime snapshot unavailable.</div>';
    }
    if (dom.aboutContent) {
      dom.aboutContent.innerHTML = state.aboutLoading
        ? '<div class="dim">Loading About content...</div>'
        : `<div class="warn-text">About content unavailable${state.aboutLoadError ? `: ${escHtml(state.aboutLoadError)}` : ''}.</div>`;
    }
    if (dom.aboutFallback) dom.aboutFallback.hidden = false;
    return;
  }

  if (dom.aboutFallback) dom.aboutFallback.hidden = true;
  renderAboutRuntime(state.aboutContent.runtime_snapshot || {});

  if (!dom.aboutContent) return;
  const payload = state.aboutContent;
  if (state.aboutActiveTab === 'technical') {
    dom.aboutContent.innerHTML = renderAboutDocCards(payload.technical_engineering_docs, query, 'No technical docs match current filter.');
    return;
  }
  if (state.aboutActiveTab === 'research') {
    dom.aboutContent.innerHTML = renderAboutDocCards(payload.falsifiable_research_docs, query, 'No research docs match current filter.');
    return;
  }
  if (state.aboutActiveTab === 'faq') {
    dom.aboutContent.innerHTML = renderAboutFaq(payload.faq, query);
    return;
  }
  if (state.aboutActiveTab === 'glossary') {
    dom.aboutContent.innerHTML = renderAboutGlossary(payload.glossary, query);
    return;
  }
  dom.aboutContent.innerHTML = renderAboutOverview(payload, query);
}

async function ensureAboutContent(force = false) {
  if (state.aboutLoading) return;
  if (!force && state.aboutContent) {
    renderAboutView();
    return;
  }

  state.aboutLoading = true;
  state.aboutLoadError = '';
  renderAboutView();
  try {
    const res = await fetch(`${API_BASE}/ghost/about/content`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    state.aboutContent = data && typeof data === 'object' ? data : null;
  } catch (err) {
    state.aboutLoadError = String(err?.message || err || 'request failed');
    maybeNotify('about-load-failed', 'warning', `About content load failed: ${state.aboutLoadError}`, 8000);
  } finally {
    state.aboutLoading = false;
    renderAboutView();
  }
}

function openAboutModal() {
  if (!dom.aboutModal) return;
  dom.aboutModal.classList.add('active');
  void ensureAboutContent(false);
}

function closeAboutModal() {
  if (!dom.aboutModal) return;
  dom.aboutModal.classList.remove('active');
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
  if (pressure) {
    const pressureHpa = Number(s.barometric_pressure_hpa);
    pressure.textContent = Number.isFinite(pressureHpa) ? `${pressureHpa} hPa` : '—';
  }
  if (phase) {
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
    const rawPhase = String(s.time_phase || '').trim().toLowerCase();
    phase.textContent = rawPhase ? (phaseNames[rawPhase] || rawPhase.toUpperCase()) : '—';
  }
  if (fatigueFill && fatigueVal) {
    const pressure = Number(s.dream_pressure ?? s.coalescence_pressure ?? s.fatigue_index ?? 0);
    const pct = Math.round(Math.max(0, Math.min(1, pressure)) * 100);
    fatigueFill.style.width = `${pct}%`;
    fatigueVal.textContent = `${pct}%`;
    fatigueFill.classList.remove('warn', 'crit');
    if (pct > 60) fatigueFill.classList.add('crit');
    else if (pct > 30) fatigueFill.classList.add('warn');
  }
  if (internet) {
    const mood = String(s.internet_mood || '').trim().toLowerCase();
    const latMs = Number(s.global_latency_avg_ms);

    if (!mood || mood === 'unknown') {
      internet.textContent = '—';
      internet.className = 'ambient-value';
      return;
    }
    const moodDisplay = mood.toUpperCase();
    const latStr = Number.isFinite(latMs) ? ` (${Math.round(latMs)}ms)` : '';
    internet.textContent = `GLOBAL ${moodDisplay}${latStr}`;
    internet.className = `ambient-value internet-${mood}`;
  }
}

function updateCoalescenceGauge(fillEl, valueEl, scalar) {
  if (!fillEl || !valueEl) return;
  const safe = clamp01(scalar);
  const pct = Math.round(safe * 100);
  fillEl.style.width = `${pct}%`;
  valueEl.textContent = `${pct}%`;
  fillEl.classList.remove('warn', 'crit');
  if (safe >= 0.85) fillEl.classList.add('crit');
  else if (safe >= 0.6) fillEl.classList.add('warn');
}

function updateCoalescenceUI(somatic) {
  const s = asObject(somatic);
  const totalPressure = clamp01(s.coalescence_pressure ?? s.dream_pressure ?? s.fatigue_index ?? 0);
  const interactionPressure = clamp01(s.coalescence_interaction_pressure);
  const idlePressure = clamp01(s.coalescence_idle_pressure);
  const circadianPressure = clamp01(s.circadian_fatigue_index ?? s.fatigue_index ?? 0);

  updateCoalescenceGauge(dom.coalescencePressureFill, dom.coalescencePressureVal, totalPressure);
  updateCoalescenceGauge(dom.coalescenceInteractionFill, dom.coalescenceInteractionVal, interactionPressure);
  updateCoalescenceGauge(dom.coalescenceIdleFill, dom.coalescenceIdleVal, idlePressure);
  updateCoalescenceGauge(dom.coalescenceCircadianFill, dom.coalescenceCircadianVal, circadianPressure);

  const interactionsSince = Math.max(0, Math.round(Number(s.interactions_since_coalescence || 0)));
  const secondsSince = Math.max(0, Math.round(Number(s.seconds_since_coalescence || 0)));
  const threshold = Math.max(0, Math.round(Number(state.health?.coalescence_threshold || 0)));
  const quietudeActive = Boolean(s?.self_preferences?.quietude_active);

  const driverMap = {
    interaction: interactionPressure,
    idle: idlePressure,
    circadian: circadianPressure,
  };
  let topDriver = 'interaction';
  let topValue = -1;
  for (const [key, val] of Object.entries(driverMap)) {
    if (val > topValue) {
      topValue = val;
      topDriver = key;
    }
  }
  const driverLabel = {
    interaction: 'INTERACTION',
    idle: 'IDLE TIME',
    circadian: 'CIRCADIAN',
  }[topDriver] || 'INTERACTION';

  if (dom.coalescenceDriver) dom.coalescenceDriver.textContent = driverLabel;
  if (dom.coalescenceSince) dom.coalescenceSince.textContent = interactionsSince.toLocaleString();
  if (dom.coalescenceElapsed) dom.coalescenceElapsed.textContent = formatTempo(secondsSince);
  if (dom.coalescenceThreshold) dom.coalescenceThreshold.textContent = threshold > 0 ? `${threshold} turns` : '—';
  if (dom.coalescenceRemaining) {
    if (threshold > 0) {
      const remaining = Math.max(0, threshold - interactionsSince);
      dom.coalescenceRemaining.textContent = `remaining interactions: ${remaining}`;
    } else {
      dom.coalescenceRemaining.textContent = 'remaining interactions: —';
    }
  }
  if (dom.coalescenceQuietude) {
    dom.coalescenceQuietude.textContent = quietudeActive ? 'ACTIVE' : 'INACTIVE';
    dom.coalescenceQuietude.className = `hw-value mono coalescence-quietude ${quietudeActive ? 'active' : 'inactive'}`;
  }
  if (!quietudeActive) {
    exitProfoundSubstrate();
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
    dom.aboutBtn.addEventListener('click', openAboutModal);
  }
  if (dom.aboutClose) {
    dom.aboutClose.addEventListener('click', closeAboutModal);
  }
  if (dom.aboutRefreshBtn) {
    dom.aboutRefreshBtn.addEventListener('click', () => {
      void ensureAboutContent(true);
    });
  }
  if (dom.aboutSearchInput) {
    dom.aboutSearchInput.addEventListener('input', (e) => {
      state.aboutQuery = String(e?.target?.value || '');
      renderAboutView();
    });
  }
  if (dom.aboutTabButtons && dom.aboutTabButtons.forEach) {
    dom.aboutTabButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = String(btn.getAttribute('data-about-tab') || '').trim().toLowerCase();
        if (!tab) return;
        state.aboutActiveTab = tab;
        renderAboutView();
      });
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
        closeAboutModal();
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
    if (dom.morpheusRewardOverlay && dom.morpheusRewardOverlay.classList.contains('active')) {
      dom.morpheusRewardOverlay.classList.remove('active');
      if (state.morpheus.rewardAnimationTimer) {
        clearInterval(state.morpheus.rewardAnimationTimer);
        state.morpheus.rewardAnimationTimer = null;
      }
      return;
    }
    if (dom.morpheusUnlockedOverlay && dom.morpheusUnlockedOverlay.classList.contains('active')) {
      closeMorpheusTerminal();
      return;
    }
    if (dom.morpheusBlueOverlay && dom.morpheusBlueOverlay.classList.contains('active')) {
      simulateMorpheusLogout();
      return;
    }
    if (dom.morpheusOverlay && dom.morpheusOverlay.classList.contains('active')) {
      resetMorpheusState({ keepClue: state.morpheus.secretProgressPreserved });
      return;
    }
    closeTopologyModal();
    closeRolodexModal();
    if (dom.sessionsModal) dom.sessionsModal.classList.remove('active');
    if (dom.timelineModal) dom.timelineModal.classList.remove('active');
    closeAboutModal();
    if (dom.auditModal) dom.auditModal.classList.remove('active');
    if (dom.tickerModal) dom.tickerModal.classList.remove('active');
    if (dom.opsModal) dom.opsModal.classList.remove('active');
  });

  if (dom.queueApproveAllBtn) {
    dom.queueApproveAllBtn.addEventListener('click', approveAllMutations);
  }

  // Wire tab switching
  bindAuditTabEvents();
}

function rolodexConfidenceBand(value) {
  const v = Number(value || 0);
  if (v >= 0.8) return { label: 'HIGH', tone: 'high' };
  if (v >= 0.55) return { label: 'MID', tone: 'mid' };
  return { label: 'LOW', tone: 'low' };
}

function syncRolodexTabSelection() {
  document.querySelectorAll('.rolodex-tab').forEach((tab) => {
    const isActive = (tab.getAttribute('data-tab') || 'persons') === state.rolodexActiveTab;
    tab.classList.toggle('active', isActive);
  });
}






function buildRolodexTelemetryPanel() {
  const world = asObject(state.rolodexWorld);
  const counts = asObject(world.counts);
  const atlasMeta = asObject(world.metadata);
  const diag = asObject(state.rolodexDiagnostics);
  const integrityPayload = asObject(diag.integrity);
  const integrityReport = asObject(integrityPayload.report);
  const integrityCounts = asObject(integrityReport.counts);
  const failures = asObject(diag.failures);
  const duplicateClusters = Array.isArray(world.duplicate_clusters) ? world.duplicate_clusters.length : 0;
  const atlasIntegrity = asObject(world.integrity);
  const atlasIntegrityCounts = asObject(atlasIntegrity.counts);
  const mode = String(diag.mode || 'unknown').toLowerCase();
  const updatedAt = Number(diag.updatedAt || 0);
  const updated = updatedAt
    ? new Date(updatedAt).toLocaleTimeString('en-US', { hour12: false })
    : 'n/a';
  const failuresCount = Number(failures.count || 0);
  const snapshotVersion = world.snapshot_version ?? '-';
  const snapshotAge = Math.max(0, Math.round(Number(atlasMeta.snapshot_age_seconds || 0)));
  const stale = Boolean(atlasMeta.stale || atlasMeta.recovery_active || atlasMeta.last_build_ok === false);

  let diagnosticsBlock = `
    <div class="dim">Ops telemetry unavailable. Unlock ops code to view ingest failures and integrity checks.</div>
  `;
  if (mode === 'ready') {
    diagnosticsBlock = `
      <div class="rolodex-summary-chips">
        <span class="rolodex-chip ${failuresCount > 0 ? 'low' : 'high'}">failures ${failuresCount}</span>
        <span class="rolodex-chip ${Number(integrityCounts.orphaned_facts || 0) > 0 ? 'low' : 'high'}">orphans ${Number(integrityCounts.orphaned_facts || 0)}</span>
        <span class="rolodex-chip ${Number(integrityCounts.empty_profiles || 0) > 0 ? 'mid' : 'high'}">empty ${Number(integrityCounts.empty_profiles || 0)}</span>
        <span class="rolodex-chip ${Number(integrityCounts.stale_bindings || 0) > 0 ? 'mid' : 'high'}">stale ${Number(integrityCounts.stale_bindings || 0)}</span>
        <span class="rolodex-chip ${Number(integrityCounts.duplicate_profiles || 0) > 0 ? 'mid' : 'high'}">duplicates ${Number(integrityCounts.duplicate_profiles || 0)}</span>
        <span class="rolodex-chip ${duplicateClusters > 0 ? 'mid' : 'high'}">atlas_dupes ${duplicateClusters}</span>
      </div>
      <div class="audit-subtext">diagnostics updated: ${escHtml(updated)}</div>
    `;
  } else if (mode === 'error') {
    diagnosticsBlock = `<div class="warn-text">Ops diagnostics failed to load.</div>`;
  }

  return `
    <div class="rolodex-facts-block" style="margin-bottom: 12px;">
      <div class="rolodex-section-title">ROLODEX + INTEGRITY TELEMETRY</div>
      <div class="rolodex-summary-chips">
        <span class="rolodex-chip">rolodex_v ${escHtml(String(snapshotVersion))}</span>
        <span class="rolodex-chip ${stale ? 'mid' : 'high'}">entry_age ${snapshotAge}s</span>
        <span class="rolodex-chip">people ${Number(counts.persons || 0)}</span>
        <span class="rolodex-chip">places ${Number(counts.places || 0)}</span>
        <span class="rolodex-chip">things ${Number(counts.things || 0)}</span>
        <span class="rolodex-chip">ideas ${Number(counts.ideas || 0)}</span>
        <span class="rolodex-chip">person_person ${Number(counts.person_person || 0)}</span>
        <span class="rolodex-chip">person_place ${Number(counts.person_place || 0)}</span>
        <span class="rolodex-chip">person_thing ${Number(counts.person_thing || 0)}</span>
        <span class="rolodex-chip">idea_links ${Number(counts.idea_links || 0)}</span>
        <span class="rolodex-chip">integrity_checks ${failuresCount}</span>
      </div>
      ${diagnosticsBlock}
    </div>
  `;
}

function formatRolodexRelativeTime(tsSeconds) {
  const ts = Number(tsSeconds || 0);
  if (!ts) return 'n/a';
  const diff = Math.max(0, Math.floor(Date.now() / 1000) - Math.floor(ts));
  if (diff < 15) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function isRolodexArchivedTimestamp(tsSeconds) {
  return Number(tsSeconds || 0) > 0;
}

function isRolodexEntryArchived(entry) {
  return isRolodexArchivedTimestamp(entry?.invalidated_at);
}

function syncRolodexArchiveToggle() {
  if (!dom.rolodexArchiveToggle) return;
  const enabled = Boolean(state.rolodexIncludeArchived);
  dom.rolodexArchiveToggle.textContent = enabled ? 'ARCHIVED: ON' : 'ARCHIVED: OFF';
  dom.rolodexArchiveToggle.classList.toggle('active', enabled);
  dom.rolodexArchiveToggle.setAttribute('aria-pressed', enabled ? 'true' : 'false');
}

function updateRolodexEntryInState(person) {
  if (!person || !person.person_key) return;
  state.rolodexEntries = (state.rolodexEntries || []).map((row) => (
    row.person_key === person.person_key
      ? { ...row, ...person }
      : row
  ));
}

async function readRolodexResponse(res) {
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (res.ok) return data;
  const detail = data?.detail;
  const detailText = typeof detail === 'string'
    ? detail
    : (detail && typeof detail === 'object' ? (detail.error || JSON.stringify(detail)) : '');
  const fallback = data?.error || detailText || `HTTP ${res.status}`;
  throw new Error(String(fallback));
}

function shortSessionId(sessionId) {
  const raw = String(sessionId || '').trim();
  if (!raw) return 'unknown';
  if (raw.length <= 12) return raw;
  return `${raw.slice(0, 8)}…${raw.slice(-4)}`;
}

async function readJsonSafe(res, fallback = {}) {
  if (!res) return fallback;
  try {
    return await res.json();
  } catch (_) {
    return fallback;
  }
}

function formatSessionStamp(tsSeconds) {
  const ts = Number(tsSeconds || 0);
  if (!Number.isFinite(ts) || ts <= 0) return 'n/a';
  return new Date(ts * 1000).toLocaleString();
}

function setSessionLineageIndicator(lineage = []) {
  const el = dom.sessionLineageIndicator;
  const rows = Array.isArray(lineage) ? lineage : [];
  if (!el) return;
  if (rows.length <= 1) {
    el.style.display = 'none';
    el.textContent = '';
    state.sessionLineage = null;
    return;
  }
  const parent = rows[rows.length - 2] || {};
  const root = rows[0] || {};
  el.style.display = 'block';
  el.textContent = `continued from ${shortSessionId(parent.session_id)} · root ${shortSessionId(root.session_id)} · hops ${rows.length - 1}`;
  state.sessionLineage = {
    session_id: String(rows[rows.length - 1]?.session_id || ''),
    lineage: rows,
  };
}

function clearChatMessages() {
  if (!dom.messages) return;
  dom.messages.innerHTML = '';
}

function appendHydratedMessage(entry) {
  if (!dom.messages || !entry) return;
  const role = String(entry.role || '').toLowerCase();
  const isGhost = role !== 'user';
  const text = String(entry.content || '');
  const ts = Number(entry.timestamp || 0);
  const when = Number.isFinite(ts) && ts > 0
    ? new Date(ts * 1000)
    : new Date();
  const timeStr = when.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const msg = document.createElement('div');
  msg.className = `message ${isGhost ? 'ghost-msg' : 'user-msg'}`;
  msg.innerHTML = `
    <div class="msg-meta">
      <div class="msg-meta-left">
        <span class="msg-role">${isGhost ? 'GHOST ω-7' : 'OPERATOR'}</span>
        <span class="msg-time">${timeStr}</span>
      </div>
      <div class="msg-meta-right"></div>
    </div>
    <div class="msg-body">${formatGhostText(text)}</div>
  `;
  dom.messages.appendChild(msg);
}

async function fetchSessionThread(sessionId) {
  const sid = String(sessionId || '').trim();
  if (!sid) throw new Error('session_id is required');
  const qp = encodeURIComponent(sid);
  const res = await fetch(`${API_BASE}/ghost/sessions/${qp}/thread`);
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (!res.ok) {
    const detail = String(data?.detail || data?.error || `HTTP ${res.status}`);
    throw new Error(detail);
  }
  return data;
}

function hydrateConversationThread(threadPayload) {
  const payload = threadPayload && typeof threadPayload === 'object' ? threadPayload : {};
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  const lineage = Array.isArray(payload.lineage) ? payload.lineage : [];
  clearChatMessages();
  if (!messages.length && dom.messages) {
    dom.messages.innerHTML = `
      <div class="message ghost-msg system-msg">
        <div class="msg-meta">
          <span class="msg-role">GHOST ω-7</span>
          <span class="msg-time">${new Date().toLocaleTimeString('en-US', { hour12: false })}</span>
        </div>
        <div class="msg-body"><span class="dim">No transcript messages were found for this thread.</span></div>
      </div>
    `;
  } else {
    messages.forEach((entry) => appendHydratedMessage(entry));
  }
  setSessionLineageIndicator(lineage);
  scrollToBottom();
}

async function resumeConversationSession(parentSessionId, opts = {}) {
  const parentId = String(parentSessionId || '').trim();
  if (!parentId || state.isStreaming) return false;
  const closeSessionsModal = Boolean(opts.closeSessionsModal);
  const closeRolodexDrilldown = Boolean(opts.closeRolodexDrilldown);
  try {
    const res = await fetch(
      `${API_BASE}/ghost/sessions/${encodeURIComponent(parentId)}/resume`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...opsHeaders(),
        },
      },
    );
    const data = await readRolodexResponse(res);
    const childId = String(data?.session_id || '').trim();
    if (!childId) throw new Error('Resume response missing child session id');

    state.sessionId = childId;
    const threadPayload = await fetchSessionThread(childId);
    hydrateConversationThread(threadPayload);

    if (closeSessionsModal && dom.sessionsModal) {
      dom.sessionsModal.classList.remove('active');
    }
    if (closeRolodexDrilldown) {
      document.querySelectorAll('.rolodex-drilldown').forEach((el) => el.remove());
    }
    notify('success', `Resumed session ${shortSessionId(parentId)}.`);
    return true;
  } catch (err) {
    const msg = String(err?.message || err || 'resume failed');
    notify('error', `Failed to resume session: ${msg}`);
    return false;
  }
}

function renderSessionsList() {
  if (!dom.sessionsList) return;
  const rows = Array.isArray(state.sessionsEntries) ? state.sessionsEntries : [];
  if (dom.sessionsCount) {
    const resumableCount = rows.filter((row) => Boolean(row?.resumable)).length;
    dom.sessionsCount.textContent = `${rows.length} sessions · ${resumableCount} resumable`;
  }
  if (!rows.length) {
    dom.sessionsList.innerHTML = '<div class="dim">No operator sessions found.</div>';
    return;
  }
  dom.sessionsList.innerHTML = rows.map((row) => {
    const sid = String(row.session_id || '');
    const resumable = Boolean(row.resumable);
    const started = formatSessionStamp(row.started_at);
    const ended = row.ended_at ? formatSessionStamp(row.ended_at) : 'active';
    const summary = String(row.summary || '').trim() || 'No summary';
    const lineageHint = row.continuation_parent_session_id
      ? `continued from ${shortSessionId(row.continuation_parent_session_id)}`
      : 'root session';
    return `
      <div class="session-row">
        <div class="session-row-main">
          <div class="session-row-title">${escHtml(shortSessionId(sid))} · ${escHtml(String(row.channel || 'operator_ui'))}</div>
          <div class="session-row-meta">start ${escHtml(started)} · end ${escHtml(ended)} · msgs ${Number(row.message_count || 0)} · ${escHtml(lineageHint)}</div>
          <div class="session-row-summary">${escHtml(summary)}</div>
        </div>
        <div class="session-row-actions">
          <button class="modal-btn session-resume-btn" data-session-id="${escHtml(sid)}" ${resumable ? '' : 'disabled'}>RESUME</button>
        </div>
      </div>
    `;
  }).join('');

  dom.sessionsList.querySelectorAll('.session-resume-btn[data-session-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const sid = btn.getAttribute('data-session-id') || '';
      if (!sid) return;
      btn.setAttribute('disabled', 'true');
      await resumeConversationSession(sid, { closeSessionsModal: true });
    });
  });
}

async function loadSessionsList() {
  if (!dom.sessionsList) return;
  state.sessionsLoading = true;
  dom.sessionsList.innerHTML = '<div class="dim">Loading operator sessions...</div>';
  try {
    const res = await fetch(`${API_BASE}/ghost/sessions?channel=operator_ui&limit=80`);
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      data = {};
    }
    if (!res.ok) {
      const detail = String(data?.detail || data?.error || `HTTP ${res.status}`);
      throw new Error(detail);
    }
    state.sessionsEntries = Array.isArray(data?.sessions) ? data.sessions : [];
    renderSessionsList();
  } catch (err) {
    const msg = String(err?.message || err || 'sessions unavailable');
    state.sessionsEntries = [];
    if (dom.sessionsCount) dom.sessionsCount.textContent = 'error';
    dom.sessionsList.innerHTML = `<div class="warn-text">Failed to load sessions: ${escHtml(msg)}</div>`;
  } finally {
    state.sessionsLoading = false;
  }
}

function openSessionsModal() {
  if (!dom.sessionsModal) return;
  dom.sessionsModal.classList.add('active');
  void loadSessionsList();
}

function closeSessionsModal() {
  if (!dom.sessionsModal) return;
  dom.sessionsModal.classList.remove('active');
}

function bindSessionsEvents() {
  if (dom.sessionsBtn) {
    dom.sessionsBtn.addEventListener('click', openSessionsModal);
  }
  if (dom.sessionsClose) {
    dom.sessionsClose.addEventListener('click', closeSessionsModal);
  }
  if (dom.sessionsRefresh) {
    dom.sessionsRefresh.addEventListener('click', () => {
      void loadSessionsList();
    });
  }
  if (dom.sessionsModal) {
    dom.sessionsModal.addEventListener('click', (e) => {
      if (e.target === dom.sessionsModal) closeSessionsModal();
    });
  }
}

async function loadRolodexDiagnostics() {
  const base = {
    mode: 'locked',
    failures: null,
    integrity: null,
    updatedAt: Date.now(),
  };
  if (!state.opsCode) {
    state.rolodexDiagnostics = base;
    return base;
  }

  const readJsonSafe = async (res) => {
    try {
      return await res.json();
    } catch (_) {
      return {};
    }
  };

  try {
    const [integrityRes, failuresRes] = await Promise.all([
      fetch(`${API_BASE}/ghost/rolodex/integrity?include_samples=false`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/rolodex/failures?limit=80&unresolved_only=true`, { headers: opsHeaders() }),
    ]);
    if ([integrityRes.status, failuresRes.status].some((code) => code === 401 || code === 403)) {
      state.rolodexDiagnostics = base;
      return base;
    }
    const [integrityData, failuresData] = await Promise.all([readJsonSafe(integrityRes), readJsonSafe(failuresRes)]);
    if (!integrityRes.ok) throw new Error(`integrity HTTP ${integrityRes.status}`);
    if (!failuresRes.ok) throw new Error(`failures HTTP ${failuresRes.status}`);
    state.rolodexDiagnostics = {
      mode: 'ready',
      integrity: integrityData,
      failures: failuresData,
      updatedAt: Date.now(),
    };
    return state.rolodexDiagnostics;
  } catch (err) {
    state.rolodexDiagnostics = {
      mode: 'error',
      integrity: null,
      failures: null,
      updatedAt: Date.now(),
      error: String(err?.message || err || 'diagnostics load failed'),
    };
    return state.rolodexDiagnostics;
  }
}

async function setRolodexPersonLock(personKey, locked) {
  if (!personKey || state.rolodexActionBusy) return;
  state.rolodexActionBusy = true;
  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}/lock`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locked: Boolean(locked) }),
    });
    const data = await readRolodexResponse(res);
    if (data?.status === 'shadow_route') {
      notify('warning', 'Lock change was shadow-routed and not applied.');
      await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
      return;
    }
    const person = data?.person;
    if (person && person.person_key) {
      updateRolodexEntryInState(person);
    } else {
      await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
      notify('warning', 'Lock response returned no profile payload; state refreshed.');
      return;
    }
    state.rolodexActionBusy = false;
    renderRolodexList();
    await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
    notify('success', locked ? 'Profile locked.' : 'Profile unlocked.');
  } catch (err) {
    const msg = String(err?.message || err || 'lock update failed');
    notify('error', `Failed to update lock state: ${msg}`);
  } finally {
    if (state.rolodexActionBusy) {
      state.rolodexActionBusy = false;
    }
  }
}

async function deleteRolodexPerson(personKey, displayName) {
  if (!personKey || state.rolodexActionBusy) return;
  const label = String(displayName || personKey || 'this profile');
  const entry = (state.rolodexEntries || []).find(e => e.person_key === personKey);
  if (entry && entry.is_locked) {
    notify('warning', `Cannot delete ${label}: Profile is LOCKED. Unlock first.`);
    return;
  }
  const ok = window.confirm(`Archive ${label} and soft-delete reinforced facts? You can restore later.`);
  if (!ok) return;
  state.rolodexActionBusy = true;
  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}`, { method: 'DELETE' });
    const data = await readRolodexResponse(res);
    if (data?.status === 'pending_approval') {
      await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
      notify('warning', 'Hard delete queued for governance approval (not yet applied).');
      return;
    }
    if (data?.status === 'shadow_route') {
      await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
      notify('warning', 'Delete request shadow-routed and not applied.');
      return;
    }
    state.rolodexEntries = (state.rolodexEntries || []).filter((row) => row.person_key !== personKey);
    if (state.rolodexSelectedKey === personKey) {
      state.rolodexSelectedKey = '';
    }
    state.rolodexActionBusy = false;
    renderRolodexList();
    if (dom.rolodexDetail) {
      dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">Profile archived (soft-deleted). Select another individual.</div>`;
    }
    await loadRolodexList();
    notify('success', 'Profile archived.');
  } catch (err) {
    const msg = String(err?.message || err || 'delete failed');
    notify('error', `Failed to delete profile: ${msg}`);
  } finally {
    if (state.rolodexActionBusy) {
      state.rolodexActionBusy = false;
    }
  }
}

async function restoreRolodexPerson(personKey, displayName) {
  if (!personKey || state.rolodexActionBusy) return;
  const label = String(displayName || personKey || 'this profile');
  const ok = window.confirm(`Restore archived profile for ${label}?`);
  if (!ok) return;
  state.rolodexActionBusy = true;
  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}/restore`, { method: 'POST' });
    const data = await readRolodexResponse(res);
    if (data?.status === 'pending_approval') {
      notify('warning', 'Restore queued for governance approval.');
      return;
    }
    if (data?.status === 'shadow_route') {
      notify('warning', 'Restore request shadow-routed and not applied.');
      return;
    }
    await loadRolodexList();
    state.rolodexSelectedKey = String(personKey || '');
    renderRolodexList();
    await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
    notify('success', 'Profile restored.');
  } catch (err) {
    const msg = String(err?.message || err || 'restore failed');
    notify('error', `Failed to restore profile: ${msg}`);
  } finally {
    if (state.rolodexActionBusy) {
      state.rolodexActionBusy = false;
    }
  }
}

async function mergeRolodexPerson(sourcePersonKey, sourceDisplayName) {
  if (!sourcePersonKey || state.rolodexActionBusy) return;
  const sourceKey = String(sourcePersonKey || '').trim();
  const sourceLabel = String(sourceDisplayName || sourceKey || 'source profile');
  const defaultTarget = sourceKey === 'operator' ? '' : 'operator';
  const requestedTarget = window.prompt(
    `Merge ${sourceLabel} into which canonical person key?`,
    defaultTarget,
  );
  if (requestedTarget == null) return;
  const targetKey = String(requestedTarget || '').trim().toLowerCase();
  if (!targetKey) {
    notify('warning', 'Merge canceled: target person key is required.');
    return;
  }
  if (targetKey === sourceKey) {
    notify('warning', 'Merge canceled: source and target keys are identical.');
    return;
  }
  const confirmed = window.confirm(`Merge "${sourceLabel}" into "${targetKey}"? This archives the source profile.`);
  if (!confirmed) return;

  state.rolodexActionBusy = true;
  try {
    const res = await fetch(`${API_BASE}/ghost/rolodex/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_person_key: sourceKey,
        target_person_key: targetKey,
        reason: 'rolodex_ui_merge',
      }),
    });
    const data = await readRolodexResponse(res);
    if (data?.status === 'shadow_route') {
      notify('warning', 'Merge request shadow-routed and not applied.');
      return;
    }
    await loadRolodexList();
    state.rolodexSelectedKey = targetKey;
    renderRolodexList();
    await loadRolodexDetails(targetKey, { includeArchived: state.rolodexIncludeArchived });
    notify('success', `Merged ${sourceLabel} into ${targetKey}.`);
  } catch (err) {
    const msg = String(err?.message || err || 'merge failed');
    notify('error', `Failed to merge profile: ${msg}`);
  } finally {
    state.rolodexActionBusy = false;
  }
}

function renderRolodexList() {
  if (!dom.rolodexList) return;
  const all = Array.isArray(state.rolodexEntries) ? state.rolodexEntries : [];
  const filter = String(state.rolodexFilter || '').trim().toLowerCase();
  const filteredRows = all.filter((row) => {
    if (!filter) return true;
    const name = String(row.display_name || row.concept_text || '').toLowerCase();
    const key = String(row.person_key || row.place_key || row.thing_key || row.concept_key || '').toLowerCase();
    const handle = String(row.contact_handle || '').toLowerCase();
    return name.includes(filter) || key.includes(filter) || handle.includes(filter);
  });
  const rows = filteredRows.slice(0, 400);

  if (dom.rolodexCount) {
    const worldCounts = asObject(asObject(state.rolodexWorld).counts);
    const activePersons = Number(worldCounts.active_persons || worldCounts.persons || all.length);
    const archivedPersons = Number(worldCounts.archived_persons || 0);
    const scopeLabel = state.rolodexIncludeArchived ? 'active+archived' : 'active';
    const archiveSummary = state.rolodexIncludeArchived
      ? ` · active ${activePersons} · archived ${archivedPersons}`
      : '';
    const clippedSummary = filteredRows.length > rows.length ? ` · showing first ${rows.length}` : '';
    dom.rolodexCount.textContent = `${filteredRows.length} shown / ${all.length} ${scopeLabel} · people ${Number(worldCounts.persons || 0)}${archiveSummary} · places ${Number(worldCounts.places || 0)} · things ${Number(worldCounts.things || 0)} · ideas ${Number(worldCounts.ideas || 0)}${clippedSummary}`;
  }

  if (!rows.length) {
    dom.rolodexList.innerHTML = filter
      ? '<div class="dim">No matches for current search.</div>'
      : '<div class="dim">No known entities yet.</div>';
    if (!filter && dom.rolodexDetail) {
      dom.rolodexDetail.innerHTML = '<div class="dim">Ghost has not formed any relational memory records here yet.</div>';
    }
    return;
  }

  dom.rolodexList.innerHTML = rows.map((row) => {
    const itemKey = row.person_key || row.place_key || row.thing_key || row.concept_key || '';
    const selected = itemKey === state.rolodexSelectedKey;
    const band = rolodexConfidenceBand(row.confidence);
    const isLocked = Boolean(row.is_locked);
    const isArchived = isRolodexEntryArchived(row);
    const itemName = row.display_name || row.concept_text || row.person_key || row.place_key || row.thing_key || row.concept_key || 'Unknown';
    const duplicateMap = new Map(); // FIXED: Initialized to avoid undefined error
    const duplicateInfo = duplicateMap.get(String(itemKey));
    
    let statsHtml = '';
    if (state.rolodexActiveTab === 'persons') {
      const interactions = Number(row.interaction_count || 0);
      const mentions = Number(row.mention_count || 0);
      const factCount = Number(row.fact_count || 0);
      statsHtml = `
        <span>chat ${interactions}</span>
        <span>mentions ${mentions}</span>
        <span>facts ${factCount}</span>
      `;
    } else {
       const provenance = row.provenance || row.source || 'unknown';
       statsHtml = `<span>source: ${escHtml(provenance)}</span>`;
    }

    const timeLabel = isArchived ? 'archived' : 'seen';
    const timeValue = isArchived ? (row.invalidated_at || row.updated_at) : (row.last_seen || row.updated_at);

    return `
      <button class="rolodex-row ${selected ? 'active' : ''}" data-item-key="${escHtml(itemKey)}">
        <div class="rolodex-row-head">
          <span class="rolodex-name">${escHtml(itemName)}</span>
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
            ${duplicateInfo ? `<span class="atlas-badge">${duplicateInfo.status === 'review_required' ? 'DUPLICATE' : `MERGED x${duplicateInfo.size}`}</span>` : ''}
            <span class="rolodex-band ${isArchived ? 'low' : (isLocked ? 'locked' : band.tone)}">${isArchived ? 'ARCHIVED' : (isLocked ? 'LOCKED' : band.label)}</span>
          </div>
        </div>
        <div class="rolodex-row-meta">
           <span>${timeLabel} ${escHtml(formatRolodexRelativeTime(timeValue))}</span>
           ${statsHtml}
        </div>
      </button>
    `;
  }).join('');

  dom.rolodexList.querySelectorAll('.rolodex-row').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const key = btn.getAttribute('data-item-key') || '';
      if (!key || key === state.rolodexSelectedKey) return;
      state.rolodexSelectedKey = key;
      renderRolodexList();
      await loadRolodexDetails(key, { includeArchived: state.rolodexIncludeArchived });
    });
  });
}

async function loadRolodexList() {
  if (!dom.rolodexList) return;
  if (state.rolodexPollBusy) return;
  state.rolodexPollBusy = true;
  dom.rolodexList.innerHTML = '<div class="dim">Loading Rolodex entities...</div>';
  if (dom.rolodexCount) dom.rolodexCount.textContent = 'loading...';
  syncRolodexArchiveToggle();
  try {
    const res = await fetch(`${API_BASE}/ghost/rolodex/world${state.rolodexIncludeArchived ? '?include_archived=true' : ''}`);
    const data = await readJsonSafe(res, {});
    if (!res.ok) {
      if (res.status === 503 && String(data?.status || '') === 'snapshot_unavailable') {
        state.rolodexWorld = data;
        state.rolodexEntries = [];
        dom.rolodexList.innerHTML = '<div class="warn-text">Rolodex unavailable. Retrying…</div>';
        if (dom.rolodexDetail) {
          dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">Snapshot recovery active. The UI will retry automatically.</div>`;
        }
        if (dom.rolodexCount) dom.rolodexCount.textContent = 'recovering';
        return;
      }
      throw new Error(String(data?.detail || data?.error || `HTTP ${res.status}`));
    }
    state.rolodexWorld = data;
    state.rolodexEntries = Array.isArray(data[state.rolodexActiveTab]) ? data[state.rolodexActiveTab] : [];
    renderRolodexList();

    const filtered = state.rolodexEntries.filter((row) => {
      const filter = String(state.rolodexFilter || '').trim().toLowerCase();
      if (!filter) return true;
      const name = String(row.display_name || row.concept_text || '').toLowerCase();
      const key = String(row.person_key || row.place_key || row.thing_key || row.concept_key || '').toLowerCase();
      const handle = String(row.contact_handle || '').toLowerCase();
      return name.includes(filter) || key.includes(filter) || handle.includes(filter);
    });
    const selectedStillVisible = filtered.some((row) => (row.person_key || row.place_key || row.thing_key || row.concept_key) === state.rolodexSelectedKey);
    if (!selectedStillVisible) {
      const firstRow = filtered[0] || {};
      state.rolodexSelectedKey = firstRow.person_key || firstRow.place_key || firstRow.thing_key || firstRow.concept_key || '';
    }
    if (state.rolodexSelectedKey) {
      renderRolodexList();
      await loadRolodexDetails(state.rolodexSelectedKey, { includeArchived: state.rolodexIncludeArchived });
    } else if (dom.rolodexDetail) {
      dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">Select an entity to view details.</div>`;
    }
  } catch (err) {
    const msg = String(err?.message || err || 'load failed');
    dom.rolodexList.innerHTML = `<div class="warn-text">Failed to load rolodex: ${escHtml(msg)}</div>`;
    if (dom.rolodexDetail) {
      dom.rolodexDetail.innerHTML = '<div class="warn-text">Unable to load selected entity.</div>';
    }
    if (dom.rolodexCount) dom.rolodexCount.textContent = 'error';
    notify('error', `Failed to load Atlas: ${msg}`);
  } finally {
    state.rolodexPollBusy = false;
  }
}

async function loadRolodexDetails(itemKey, opts = {}) {
  if (!dom.rolodexDetail || !itemKey) return;
  const includeArchived = Boolean(opts?.includeArchived || state.rolodexIncludeArchived);
  dom.rolodexDetail.innerHTML = '<div class="dim">Loading entity details...</div>';
  try {
    let data = (state.rolodexEntries || []).find((r) =>
      r.person_key === itemKey || r.place_key === itemKey || r.thing_key === itemKey || r.concept_key === itemKey
    );
    if (!data) {
      const qp = encodeURIComponent(String(itemKey));
      const archiveParam = includeArchived ? '&include_archived=true' : '';
      let endpoint = '';
      if (state.rolodexActiveTab === 'persons') {
        endpoint = `${API_BASE}/ghost/rolodex/${qp}?fact_limit=120${archiveParam}`;
      } else if (state.rolodexActiveTab === 'places') {
        endpoint = `${API_BASE}/ghost/entities/places/${qp}`;
      } else if (state.rolodexActiveTab === 'things') {
        endpoint = `${API_BASE}/ghost/entities/things/${qp}`;
      } else if (state.rolodexActiveTab === 'ideas') {
        endpoint = `${API_BASE}/ghost/entities/ideas/${qp}`;
      }
      const res = await fetch(endpoint);
      if (!res.ok) {
        if (res.status === 404) {
          dom.rolodexDetail.innerHTML = '<div class="warn-text">Entity not found (it may have been removed).</div>';
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      data = await res.json();
    }
    data = data && typeof data === 'object' ? JSON.parse(JSON.stringify(data)) : {};
    if (state.rolodexActiveTab !== 'persons') {
      const itemName = String(data.display_name || data.concept_text || data.place_key || data.thing_key || data.concept_key || itemKey || '');
      const confidence = Number(data.confidence || 0);
      const band = rolodexConfidenceBand(confidence);
      const status = String(data.status || 'active').toLowerCase();
      const isArchived = status === 'deprecated' || !!data.invalidated_at;
      const notesObj = data.notes || data.evidence_text || (data.metadata && data.metadata.evidence_text) || '';
      const notes = typeof notesObj === 'string' ? notesObj : JSON.stringify(notesObj);
      const isIdea = state.rolodexActiveTab === 'ideas';
      // ideas have no edit endpoints — keep them readonly
      const isEditable = !isIdea;
      const assocCounts = asObject(data.association_counts);
      const relationshipRows = Array.isArray(data.relationships) ? data.relationships : [];
      const relationSummary = isIdea
        ? `people ${Number(assocCounts.people || 0)} · places ${Number(assocCounts.places || 0)} · things ${Number(assocCounts.things || 0)}`
        : `people ${Number(assocCounts.people || 0)} · ideas ${Number(assocCounts.ideas || 0)}`;

      updateRolodexEntryInState({
        person_key: itemKey,
        display_name: itemName,
        confidence,
        invalidated_at: data.invalidated_at || null,
      });
      renderRolodexList();

      const actionsHtml = isEditable ? (isArchived
        ? `<button class="modal-btn rolodex-action-btn" data-role="entity-restore" data-entity-key="${escHtml(itemKey)}" data-entity-tab="${escHtml(state.rolodexActiveTab)}">RESTORE ENTITY</button>`
        : `<button class="modal-btn rolodex-action-btn danger" data-role="entity-deprecate" data-entity-key="${escHtml(itemKey)}" data-entity-tab="${escHtml(state.rolodexActiveTab)}">DEPRECATE</button>`
      ) : '';

      const editFieldsHtml = isEditable && !isArchived ? `
        <div class="rolodex-notes-section" style="margin-top:16px;">
          <div class="rolodex-notes-label">// DISPLAY NAME</div>
          <div style="display:flex;gap:8px;align-items:center;margin-top:4px;">
            <input type="text" id="entity-display-name-input" class="rolodex-contact-handle-input" value="${escHtml(itemName)}" placeholder="Display name…" autocomplete="off" spellcheck="false" style="flex:1;">
            <button class="modal-btn rolodex-action-btn" data-role="entity-name-save" data-entity-key="${escHtml(itemKey)}" data-entity-tab="${escHtml(state.rolodexActiveTab)}" style="white-space:nowrap;">SAVE NAME</button>
          </div>
          <div class="rolodex-notes-status" id="entity-name-status">Status: Static</div>
        </div>
        <div class="rolodex-notes-section" style="margin-top:16px;">
          <div class="rolodex-notes-label">// NOTES</div>
          <textarea class="rolodex-notes-area" id="entity-notes-input" placeholder="Add notes or context…" style="margin-top:4px;">${escHtml(notes)}</textarea>
          <div class="rolodex-notes-status" id="entity-notes-status">Status: Static</div>
        </div>
      ` : `
        <div class="rolodex-notes-section" style="margin-top:20px;">
          <div class="rolodex-notes-label">// NOTES & EVIDENCE</div>
          <div class="rolodex-notes-area" style="min-height:80px;white-space:pre-wrap;">${escHtml(notes || '(No notes)')}</div>
        </div>
      `;

      const summaryHtml = `
        <div class="rolodex-summary">
          <div class="rolodex-summary-title">${escHtml(itemName)}</div>
          <div class="rolodex-summary-key">${escHtml(itemKey)}</div>
          <div class="rolodex-summary-chips">
            <span class="rolodex-chip ${isArchived ? 'low' : band.tone}">${isArchived ? 'DEPRECATED' : `${band.label} CONFIDENCE (${Math.round(confidence * 100)}%)`}</span>
            <span class="rolodex-chip">source: ${escHtml(data.provenance || data.source || 'unknown')}</span>
            <span class="rolodex-chip">${escHtml(relationSummary)}</span>
            <span class="rolodex-chip" title="Created">created ${escHtml(formatRolodexRelativeTime(data.created_at || data.updated_at || Date.now()))}</span>
          </div>
          <div class="rolodex-actions-row" style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;">
            ${actionsHtml}
          </div>
          ${editFieldsHtml}
          <div class="rolodex-facts-block" style="margin-top:16px;">
            <div class="rolodex-section-title">RELATIONSHIPS</div>
            <div class="rolodex-history-list">
              ${relationshipRows.length ? relationshipRows.slice(0, 12).map((rel) => `
                <div class="rolodex-history-item">
                  <div class="rolodex-history-time">${escHtml(String(rel.direction || 'linked').toUpperCase())} · ${escHtml(String(rel.type || 'relation').replaceAll('_', ' '))}</div>
                  <div class="rolodex-history-content">${escHtml(String(rel.counterparty_label || rel.counterparty_key || 'unknown'))}</div>
                </div>
              `).join('') : '<div class="dim">No structured relationships recorded.</div>'}
            </div>
          </div>
          <div id="rolodex-drilldown-anchor"></div>
        </div>
      `;

      const telemetryHtml = buildRolodexTelemetryPanel();
      dom.rolodexDetail.innerHTML = telemetryHtml + summaryHtml;

      // Wire entity actions
      const deprecateBtn = dom.rolodexDetail.querySelector('[data-role="entity-deprecate"]');
      if (deprecateBtn) {
        deprecateBtn.addEventListener('click', async () => {
          const key = deprecateBtn.getAttribute('data-entity-key') || '';
          const tab = deprecateBtn.getAttribute('data-entity-tab') || '';
          if (!key || !tab) return;
          deprecateBtn.disabled = true;
          deprecateBtn.textContent = 'DEPRECATING…';
          try {
            const qp = encodeURIComponent(key);
            const endpoint = tab === 'places'
              ? `${API_BASE}/ghost/entities/places/${qp}/invalidate`
              : `${API_BASE}/ghost/entities/things/${qp}/invalidate`;
            const res = await fetch(endpoint, { method: 'PATCH', headers: { 'Content-Type': 'application/json' } });
            if (res.ok) {
              notify('success', `Entity deprecated: ${key}`);
              await loadRolodexDetails(key, { includeArchived: state.rolodexIncludeArchived });
              await loadRolodexList();
            } else {
              const err = await res.json().catch(() => ({}));
              notify('error', `Deprecate failed: ${String(err?.detail || err?.error || res.status)}`);
              deprecateBtn.disabled = false;
              deprecateBtn.textContent = 'DEPRECATE';
            }
          } catch (err) {
            notify('error', `Deprecate error: ${String(err?.message || err)}`);
            deprecateBtn.disabled = false;
            deprecateBtn.textContent = 'DEPRECATE';
          }
        });
      }

      const restoreBtn = dom.rolodexDetail.querySelector('[data-role="entity-restore"]');
      if (restoreBtn) {
        restoreBtn.addEventListener('click', async () => {
          const key = restoreBtn.getAttribute('data-entity-key') || '';
          const tab = restoreBtn.getAttribute('data-entity-tab') || '';
          if (!key || !tab) return;
          restoreBtn.disabled = true;
          restoreBtn.textContent = 'RESTORING…';
          try {
            const qp = encodeURIComponent(key);
            const endpoint = tab === 'places'
              ? `${API_BASE}/ghost/entities/places/${qp}`
              : `${API_BASE}/ghost/entities/things/${qp}`;
            const existingName = String(data.display_name || key);
            const res = await fetch(endpoint, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ display_name: existingName, status: 'active', confidence: Number(data.confidence || 0.6), provenance: String(data.provenance || 'operator'), notes: String(data.notes || '') }),
            });
            if (res.ok) {
              notify('success', `Entity restored: ${key}`);
              await loadRolodexDetails(key, { includeArchived: state.rolodexIncludeArchived });
              await loadRolodexList();
            } else {
              const err = await res.json().catch(() => ({}));
              notify('error', `Restore failed: ${String(err?.detail || err?.error || res.status)}`);
              restoreBtn.disabled = false;
              restoreBtn.textContent = 'RESTORE ENTITY';
            }
          } catch (err) {
            notify('error', `Restore error: ${String(err?.message || err)}`);
            restoreBtn.disabled = false;
            restoreBtn.textContent = 'RESTORE ENTITY';
          }
        });
      }

      const nameSaveBtn = dom.rolodexDetail.querySelector('[data-role="entity-name-save"]');
      if (nameSaveBtn) {
        nameSaveBtn.addEventListener('click', async () => {
          const key = nameSaveBtn.getAttribute('data-entity-key') || '';
          const tab = nameSaveBtn.getAttribute('data-entity-tab') || '';
          const input = document.getElementById('entity-display-name-input');
          const statusEl = document.getElementById('entity-name-status');
          if (!key || !tab || !(input instanceof HTMLInputElement)) return;
          const newName = input.value.trim();
          if (!newName) { if (statusEl) statusEl.textContent = 'Status: Name cannot be empty'; return; }
          if (statusEl) statusEl.textContent = 'Status: Saving…';
          nameSaveBtn.disabled = true;
          try {
            const qp = encodeURIComponent(key);
            const endpoint = tab === 'places'
              ? `${API_BASE}/ghost/entities/places/${qp}`
              : `${API_BASE}/ghost/entities/things/${qp}`;
            const res = await fetch(endpoint, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ display_name: newName, status: String(data.status || 'active'), confidence: Number(data.confidence || 0.6), provenance: String(data.provenance || 'operator'), notes: String(data.notes || '') }),
            });
            if (res.ok) {
              if (statusEl) statusEl.textContent = 'Status: Saved';
              notify('success', `Name updated: ${key}`);
              data.display_name = newName;
              updateRolodexEntryInState({ person_key: key, display_name: newName });
              renderRolodexList();
            } else {
              const err = await res.json().catch(() => ({}));
              if (statusEl) statusEl.textContent = `Status: Save failed (${String(err?.detail || res.status)})`;
            }
          } catch (err) {
            if (statusEl) statusEl.textContent = `Status: Error — ${String(err?.message || err)}`;
          } finally {
            nameSaveBtn.disabled = false;
          }
        });
      }

      // Notes auto-save for editable entities
      let entityNotesTimeout = null;
      const entityNotesInput = document.getElementById('entity-notes-input');
      const entityNotesStatus = document.getElementById('entity-notes-status');
      if (isEditable && !isArchived && entityNotesInput && entityNotesStatus) {
        entityNotesInput.addEventListener('input', () => {
          entityNotesStatus.textContent = 'Status: Changes pending…';
          if (entityNotesTimeout) clearTimeout(entityNotesTimeout);
          entityNotesTimeout = setTimeout(async () => {
            entityNotesStatus.textContent = 'Status: Saving…';
            try {
              const qp = encodeURIComponent(itemKey);
              const tab = state.rolodexActiveTab;
              const endpoint = tab === 'places'
                ? `${API_BASE}/ghost/entities/places/${qp}`
                : `${API_BASE}/ghost/entities/things/${qp}`;
              const res = await fetch(endpoint, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  display_name: String(data.display_name || itemName),
                  status: String(data.status || 'active'),
                  confidence: Number(data.confidence || 0.6),
                  provenance: String(data.provenance || 'operator'),
                  notes: entityNotesInput.value,
                }),
              });
              entityNotesStatus.textContent = res.ok ? 'Status: Saved' : `Status: Save failed (${res.status})`;
              if (res.ok) data.notes = entityNotesInput.value;
            } catch (err) {
              entityNotesStatus.textContent = `Status: Error — ${String(err?.message || err)}`;
            }
          }, 800);
        });
      }

      return;
    }

    const personKeyNormalized = String(data.person_key || itemKey || '');
    const confidence = Number(data.confidence || 0);
    const band = rolodexConfidenceBand(confidence);
    const facts = Array.isArray(data.facts) ? data.facts : [];
    const isLocked = Boolean(data.is_locked);
    const listEntry = (state.rolodexEntries || []).find((row) => String(row.person_key || '') === personKeyNormalized);
    const isArchived = isRolodexArchivedTimestamp(data.invalidated_at) || isRolodexEntryArchived(listEntry);
    const archivedAt = isArchived ? Number(data.invalidated_at || (listEntry && listEntry.invalidated_at) || 0) : 0;
    const assoc = asObject(listEntry && listEntry.association_counts);
    const assocPeople = Number(assoc.people || data?.association_counts?.people || 0);
    const assocPlaces = Number(assoc.places || 0);
    const assocThings = Number(assoc.things || 0);
    const assocIdeas = Number(assoc.ideas || 0);
    const relationships = Array.isArray(data.relationships) ? data.relationships : [];
    const aliases = Array.isArray(data.aliases) ? data.aliases : [];
    const telemetryHtml = buildRolodexTelemetryPanel();
    updateRolodexEntryInState({
      person_key: personKeyNormalized,
      display_name: data.display_name,
      contact_handle: String(data.contact_handle || ''),
      confidence,
      interaction_count: Number(data.interaction_count || 0),
      mention_count: Number(data.mention_count || 0),
      fact_count: facts.length,
      last_seen: data.last_seen,
      is_locked: isLocked,
      locked_at: data.locked_at || null,
      invalidated_at: data.invalidated_at || null,
    });
    renderRolodexList();

    const actionsHtml = isArchived
      ? `
          <button
            class="modal-btn rolodex-action-btn"
            data-role="rolodex-restore"
            data-person-key="${escHtml(personKeyNormalized)}"
            data-display-name="${escHtml(data.display_name || data.person_key || 'profile')}"
            ${state.rolodexActionBusy ? 'disabled' : ''}
          >
            RESTORE PROFILE
          </button>
        `
      : `
          <button
            class="modal-btn rolodex-action-btn ${isLocked ? 'locked' : ''}"
            data-role="rolodex-lock-toggle"
            data-person-key="${escHtml(personKeyNormalized)}"
            data-next-lock="${isLocked ? '0' : '1'}"
            ${state.rolodexActionBusy ? 'disabled' : ''}
          >
            ${isLocked ? 'UNLOCK PROFILE' : 'LOCK PROFILE'}
          </button>
          <button
            class="modal-btn rolodex-action-btn danger"
            data-role="rolodex-delete"
            data-person-key="${escHtml(personKeyNormalized)}"
            data-display-name="${escHtml(data.display_name || data.person_key || 'profile')}"
            ${state.rolodexActionBusy ? 'disabled' : ''}
          >
            DELETE PROFILE
          </button>
          <button
            class="modal-btn rolodex-action-btn"
            data-role="rolodex-merge"
            data-person-key="${escHtml(personKeyNormalized)}"
            data-display-name="${escHtml(data.display_name || data.person_key || 'profile')}"
            ${state.rolodexActionBusy ? 'disabled' : ''}
          >
            MERGE PROFILE
          </button>
        `;

    const summaryHtml = `
      <div class="rolodex-summary">
        <div class="rolodex-summary-title">${escHtml(data.display_name || data.person_key || 'Unknown')}</div>
        <div class="rolodex-summary-key">${escHtml(data.person_key || '')}</div>
        <div class="rolodex-summary-chips">
          <span class="rolodex-chip interactable ${isArchived ? 'low' : (isLocked ? 'locked' : band.tone)}" data-role="history-trigger" data-type="profile" title="Click to view profile metrics">${isArchived ? 'ARCHIVED PROFILE' : (isLocked ? 'LOCKED PROFILE' : `${band.label} CONFIDENCE (${Math.round(confidence * 100)}%)`)}</span>
          ${isLocked ? `<span class="rolodex-chip interactable ${band.tone}" data-role="history-trigger" data-type="profile" title="Click to view profile metrics">${band.label} CONFIDENCE (${Math.round(confidence * 100)}%)</span>` : ''}
          ${isArchived ? `<span class="rolodex-chip low" title="Profile archived timestamp">archived ${escHtml(formatRolodexRelativeTime(archivedAt))}</span>` : ''}
          ${isLocked && data.locked_at ? `<span class="rolodex-chip interactable" data-role="history-trigger" data-type="profile" title="Click to view lock metadata">locked: ${escHtml(formatRolodexRelativeTime(data.locked_at))}</span>` : ''}
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="chat" title="Click to view interaction history">chat ${Number(data.interaction_count || 0)}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="mentions" title="Click to view mention snippets">mentions ${Number(data.mention_count || 0)}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="facts" title="Click to view reinforced facts as a list">facts ${facts.length}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="profile" title="Linked people entities">people ${assocPeople}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="profile" title="Linked place entities">places ${assocPlaces}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="profile" title="Linked thing entities">things ${assocThings}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="profile" title="Linked idea entities">ideas ${assocIdeas}</span>
          <span class="rolodex-chip interactable" data-role="history-trigger" data-type="seen" title="Click to view activity timeline">seen ${escHtml(formatRolodexRelativeTime(data.last_seen))}</span>
        </div>
        <div class="rolodex-contact-row">
          <label class="rolodex-contact-label" for="rolodex-contact-handle-input">CONTACT HANDLE</label>
          <div class="rolodex-contact-controls">
            <input
              type="text"
              id="rolodex-contact-handle-input"
              class="rolodex-contact-input"
              value="${escHtml(String(data.contact_handle || ''))}"
              placeholder="+12145551212 or email"
              autocomplete="off"
              spellcheck="false"
              ${isArchived ? 'disabled' : ''}
            >
            <button
              class="modal-btn rolodex-action-btn"
              data-role="rolodex-handle-save"
              data-person-key="${escHtml(personKeyNormalized)}"
              ${(state.rolodexActionBusy || isArchived) ? 'disabled' : ''}
            >
              SAVE HANDLE
            </button>
          </div>
          <div class="rolodex-contact-status" id="rolodex-contact-handle-status">
            ${isArchived ? 'Status: Archived (restore required for edits)' : (data.contact_handle ? 'Status: Bound' : 'Status: Unbound')}
          </div>
        </div>
        <div class="rolodex-contact-row">
          <label class="rolodex-contact-label" for="rolodex-object-build-input">BUILD OBJECT</label>
          <div class="rolodex-contact-controls">
            <input
              type="text"
              id="rolodex-object-build-input"
              class="rolodex-contact-input"
              value=""
              placeholder="camera rig, test bench, semantic index..."
              autocomplete="off"
              spellcheck="false"
              ${isArchived ? 'disabled' : ''}
            >
            <button
              class="modal-btn rolodex-action-btn"
              data-role="rolodex-object-build"
              data-person-key="${escHtml(personKeyNormalized)}"
              ${(state.rolodexActionBusy || isArchived) ? 'disabled' : ''}
            >
              BUILD OBJECT
            </button>
          </div>
          <div class="rolodex-contact-status" id="rolodex-object-build-status">
            ${isArchived ? 'Status: Archived (restore required for edits)' : 'Status: Ready'}
          </div>
        </div>
        <div id="rolodex-drilldown-anchor"></div>
        <div class="rolodex-actions">${actionsHtml}</div>
        ${isArchived ? '<div class="audit-subtext">Archived profiles are read-only until restored.</div>' : ''}
      </div>
    `;

    const factsHtml = facts.length
      ? facts.map((fact) => {
        const fConf = Math.max(0, Math.min(1, Number(fact.confidence || 0)));
        const fPct = Math.round(fConf * 100);
        const factArchived = isRolodexArchivedTimestamp(fact.invalidated_at);
        const evidence = String(fact.evidence_text || '').trim();
        const clipped = evidence.length > 220 ? `${evidence.slice(0, 220)}...` : evidence;
        return `
          <div class="rolodex-fact interactable" 
               data-fact-type="${escHtml(fact.fact_type)}" 
               data-fact-value="${escHtml(fact.fact_value)}"
               title="Click to view full evidence and metadata">
            <div class="rolodex-fact-head">
              <span class="rolodex-fact-type">${escHtml(String(fact.fact_type || 'fact').replace(/_/g, ' '))}</span>
              <span class="rolodex-fact-conf">${fPct}%</span>
            </div>
            <div class="rolodex-fact-value">${escHtml(fact.fact_value || '')}</div>
            <div class="rolodex-fact-meta">
              <span>source: ${escHtml(fact.source_role || 'unknown')}</span>
              <span>${factArchived ? 'archived' : 'observed'}: ${escHtml(formatRolodexRelativeTime(factArchived ? fact.invalidated_at : fact.last_observed_at))}</span>
              <span>count: ${Number(fact.observation_count || 0)}</span>
            </div>
            ${clipped ? `<div class="rolodex-fact-evidence">"${escHtml(clipped)}"</div>` : ''}
          </div>
        `;
      }).join('')
      : '<div class="dim">No reinforced facts stored for this individual yet.</div>';

    dom.rolodexDetail.innerHTML = `
      ${telemetryHtml}
      ${summaryHtml}
      <div class="rolodex-facts-block">
        <div class="rolodex-section-title">REINFORCED FACTS</div>
        <div class="rolodex-facts-list">${factsHtml}</div>
      </div>
      <div class="rolodex-facts-block">
        <div class="rolodex-section-title">STRUCTURED RELATIONSHIPS</div>
        <div class="rolodex-history-list">
          ${relationships.length ? relationships.slice(0, 14).map((rel) => `
            <div class="rolodex-history-item">
              <div class="rolodex-history-time">${escHtml(String(rel.direction || 'linked').toUpperCase())} · ${escHtml(String(rel.type || rel.relationship_type || 'relation').replaceAll('_', ' '))}</div>
              <div class="rolodex-history-content">${escHtml(String(rel.counterparty_label || rel.counterparty_key || 'unknown'))}</div>
            </div>
          `).join('') : '<div class="dim">No first-class relationships recorded.</div>'}
        </div>
      </div>
      <div class="rolodex-facts-block">
        <div class="rolodex-section-title">ALIAS + MERGE HISTORY</div>
        <div class="rolodex-history-list">
          ${aliases.length ? aliases.slice(0, 12).map((alias) => `
            <div class="rolodex-history-item">
              <div class="rolodex-history-time">${escHtml(String(alias.source || 'atlas').toUpperCase())} · ${Math.round(Number(alias.confidence || 0) * 100)}%</div>
              <div class="rolodex-history-content">${escHtml(String(alias.alias_display_name || alias.alias_key || 'alias'))} → ${escHtml(String(alias.canonical_key || personKeyNormalized))}</div>
            </div>
          `).join('') : '<div class="dim">No alias lineage recorded.</div>'}
        </div>
      </div>
      <div class="rolodex-notes-section">
        <div class="rolodex-notes-label">// OPERATOR_NOTES</div>
        <textarea class="rolodex-notes-area" id="rolodex-notes-input" placeholder="Add manual context or notes for this individual..." ${isArchived ? 'disabled' : ''}>${escHtml(data.notes || '')}</textarea>
        <div class="rolodex-notes-status" id="rolodex-notes-status">${isArchived ? 'Status: Archived profiles are read-only' : 'Status: Static'}</div>
      </div>
    `;

    const lockBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-lock-toggle"]');
    if (lockBtn) {
      lockBtn.addEventListener('click', () => {
        const key = lockBtn.getAttribute('data-person-key') || '';
        const nextLock = lockBtn.getAttribute('data-next-lock') === '1';
        void setRolodexPersonLock(key, nextLock);
      });
    }
    const deleteBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-delete"]');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', () => {
        const key = deleteBtn.getAttribute('data-person-key') || '';
        const name = deleteBtn.getAttribute('data-display-name') || '';
        void deleteRolodexPerson(key, name);
      });
    }
    const mergeBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-merge"]');
    if (mergeBtn) {
      mergeBtn.addEventListener('click', () => {
        const key = mergeBtn.getAttribute('data-person-key') || '';
        const name = mergeBtn.getAttribute('data-display-name') || '';
        void mergeRolodexPerson(key, name);
      });
    }
    const restoreBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-restore"]');
    if (restoreBtn) {
      restoreBtn.addEventListener('click', () => {
        const key = restoreBtn.getAttribute('data-person-key') || '';
        const name = restoreBtn.getAttribute('data-display-name') || '';
        void restoreRolodexPerson(key, name);
      });
    }
    const handleSaveBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-handle-save"]');
    if (handleSaveBtn && !isArchived) {
      handleSaveBtn.addEventListener('click', async () => {
        const key = handleSaveBtn.getAttribute('data-person-key') || '';
        const input = document.getElementById('rolodex-contact-handle-input');
        const statusEl = document.getElementById('rolodex-contact-handle-status');
        if (!key || !(input instanceof HTMLInputElement)) return;
        if (statusEl) statusEl.textContent = 'Status: Saving...';
        const result = await saveRolodexContactHandle(key, input.value);
        if (statusEl) {
          if (result.status === 'shadow_route') {
            statusEl.textContent = 'Status: Shadow route (not applied)';
          } else if (result.ok) {
            statusEl.textContent = result.contact_handle ? 'Status: Bound' : 'Status: Unbound';
          } else {
            statusEl.textContent = 'Status: Save failed';
          }
        }
      });
    }
    const objectBuildBtn = dom.rolodexDetail.querySelector('[data-role="rolodex-object-build"]');
    if (objectBuildBtn && !isArchived) {
      objectBuildBtn.addEventListener('click', async () => {
        const key = objectBuildBtn.getAttribute('data-person-key') || '';
        const input = document.getElementById('rolodex-object-build-input');
        const statusEl = document.getElementById('rolodex-object-build-status');
        if (!(input instanceof HTMLInputElement)) return;
        if (statusEl) statusEl.textContent = 'Status: Building...';
        const result = await buildRolodexObject(key, input.value);
        if (result.ok) {
          input.value = '';
          if (statusEl) statusEl.textContent = `Status: Built ${result.thing_key || 'object'}`;
        } else if (statusEl) {
          statusEl.textContent = result.status === 'shadow_route' ? 'Status: Shadow route (not applied)' : 'Status: Build failed';
        }
      });
    }

    dom.rolodexDetail.querySelectorAll('[data-role="history-trigger"]').forEach(el => {
      el.addEventListener('click', () => {
        const type = el.getAttribute('data-type');
        void showRolodexHistory(type, personKeyNormalized, facts, data);
      });
    });

    dom.rolodexDetail.querySelectorAll('.rolodex-fact.interactable').forEach(el => {
      el.addEventListener('click', () => {
        const type = el.getAttribute('data-fact-type');
        const val = el.getAttribute('data-fact-value');
        const fact = facts.find(f => f.fact_type === type && f.fact_value === val);
        if (fact) showFactDrilldown(fact);
      });
    });

    let saveTimeout = null;
    const notesInput = document.getElementById('rolodex-notes-input');
    const notesStatus = document.getElementById('rolodex-notes-status');
    if (!isArchived && notesInput && notesStatus) {
      notesInput.addEventListener('input', () => {
        notesStatus.textContent = 'Status: Changes pending...';
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(async () => {
          notesStatus.textContent = 'Status: Saving...';
          const result = await saveRolodexNotes(personKeyNormalized, notesInput.value);
          if (result.status === 'shadow_route') {
            notesStatus.textContent = 'Status: Shadow route (not applied)';
          } else {
            notesStatus.textContent = result.ok ? 'Status: Saved' : 'Status: Save failed';
          }
        }, 800);
      });
    }
  } catch (err) {
    const msg = String(err?.message || err || 'load failed');
    dom.rolodexDetail.innerHTML = `<div class="warn-text">Failed to load profile: ${escHtml(msg)}</div>`;
    notify('error', 'Failed to load selected rolodex profile.');
  }
}

async function saveRolodexNotes(personKey, notes) {
  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes }),
    });
    const data = await readRolodexResponse(res);
    if (data?.status === 'shadow_route') {
      return { ok: false, status: 'shadow_route' };
    }
    return { ok: true, status: String(data?.status || 'updated') };
  } catch (err) {
    console.error('Failed to save notes:', err);
    return { ok: false, status: 'error', error: String(err?.message || err || 'save failed') };
  }
}

async function saveRolodexContactHandle(personKey, contactHandleRaw) {
  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}/contact-handle`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contact_handle: contactHandleRaw }),
    });
    const data = await readRolodexResponse(res);
    if (data?.status === 'shadow_route') {
      notify('warning', 'Contact handle update shadow-routed and not applied.');
      return { ok: false, status: 'shadow_route' };
    }
    const person = data?.person;
    if (person && person.person_key) {
      updateRolodexEntryInState(person);
      renderRolodexList();
      await loadRolodexDetails(person.person_key, { includeArchived: state.rolodexIncludeArchived });
      notify('success', person.contact_handle ? 'Contact handle saved.' : 'Contact handle cleared.');
      return { ok: true, status: 'updated', contact_handle: String(person.contact_handle || '') };
    }
    notify('warning', 'Contact handle response had no person payload.');
    return { ok: false, status: 'invalid_response' };
  } catch (err) {
    const msg = String(err?.message || err || 'save failed');
    notify('error', `Failed to save contact handle: ${msg}`);
    return { ok: false, status: 'error', error: msg };
  }
}

async function buildRolodexObject(personKey, objectNameRaw) {
  const objectName = String(objectNameRaw || '').trim();
  if (!objectName) {
    notify('warning', 'Object name is required.');
    return { ok: false, status: 'invalid_input' };
  }
  try {
    const res = await fetch(`${API_BASE}/ghost/rolodex/objects/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        person_key: personKey,
        object_name: objectName,
        confidence: 0.7,
        notes: '',
        metadata: { via: 'rolodex_ui' },
      }),
    });
    const data = await readRolodexResponse(res);
    if (data?.status === 'shadow_route') {
      notify('warning', 'Object build shadow-routed and not applied.');
      return { ok: false, status: 'shadow_route' };
    }
    await loadRolodexList();
    if (personKey) {
      await loadRolodexDetails(personKey, { includeArchived: state.rolodexIncludeArchived });
    }
    notify('success', `Object created: ${objectName}`);
    return {
      ok: true,
      status: 'ok',
      thing_key: String(data?.thing_key || ''),
      association_ok: Boolean(data?.association_ok),
    };
  } catch (err) {
    const msg = String(err?.message || err || 'object build failed');
    notify('error', `Failed to build object: ${msg}`);
    return { ok: false, status: 'error', error: msg };
  }
}

async function showRolodexHistory(type, personKey, facts = [], personData = null) {
  const anchor = document.getElementById('rolodex-drilldown-anchor');
  if (!anchor) return;
  const mode = String(type || 'history').toLowerCase();
  const title = mode.replaceAll('_', ' ').toUpperCase();
  const fmtTs = (raw) => {
    const n = Number(raw || 0);
    if (!Number.isFinite(n) || n <= 0) return 'n/a';
    return new Date(n * 1000).toLocaleString();
  };

  anchor.innerHTML = `
    <div class="rolodex-drilldown">
      <div class="rolodex-drilldown-header">
        <span class="rolodex-drilldown-title">${escHtml(title)} HISTORY</span>
        <button class="rolodex-drilldown-close" onclick="this.parentElement.parentElement.remove()">×</button>
      </div>
      <div class="rolodex-history-list">
        <div class="dim">Loading history records...</div>
      </div>
    </div>
  `;

  if (mode === 'facts') {
    const list = anchor.querySelector('.rolodex-history-list');
    const rows = Array.isArray(facts) ? facts : [];
    if (!list) return;
    if (!rows.length) {
      list.innerHTML = '<div class="dim">No reinforced facts stored for this profile.</div>';
      return;
    }
    list.innerHTML = rows.slice(0, 80).map((fact) => {
      const confidence = Math.round(Number(fact?.confidence || 0) * 100);
      const observed = fmtTs(fact?.last_observed_at);
      const fType = String(fact?.fact_type || 'fact').replaceAll('_', ' ');
      const value = String(fact?.fact_value || '');
      const count = Number(fact?.observation_count || 0);
      return `
        <div class="rolodex-history-item">
          <div class="rolodex-history-time">${escHtml(fType.toUpperCase())} • ${confidence}% • seen ${escHtml(observed)}</div>
          <div class="rolodex-history-content">${escHtml(value)} (count: ${count})</div>
        </div>
      `;
    }).join('');
    return;
  }

  if (mode === 'profile') {
    const list = anchor.querySelector('.rolodex-history-list');
    const profile = personData && typeof personData === 'object' ? personData : {};
    const confidence = Math.round(Number(profile?.confidence || 0) * 100);
    const firstSeen = fmtTs(profile?.first_seen);
    const lastSeen = fmtTs(profile?.last_seen);
    const locked = Boolean(profile?.is_locked);
    const lockedAt = fmtTs(profile?.locked_at);
    const interactions = Number(profile?.interaction_count || 0);
    const mentions = Number(profile?.mention_count || 0);
    const factCount = Array.isArray(facts) ? facts.length : Number(profile?.fact_count || 0);
    const notesRaw = String(profile?.notes || '').trim();
    const notes = notesRaw ? notesRaw : 'No operator notes recorded.';
    if (!list) return;
    list.innerHTML = `
      <div class="rolodex-history-item">
        <div class="rolodex-history-time">IDENTITY SNAPSHOT</div>
        <div class="rolodex-history-content">
          key: ${escHtml(String(profile?.person_key || personKey || 'unknown'))}<br>
          display: ${escHtml(String(profile?.display_name || 'Unknown'))}<br>
          confidence: ${confidence}%<br>
          state: ${locked ? 'LOCKED' : 'UNLOCKED'}${locked ? ` (since ${escHtml(lockedAt)})` : ''}
        </div>
      </div>
      <div class="rolodex-history-item">
        <div class="rolodex-history-time">ACTIVITY SNAPSHOT</div>
        <div class="rolodex-history-content">
          interactions: ${interactions}<br>
          mentions: ${mentions}<br>
          reinforced facts: ${factCount}<br>
          first seen: ${escHtml(firstSeen)}<br>
          last seen: ${escHtml(lastSeen)}
        </div>
      </div>
      <div class="rolodex-history-item">
        <div class="rolodex-history-time">OPERATOR NOTES</div>
        <div class="rolodex-history-content">${escHtml(notes)}</div>
      </div>
    `;
    return;
  }

  try {
    const qp = encodeURIComponent(String(personKey));
    const res = await fetch(`${API_BASE}/ghost/rolodex/${qp}/history?limit=40`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const list = anchor.querySelector('.rolodex-history-list');
    if (!list) return;

    if (mode === 'chat' || mode === 'seen') {
      const rows = data.sessions || [];
      if (!rows.length) {
        list.innerHTML = '<div class="dim">No session records found.</div>';
      } else {
        list.innerHTML = rows.map(s => `
          <div class="rolodex-history-item">
            <div class="rolodex-history-time">
              ${escHtml(fmtTs(s.started_at))} · ${s.ended_at ? `closed ${escHtml(fmtTs(s.ended_at))}` : 'active'}
            </div>
            <div class="rolodex-history-content">${escHtml(s.summary || 'Interaction session')}</div>
            <div class="session-row-actions">
              <button
                class="modal-btn rolodex-history-resume-btn"
                data-session-id="${escHtml(String(s.session_id || ''))}"
                ${s.ended_at ? '' : 'disabled'}
              >RESUME</button>
            </div>
          </div>
        `).join('');
        list.querySelectorAll('.rolodex-history-resume-btn[data-session-id]').forEach((btn) => {
          btn.addEventListener('click', async () => {
            const sid = btn.getAttribute('data-session-id') || '';
            if (!sid) return;
            btn.setAttribute('disabled', 'true');
            await resumeConversationSession(sid, { closeRolodexDrilldown: true });
          });
        });
      }
    } else if (mode === 'mentions') {
      const rows = data.mentions || [];
      if (!rows.length) {
        list.innerHTML = '<div class="dim">No mention records found.</div>';
      } else {
        list.innerHTML = rows.map(m => `
          <div class="rolodex-history-item">
            <div class="rolodex-history-time">${escHtml(fmtTs(m.timestamp))} [${escHtml(m.type || 'memory')}]</div>
            <div class="rolodex-history-content">"${escHtml(m.content)}"</div>
          </div>
        `).join('');
      }
    } else {
      list.innerHTML = '<div class="dim">No drilldown renderer available for this data type.</div>';
    }
  } catch (err) {
    const msg = String(err?.message || err || 'history unavailable');
    anchor.innerHTML = `
      <div class="rolodex-drilldown">
        <div class="rolodex-drilldown-header">
          <span class="rolodex-drilldown-title">${escHtml(title)} HISTORY</span>
          <button class="rolodex-drilldown-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
        <div class="rolodex-history-list">
          <div class="rolodex-history-item">
            <div class="rolodex-history-time">ERROR</div>
            <div class="rolodex-history-content">Failed to load history: ${escHtml(msg)}</div>
          </div>
        </div>
      </div>
    `;
  }
}

function showFactDrilldown(fact) {
  const anchor = document.getElementById('rolodex-drilldown-anchor');
  if (!anchor) return;

  const firstObs = fact.first_observed_at ? new Date(fact.first_observed_at * 1000).toLocaleString() : 'n/a';
  const lastObs = fact.last_observed_at ? new Date(fact.last_observed_at * 1000).toLocaleString() : 'n/a';

  anchor.innerHTML = `
    <div class="rolodex-drilldown">
      <div class="rolodex-drilldown-header">
        <span class="rolodex-drilldown-title">FACT_EVIDENCE: ${escHtml(fact.fact_type.toUpperCase())}</span>
        <button class="rolodex-drilldown-close" onclick="this.parentElement.parentElement.remove()">×</button>
      </div>
      <div class="rolodex-history-list">
        <div class="rolodex-history-item">
          <div class="rolodex-history-time">PROVENANCE & INTEGRITY</div>
          <div class="rolodex-history-content">
            First seen: ${escHtml(firstObs)}<br>
            Last seen: ${escHtml(lastObs)}<br>
            Observations: ${fact.observation_count}<br>
            Trust Level: ${Math.round(fact.confidence * 100)}%
          </div>
        </div>
        <div class="rolodex-history-item">
          <div class="rolodex-history-time">REINFORCING EVIDENCE</div>
          <div class="rolodex-history-content" style="white-space: pre-wrap; font-style: italic;">"${escHtml(fact.evidence_text || 'No literal snippet stored.')}"</div>
        </div>
      </div>
    </div>
  `;
}

function stopRolodexPolling() {
  if (state.rolodexPollTimer) {
    clearInterval(state.rolodexPollTimer);
    state.rolodexPollTimer = null;
  }
}

function startRolodexPolling() {
  stopRolodexPolling();
  state.rolodexPollTimer = setInterval(() => {
    if (!dom.rolodexModal || !dom.rolodexModal.classList.contains('active')) return;
    if (state.rolodexPollBusy) return;
    void loadRolodexList();
  }, 3200);
}

async function openRolodexModal(opts = {}) {
  if (!dom.rolodexModal) return;
  closeTopologyModal();
  const graphFocus = Boolean(opts?.graphFocus);
  dom.rolodexModal.classList.add('active');
  syncRolodexTabSelection();
  syncRolodexArchiveToggle();
  if (dom.rolodexSearch) {
    dom.rolodexSearch.value = '';
    state.rolodexFilter = '';
    if (!graphFocus) {
      setTimeout(() => dom.rolodexSearch && dom.rolodexSearch.focus(), 20);
    }
  }
  await loadRolodexList();
  await loadRolodexDiagnostics();
  if (state.rolodexSelectedKey) {
    await loadRolodexDetails(state.rolodexSelectedKey, { includeArchived: state.rolodexIncludeArchived });
  } else if (dom.rolodexDetail) {
    dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">Select an entity to view relational details.</div>`;
  }
  startRolodexPolling();
}

function closeRolodexModal() {
  if (!dom.rolodexModal) return;
  dom.rolodexModal.classList.remove('active');
  stopRolodexPolling();
}

function bindRolodexEvents() {
  document.querySelectorAll('.rolodex-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.rolodex-tab').forEach(t => t.classList.remove('active'));
      const target = e.target.closest('.rolodex-tab');
      if (target) {
        target.classList.add('active');
        state.rolodexActiveTab = target.getAttribute('data-tab') || 'persons';
      }
      state.rolodexSelectedKey = '';
      if (dom.rolodexSearch) dom.rolodexSearch.value = '';
      state.rolodexFilter = '';
      
      if (state.rolodexWorld) {
        state.rolodexEntries = Array.isArray(state.rolodexWorld[state.rolodexActiveTab]) 
            ? state.rolodexWorld[state.rolodexActiveTab] 
            : [];
      }
      
      renderRolodexList();
      if (dom.rolodexDetail) {
         dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">Select an entity to view details.</div>`;
      }
    });
  });

  if (dom.rolodexBtn) {
    dom.rolodexBtn.addEventListener('click', () => {
      void openRolodexModal();
    });
  }
  if (dom.rolodexClose) {
    dom.rolodexClose.addEventListener('click', closeRolodexModal);
  }
  if (dom.rolodexModal) {
    dom.rolodexModal.addEventListener('click', (e) => {
      if (e.target === dom.rolodexModal) closeRolodexModal();
    });
  }
  if (dom.rolodexSearch) {
    dom.rolodexSearch.addEventListener('input', () => {
      state.rolodexFilter = dom.rolodexSearch.value || '';
      renderRolodexList();
      const filter = String(state.rolodexFilter || '').trim().toLowerCase();
      const filtered = (state.rolodexEntries || []).filter((row) => {
        if (!filter) return true;
        const name = String(row.display_name || row.concept_text || '').toLowerCase();
        const key = String(row.person_key || row.place_key || row.thing_key || row.concept_key || '').toLowerCase();
        const handle = String(row.contact_handle || '').toLowerCase();
        return name.includes(filter) || key.includes(filter) || handle.includes(filter);
      });
      const selectedVisible = filtered.some((row) => (row.person_key || row.place_key || row.thing_key || row.concept_key) === state.rolodexSelectedKey);
      if (!selectedVisible) {
        const firstRow = filtered[0] || {};
        state.rolodexSelectedKey = firstRow.person_key || firstRow.place_key || firstRow.thing_key || firstRow.concept_key || '';
        renderRolodexList();
        if (state.rolodexSelectedKey) {
          void loadRolodexDetails(state.rolodexSelectedKey, { includeArchived: state.rolodexIncludeArchived });
        } else if (dom.rolodexDetail) {
          dom.rolodexDetail.innerHTML = `${buildRolodexTelemetryPanel()}<div class="dim">No matching entity selected.</div>`;
        }
      }
    });
  }
  if (dom.rolodexArchiveToggle) {
    syncRolodexArchiveToggle();
    dom.rolodexArchiveToggle.addEventListener('click', () => {
      state.rolodexIncludeArchived = !state.rolodexIncludeArchived;
      syncRolodexArchiveToggle();
      void loadRolodexList();
    });
  }
}

function opsHeaders() {
  return state.opsCode ? { 'X-Ops-Code': state.opsCode } : {};
}

function isOpsChatCommand(text) {
  return /^\/ops\//i.test(String(text || '').trim());
}

async function verifyOpsCode(code) {
  const value = String(code || '').trim();
  if (!value) return false;
  const res = await fetch(`${API_BASE}/ops/verify`, {
    headers: { 'X-Ops-Code': value },
  });
  return res.ok;
}

async function ensureOpsCommandAuthorized() {
  if (state.opsCode) {
    try {
      if (await verifyOpsCode(state.opsCode)) return true;
    } catch (_) {
      // fall through to explicit prompt path
    }
  }

  const entered = window.prompt('Enter system operations code to run this command:');
  const code = String(entered || '').trim();
  if (!code) {
    notify('warning', 'Ops command canceled (no code provided).');
    return false;
  }

  try {
    const ok = await verifyOpsCode(code);
    if (!ok) {
      notify('error', 'Invalid system operations code. Command blocked.');
      return false;
    }
    state.opsCode = code;
    state.opsUnlocked = true;
    setOpsStatus('[ ACCESS GRANTED ]', 'granted');
    return true;
  } catch (_) {
    notify('error', 'Ops authorization failed.');
    return false;
  }
}

function setOpsStatus(message, mode = '') {
  if (!dom.opsAuthStatus) return;
  dom.opsAuthStatus.className = `terminal-status ${mode}`.trim();
  dom.opsAuthStatus.textContent = message || '';
}

function setOpsWindow(windowName) {
  const target = windowName === 'weekly' ? 'weekly' : 'daily';
  state.opsWindow = target;
  if (dom.opsWindowDaily) dom.opsWindowDaily.classList.toggle('active', target === 'daily');
  if (dom.opsWindowWeekly) dom.opsWindowWeekly.classList.toggle('active', target === 'weekly');
}

function setOpsMode(modeName) {
  const target = modeName === 'rpd' ? 'rpd' : 'reports';
  state.opsMode = target;
  if (dom.opsModeReports) dom.opsModeReports.classList.toggle('active', target === 'reports');
  if (dom.opsModeRpd) dom.opsModeRpd.classList.toggle('active', target === 'rpd');
  if (dom.opsReportControls) dom.opsReportControls.style.display = target === 'reports' ? 'flex' : 'none';
  if (dom.opsReportsLayout) dom.opsReportsLayout.style.display = target === 'reports' ? 'grid' : 'none';
  if (dom.opsRpdLayout) dom.opsRpdLayout.classList.toggle('active', target === 'rpd');
}

function setOpsUnlocked(unlocked) {
  const on = Boolean(unlocked);
  state.opsUnlocked = on;
  if (dom.opsAuthTerminal) {
    dom.opsAuthTerminal.classList.toggle('hidden', on);
  }
  if (dom.opsPanel) {
    dom.opsPanel.classList.toggle('active', on);
  }
  if (!on) {
    state.opsSelectedRelPath = '';
    if (dom.opsFileName) dom.opsFileName.textContent = 'No file selected.';
    if (dom.opsFileContent) dom.opsFileContent.textContent = '';
    if (dom.opsRuns) dom.opsRuns.innerHTML = '<div class="dim" style="padding:10px">Unlock to load report runs...</div>';
    if (dom.opsRpdState) dom.opsRpdState.textContent = 'No data loaded.';
    if (dom.opsRpdRuns) dom.opsRpdRuns.textContent = '';
    if (dom.opsRrdState) dom.opsRrdState.textContent = 'No data loaded.';
    if (dom.opsRrdRuns) dom.opsRrdRuns.textContent = '';
    if (dom.opsTopologyState) dom.opsTopologyState.textContent = '';
    if (dom.opsRpdResidue) dom.opsRpdResidue.textContent = '';
    if (dom.opsRpdManifold) dom.opsRpdManifold.textContent = '';
    if (dom.opsResonanceEvents) dom.opsResonanceEvents.textContent = '';
  }
}

function openOpsModal() {
  if (!dom.opsModal) return;
  state.opsCode = '';
  setOpsUnlocked(false);
  setOpsMode('reports');
  setOpsWindow('daily');
  setOpsStatus('[ ENTER CODE ]', '');
  dom.opsModal.classList.add('active');
  if (dom.opsCodeInput) {
    dom.opsCodeInput.value = '';
    dom.opsCodeInput.focus();
  }
}

function closeOpsModal() {
  if (!dom.opsModal) return;
  dom.opsModal.classList.remove('active');
}

async function opsLoadFile(relPath) {
  if (!state.opsUnlocked || !relPath) return;
  try {
    const qp = encodeURIComponent(relPath);
    const res = await fetch(`${API_BASE}/ops/file?rel_path=${qp}`, {
      headers: opsHeaders(),
    });
    if (!res.ok) {
      const raw = await res.text();
      throw new Error(raw || `HTTP ${res.status}`);
    }
    const data = await res.json();
    state.opsSelectedRelPath = relPath;
    if (dom.opsFileName) {
      const suffix = data.truncated ? ' [TRUNCATED]' : '';
      dom.opsFileName.textContent = `${data.rel_path} (${data.size_bytes} bytes)${suffix}`;
    }
    if (dom.opsFileContent) dom.opsFileContent.textContent = data.content || '';
  } catch (err) {
    if (dom.opsFileName) dom.opsFileName.textContent = 'Failed to load file.';
    if (dom.opsFileContent) dom.opsFileContent.textContent = String(err?.message || err || 'Unknown error');
    notify('error', 'Failed to load ops artifact file.');
  }
}

function opsRenderRuns(runs) {
  if (!dom.opsRuns) return;
  if (!Array.isArray(runs) || runs.length === 0) {
    dom.opsRuns.innerHTML = '<div class="dim" style="padding:10px">No runs found for this window.</div>';
    if (dom.opsFileName) dom.opsFileName.textContent = 'No file selected.';
    if (dom.opsFileContent) dom.opsFileContent.textContent = '';
    return;
  }

  const rows = runs.map((run, idx) => {
    const files = Array.isArray(run.files) ? run.files : [];
    const preferred = files.includes('summary.txt') ? 'summary.txt' : (files[0] || '');
    const relPath = preferred ? `${run.rel_run_path}/${preferred}` : '';
    const active = relPath && relPath === state.opsSelectedRelPath;
    const safeLabel = escHtml(`${run.day}/${run.run}`);
    const safeFiles = escHtml(files.join(', '));
    return `
      <div class="ops-run ${active ? 'active' : ''}" data-rel-path="${escHtml(relPath)}">
        <div class="ops-run-head">
          <span class="ops-run-label">${safeLabel}</span>
          <span class="ops-run-time">${escHtml(run.window || state.opsWindow)}</span>
        </div>
        <div class="ops-run-files">${safeFiles || 'no files'}</div>
      </div>
    `;
  }).join('');

  dom.opsRuns.innerHTML = rows;
  dom.opsRuns.querySelectorAll('.ops-run').forEach((row) => {
    row.addEventListener('click', async () => {
      const relPath = row.getAttribute('data-rel-path') || '';
      if (!relPath) return;
      dom.opsRuns.querySelectorAll('.ops-run').forEach((el) => el.classList.remove('active'));
      row.classList.add('active');
      await opsLoadFile(relPath);
    });
  });

  const preferred = runs.find((r) => Array.isArray(r.files) && r.files.includes('summary.txt'));
  const fallback = runs[0];
  const loadRun = preferred || fallback;
  if (loadRun) {
    const files = Array.isArray(loadRun.files) ? loadRun.files : [];
    const initialName = files.includes('summary.txt') ? 'summary.txt' : (files[0] || '');
    const relPath = initialName ? `${loadRun.rel_run_path}/${initialName}` : '';
    if (relPath) {
      opsLoadFile(relPath);
    }
  }
}

function formatJsonPretty(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (e) {
    return String(value ?? '');
  }
}

function opsRenderRpdRuns(runs) {
  if (!dom.opsRpdRuns) return;
  if (!Array.isArray(runs) || runs.length === 0) {
    dom.opsRpdRuns.textContent = 'No RPD runs recorded yet.';
    return;
  }
  const lines = runs.slice(0, 20).map((row, idx) => {
    const ts = row.created_at ? new Date(row.created_at).toLocaleString() : 'n/a';
    return [
      `#${idx + 1} ${row.source} :: ${row.candidate_type}/${row.candidate_key}`,
      `decision=${row.decision} clarity=${Number(row.shared_clarity_score || 0).toFixed(3)} warp=${Number(row.topology_warp_delta || 0).toFixed(3)}`,
      `degradation=[${Array.isArray(row.degradation_list) ? row.degradation_list.join(', ') : ''}]`,
      `${ts}`,
      '',
    ].join('\\n');
  });
  dom.opsRpdRuns.textContent = lines.join('\\n');
}

function opsRenderRpdResidue(items) {
  if (!dom.opsRpdResidue) return;
  if (!Array.isArray(items) || items.length === 0) {
    dom.opsRpdResidue.textContent = 'Residue queue is empty.';
    return;
  }
  dom.opsRpdResidue.textContent = items.map((item, idx) => {
    const text = String(item.residue_text || '').replace(/\\s+/g, ' ').slice(0, 220);
    return [
      `#${idx + 1} [${item.status}] ${item.candidate_type}/${item.candidate_key} | revisits=${item.revisit_count}`,
      `${text}${text.length >= 220 ? '…' : ''}`,
      '',
    ].join('\\n');
  }).join('\\n');
}

function opsRenderRpdManifold(entries) {
  if (!dom.opsRpdManifold) return;
  if (!Array.isArray(entries) || entries.length === 0) {
    dom.opsRpdManifold.textContent = 'Shared conceptual manifold is empty.';
    return;
  }
  dom.opsRpdManifold.textContent = entries.slice(0, 30).map((entry, idx) => {
    const text = String(entry.concept_text || '').replace(/\\s+/g, ' ').slice(0, 220);
    return [
      `#${idx + 1} [${entry.status}] ${entry.concept_key} | conf=${Number(entry.confidence || 0).toFixed(2)} rpd=${Number(entry.rpd_score || 0).toFixed(2)}`,
      `${text}${text.length >= 220 ? '…' : ''}`,
      '',
    ].join('\\n');
  }).join('\\n');
}

function opsRenderRrdRuns(runs) {
  if (!dom.opsRrdRuns) return;
  if (!Array.isArray(runs) || runs.length === 0) {
    dom.opsRrdRuns.textContent = 'No RRD topology runs recorded yet.';
    return;
  }
  dom.opsRrdRuns.textContent = runs.slice(0, 30).map((row, idx) => {
    const ts = row.created_at ? new Date(row.created_at).toLocaleString() : 'n/a';
    const reasons = Array.isArray(row.reasons) ? row.reasons.join(', ') : '';
    const dampReason = String(row.damping_reason || '');
    return [
      `#${idx + 1} ${row.source} :: ${row.candidate_type}/${row.candidate_key}`,
      `decision=${row.decision} phase=${row.rollout_phase} would_block=${Boolean(row.would_block)} enforce_block=${Boolean(row.enforce_block)}`,
      `delta=${Number(row.rrd2_delta || 0).toFixed(3)} cohesion=${Number(row.structural_cohesion || 0).toFixed(3)} neg=${Number(row.negative_resonance || 0).toFixed(3)} warp=${Number(row.topology_warp_delta || 0).toFixed(3)}`,
      `eval_ms=${Number(row.eval_ms || 0).toFixed(2)} batch=${Number(row.candidate_batch_index || 0)}/${Number(row.candidate_batch_size || 0)} qdepth=${Number(row.queue_depth_snapshot || 0)}`,
      `damping=${Boolean(row.damping_applied)}${dampReason ? ` (${dampReason})` : ''}`,
      `reasons=[${reasons}]`,
      `${ts}`,
      '',
    ].join('\\n');
  }).join('\\n');
}

function opsRenderTopologyState(rows) {
  if (!dom.opsTopologyState) return;
  if (!Array.isArray(rows) || rows.length === 0) {
    dom.opsTopologyState.textContent = 'Topology state is empty.';
    return;
  }
  dom.opsTopologyState.textContent = rows.slice(0, 40).map((row, idx) => {
    return [
      `#${idx + 1} ${row.identity_key}`,
      `stability=${Number(row.stability || 0).toFixed(3)} plasticity=${Number(row.plasticity || 0).toFixed(3)} friction=${Number(row.friction_load || 0).toFixed(3)} align=${Number(row.resonance_alignment || 0).toFixed(3)}`,
      `last_delta=${Number(row.last_rrd2_delta || 0).toFixed(3)} decision=${row.last_decision} source=${row.last_source}`,
      `${row.updated_at || 'n/a'}`,
      '',
    ].join('\\n');
  }).join('\\n');
}

function opsRenderResonanceEvents(events) {
  if (!dom.opsResonanceEvents) return;
  if (!Array.isArray(events) || events.length === 0) {
    dom.opsResonanceEvents.textContent = 'No resonance events logged yet.';
    return;
  }
  dom.opsResonanceEvents.textContent = events.slice(0, 30).map((event, idx) => {
    const sig = event.resonance_signature || {};
    const topAxes = Array.isArray(sig.top_axes)
      ? sig.top_axes.map((x) => `${x.axis}:${Number(x.value || 0).toFixed(2)}`).join(', ')
      : '';
    return [
      `#${idx + 1} ${event.event_source} :: ${event.created_at || 'n/a'}`,
      `dominant=${topAxes || 'n/a'}`,
      '',
    ].join('\\n');
  }).join('\\n');
}

async function opsRefreshRpd() {
  if (!state.opsUnlocked) {
    setOpsStatus('[ ENTER CODE ]', 'denied');
    return;
  }
  try {
    if (dom.opsRpdState) dom.opsRpdState.textContent = 'Loading RPD state...';
    if (dom.opsRpdRuns) dom.opsRpdRuns.textContent = 'Loading RPD runs...';
    if (dom.opsRrdState) dom.opsRrdState.textContent = 'Loading RRD state...';
    if (dom.opsRrdRuns) dom.opsRrdRuns.textContent = 'Loading RRD topology runs...';
    if (dom.opsTopologyState) dom.opsTopologyState.textContent = 'Loading topology state...';
    if (dom.opsRpdResidue) dom.opsRpdResidue.textContent = 'Loading residue...';
    if (dom.opsRpdManifold) dom.opsRpdManifold.textContent = 'Loading manifold...';
    if (dom.opsResonanceEvents) dom.opsResonanceEvents.textContent = 'Loading resonance events...';

    const [stateRes, runsRes, rrdStateRes, rrdRunsRes, manifoldRes] = await Promise.all([
      fetch(`${API_BASE}/ghost/rpd/state`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/rpd/runs?limit=30`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/rrd/state`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/rrd/runs?limit=40`, { headers: opsHeaders() }),
      fetch(`${API_BASE}/ghost/manifold?limit=80`, { headers: opsHeaders() }),
    ]);

    if (!stateRes.ok) throw new Error(await stateRes.text() || `HTTP ${stateRes.status}`);
    if (!runsRes.ok) throw new Error(await runsRes.text() || `HTTP ${runsRes.status}`);
    if (!rrdStateRes.ok) throw new Error(await rrdStateRes.text() || `HTTP ${rrdStateRes.status}`);
    if (!rrdRunsRes.ok) throw new Error(await rrdRunsRes.text() || `HTTP ${rrdRunsRes.status}`);
    if (!manifoldRes.ok) throw new Error(await manifoldRes.text() || `HTTP ${manifoldRes.status}`);

    const stateData = await stateRes.json();
    const runsData = await runsRes.json();
    const rrdStateData = await rrdStateRes.json();
    const rrdRunsData = await rrdRunsRes.json();
    const manifoldData = await manifoldRes.json();

    if (dom.opsRpdState) {
      const stateSnapshot = {
        mode: stateData.mode,
        latest: stateData.latest,
        residue_counts: stateData.residue_counts,
        manifold_counts: stateData.manifold_counts,
        not_consciousness_metric: true,
      };
      dom.opsRpdState.textContent = formatJsonPretty(stateSnapshot);
    }
    if (dom.opsRrdState) {
      const rrdSnapshot = {
        rrd2: rrdStateData.rrd2,
        latest_gate: rrdStateData.latest_gate,
        rrd_performance: rrdStateData.rrd_performance,
        decision_counts: rrdStateData.decision_counts,
        block_counts: rrdStateData.block_counts,
        not_consciousness_metric: true,
      };
      dom.opsRrdState.textContent = formatJsonPretty(rrdSnapshot);
    }
    opsRenderRpdRuns(runsData.runs || []);
    opsRenderRrdRuns(rrdRunsData.runs || []);
    opsRenderTopologyState(rrdStateData.topology_state || []);
    opsRenderResonanceEvents(rrdStateData.resonance_events || []);
    opsRenderRpdResidue(stateData.residue_queue || []);
    opsRenderRpdManifold(manifoldData.entries || stateData.manifold_latest || []);
  } catch (err) {
    const msg = String(err?.message || err || 'RPD refresh failed');
    if (dom.opsRpdState) dom.opsRpdState.textContent = msg;
    if (dom.opsRpdRuns) dom.opsRpdRuns.textContent = msg;
    if (dom.opsRrdState) dom.opsRrdState.textContent = msg;
    if (dom.opsRrdRuns) dom.opsRrdRuns.textContent = msg;
    if (dom.opsTopologyState) dom.opsTopologyState.textContent = msg;
    if (dom.opsRpdResidue) dom.opsRpdResidue.textContent = msg;
    if (dom.opsRpdManifold) dom.opsRpdManifold.textContent = msg;
    if (dom.opsResonanceEvents) dom.opsResonanceEvents.textContent = msg;
    notify('error', 'Failed to load RPD/reflection data.');
  }
}

async function opsRunReflectionPass() {
  if (!state.opsUnlocked) {
    setOpsStatus('[ ENTER CODE ]', 'denied');
    return;
  }
  try {
    if (dom.opsRpdState) dom.opsRpdState.textContent = 'Running reflection pass...';
    const res = await fetch(`${API_BASE}/ghost/reflection/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...opsHeaders(),
      },
      body: JSON.stringify({ limit: 8, source: 'ops_manual_reflection' }),
    });
    if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);
    const data = await res.json();
    notify('success', `Reflection pass complete: promoted ${Number(data.promoted || 0)} concepts.`);
    await opsRefreshRpd();
  } catch (err) {
    notify('error', `Reflection pass failed: ${String(err?.message || err || 'unknown error')}`);
    await opsRefreshRpd();
  }
}

async function opsRefreshRuns() {
  if (!state.opsUnlocked) {
    setOpsStatus('[ ENTER CODE ]', 'denied');
    return;
  }
  if (!dom.opsRuns) return;
  try {
    dom.opsRuns.innerHTML = '<div class="dim" style="padding:10px">Loading runs...</div>';
    const res = await fetch(`${API_BASE}/ops/runs?window=${state.opsWindow}&limit=80`, {
      headers: opsHeaders(),
    });
    if (!res.ok) {
      const raw = await res.text();
      throw new Error(raw || `HTTP ${res.status}`);
    }
    const data = await res.json();
    opsRenderRuns(data.runs || []);
  } catch (err) {
    dom.opsRuns.innerHTML = `<div class="warn-text" style="padding:10px">${escHtml(String(err?.message || err || 'Load failed'))}</div>`;
    notify('error', 'Failed to load system ops runs.');
  }
}

function bindOpsEvents() {
  if (dom.headerLogo) {
    dom.headerLogo.addEventListener('click', openOpsModal);
  }

  if (dom.opsClose) {
    dom.opsClose.addEventListener('click', closeOpsModal);
  }
  if (dom.opsModal) {
    dom.opsModal.addEventListener('click', (e) => {
      if (e.target === dom.opsModal) closeOpsModal();
    });
  }

  const submit = async () => {
    const raw = dom.opsCodeInput ? dom.opsCodeInput.value : '';
    const code = String(raw || '').trim();
    if (!code) {
      setOpsStatus('[ ENTER CODE ]', 'denied');
      return;
    }
    try {
      setOpsStatus('[ VALIDATING... ]', '');
      const res = await fetch(`${API_BASE}/ops/verify`, {
        headers: { 'X-Ops-Code': code },
      });
      if (!res.ok) {
        setOpsUnlocked(false);
        setOpsStatus('[ ACCESS DENIED ]', 'denied');
        return;
      }
      state.opsCode = code;
      setOpsUnlocked(true);
      setOpsStatus('[ ACCESS GRANTED ]', 'granted');
      if (state.opsMode === 'rpd') await opsRefreshRpd();
      else await opsRefreshRuns();
    } catch (err) {
      setOpsUnlocked(false);
      setOpsStatus('[ AUTH ERROR ]', 'denied');
    }
  };

  if (dom.opsCodeSubmit) {
    dom.opsCodeSubmit.addEventListener('click', submit);
  }
  if (dom.opsCodeInput) {
    dom.opsCodeInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submit();
    });
  }

  if (dom.opsModeReports) {
    dom.opsModeReports.addEventListener('click', async () => {
      setOpsMode('reports');
      await opsRefreshRuns();
    });
  }
  if (dom.opsModeRpd) {
    dom.opsModeRpd.addEventListener('click', async () => {
      setOpsMode('rpd');
      await opsRefreshRpd();
    });
  }

  if (dom.opsWindowDaily) {
    dom.opsWindowDaily.addEventListener('click', async () => {
      setOpsWindow('daily');
      await opsRefreshRuns();
    });
  }
  if (dom.opsWindowWeekly) {
    dom.opsWindowWeekly.addEventListener('click', async () => {
      setOpsWindow('weekly');
      await opsRefreshRuns();
    });
  }
  if (dom.opsRefresh) {
    dom.opsRefresh.addEventListener('click', async () => {
      if (state.opsMode === 'rpd') await opsRefreshRpd();
      else await opsRefreshRuns();
    });
  }
  if (dom.opsRpdRefresh) {
    dom.opsRpdRefresh.addEventListener('click', opsRefreshRpd);
  }
  if (dom.opsReflectionRun) {
    dom.opsReflectionRun.addEventListener('click', opsRunReflectionPass);
  }
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
  else if (tab === 'iit') await loadIITTab();
  else if (tab === 'relational_memory') await loadWorldModelTab();
  else if (tab === 'observer') await loadObserverTab();
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

async function loadIITTab() {
  try {
    const res = await fetch(`${API_BASE}/ghost/iit/state`);
    if (!res.ok) throw new Error('Failed to fetch IIT state');
    const data = await res.json();
    if (data.error) {
      dom.auditBody.innerHTML = `<div class="warn-text">${escHtml(data.error)}</div>`;
      return;
    }
    const m = data.metrics || {};
    const adv = data.advisory || {};
    const compl = data.substrate_completeness_score ?? 0;
    const phi = m.phi_proxy ?? '—';
    const integ = m.integration_index ?? '—';
    const excl = m.exclusion_margin ?? '—';
    const compd = m.composition_density ?? '—';
    const backend = data.backend || 'heuristic';
    const mode = data.mode || 'advisory';
    const degList = adv.degradation_list || [];
    const deg = degList.length
      ? degList.map(d => `<div class="audit-subtext">- ${escHtml(d)}</div>`).join('')
      : '<div class="audit-subtext">None</div>';
    const complex = (m.maximal_complex && m.maximal_complex.supporting_nodes)
      ? m.maximal_complex.supporting_nodes.join(', ')
      : '—';

    dom.auditBody.innerHTML = `
      <div class="audit-entry">
        <div class="audit-meta">
          <span class="audit-time">run ${escHtml(data.run_id || '')}</span>
          <span class="audit-label tag-evolution">${escHtml(mode.toUpperCase())} · ${escHtml(backend)}</span>
          <span class="audit-label tag-action-success">not_consciousness_metric: ${String(data.not_consciousness_metric)}</span>
        </div>
        <div class="audit-text">
          <div class="audit-subtext">phi_proxy: <strong>${phi}</strong></div>
          <div class="audit-subtext">integration_index: ${integ} | exclusion_margin: ${excl} | composition_density: ${compd}</div>
          <div class="audit-subtext">substrate_completeness_score: ${compl} / 6</div>
          <div class="audit-subtext">maximal_complex: ${complex}</div>
          <div class="audit-subtext">compute_ms: ${data.compute_ms ?? '—'}</div>
          <div class="audit-subtext" style="margin-top:10px;">degradation_list:</div>
          ${deg}
        </div>
      </div>
    `;
  } catch (err) {
    console.error('IIT tab load failed', err);
    dom.auditBody.innerHTML = `<div class="warn-text">Error loading IIT advisory.</div>`;
    notify('error', 'Failed to load IIT advisory.');
  }
}

async function loadObserverTab() {
  const fmtTime = (raw) => {
    if (!raw) return '—';
    const parsed = Date.parse(String(raw));
    if (!Number.isFinite(parsed)) return String(raw);
    return new Date(parsed).toLocaleString('en-US', { hour12: false });
  };

  try {
    const res = await fetch(`${API_BASE}/ghost/observer/latest`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const report = asObject(data.report);
    const artifact = asObject(data.artifact);
    state.observerLatest = report;

    if (!Object.keys(report).length) {
      dom.auditBody.innerHTML = '<div class="dim">No observer reports generated yet.</div>';
      return;
    }

    const snapshot = asObject(report.self_model_snapshot);
    const conflicts = asArray(report.purpose_vs_usage_conflicts).slice(0, 8).map((row) => asObject(row));
    const risks = asArray(report.open_risks).slice(0, 8).map((row) => asObject(row));
    const changes = asArray(report.notable_self_initiated_changes).slice(0, 8).map((row) => asObject(row));

    const conflictRows = conflicts.length
      ? conflicts.map((row) => `
          <div class="observer-risk ${String(row.severity || '').toLowerCase() === 'high' ? 'high' : 'warn'}">
            [${escHtml(String(row.severity || 'info').toUpperCase())}] ${escHtml(String(row.code || 'conflict'))}
            <div class="audit-subtext">${escHtml(String(row.detail || ''))}</div>
          </div>
        `).join('')
      : '<div class="dim">No purpose-vs-usage conflicts in latest report.</div>';

    const riskRows = risks.length
      ? risks.map((row) => `
          <div class="observer-risk ${String(row.severity || '').toLowerCase() === 'high' ? 'high' : 'warn'}">
            [${escHtml(String(row.severity || 'info').toUpperCase())}] ${escHtml(String(row.code || 'risk'))}
            <div class="audit-subtext">${escHtml(String(row.detail || ''))}</div>
          </div>
        `).join('')
      : '<div class="dim">No open risks flagged.</div>';

    const changeRows = changes.length
      ? `<div class="operator-list">${
        changes.map((row) => `
          <div class="operator-card">
            <div class="operator-row">
              <span class="operator-dimension">${escHtml(String(row.body || 'mutation'))}/${escHtml(String(row.action || 'unknown'))}</span>
              <span class="operator-badge">${escHtml(String(row.status || 'unknown').toUpperCase())}</span>
            </div>
            <div class="operator-meta">
              <span>risk=${escHtml(String(row.risk_tier || '—'))}</span>
              <span>key=${escHtml(String(row.target_key || '—'))}</span>
              <span>${escHtml(fmtTime(row.created_at))}</span>
            </div>
          </div>
        `).join('')
      }</div>`
      : '<div class="dim">No self-initiated changes in current report window.</div>';

    dom.auditBody.innerHTML = `
      <div class="operator-model">
        <div class="operator-summary">
          <span class="operator-summary-chip">generated<strong>${escHtml(fmtTime(report.generated_at))}</strong></span>
          <span class="operator-summary-chip">window<strong>${escHtml(String(report.window_hours || '1'))}h</strong></span>
          <span class="operator-summary-chip">ghost<strong>${escHtml(String(report.ghost_id || 'omega-7'))}</strong></span>
        </div>

        <div class="operator-section">
          <div class="operator-section-title">SELF MODEL SNAPSHOT</div>
          <div class="audit-subtext">self_model updated_at: ${escHtml(fmtTime(snapshot.updated_at))}</div>
          <div class="audit-subtext">updated_by: ${escHtml(String(snapshot.updated_by || 'n/a'))}</div>
          <div class="audit-text">${escHtml(String(snapshot.self_model || 'n/a'))}</div>
        </div>

        <div class="operator-section">
          <div class="operator-section-title">TOP CONFLICTS</div>
          ${conflictRows}
        </div>

        <div class="operator-section">
          <div class="operator-section-title">OPEN RISKS</div>
          ${riskRows}
        </div>

        <div class="operator-section">
          <div class="operator-section-title">NOTABLE SELF-INITIATED CHANGES</div>
          ${changeRows}
        </div>

        <div class="operator-section">
          <div class="operator-section-title">LATEST ARTIFACT</div>
          <div class="audit-subtext">json: ${escHtml(String(artifact.json_path || 'n/a'))}</div>
          <div class="audit-subtext">markdown: ${escHtml(String(artifact.markdown_path || 'n/a'))}</div>
        </div>
      </div>
    `;
  } catch (err) {
    console.error('Observer tab load failed', err);
    dom.auditBody.innerHTML = '<div class="warn-text">Error loading observer report.</div>';
    notify('error', 'Failed to load observer report.');
  }
}

async function loadWorldModelTab() {
  const readJsonSafe = async (res, fallback) => {
    if (!res) return fallback;
    try {
      return await res.json();
    } catch (_) {
      return fallback;
    }
  };
  const fmtTs = (raw) => {
    if (raw === null || raw === undefined || raw === '') return '—';
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) {
      const ms = n > 1e12 ? n : n * 1000;
      return new Date(ms).toLocaleString('en-US', { hour12: false });
    }
    const text = String(raw || '').trim();
    if (!text) return '—';
    const parsed = Date.parse(text);
    if (!Number.isFinite(parsed)) return text;
    return new Date(parsed).toLocaleString('en-US', { hour12: false });
  };
  const shortText = (value, max = 120) => {
    const text = String(value || '').trim();
    if (!text) return '—';
    if (text.length <= max) return text;
    return `${text.slice(0, max - 1)}…`;
  };

  try {
    const [statusRes, obsRes, beliefRes, entitiesRes, ingestRes, activityRes] = await Promise.all([
      fetch(`${API_BASE}/ghost/world_model/status`),
      fetch(`${API_BASE}/ghost/world_model/nodes?label=Observation&limit=12`),
      fetch(`${API_BASE}/ghost/world_model/nodes?label=Belief&limit=12`),
      fetch(`${API_BASE}/ghost/entities/snapshot?limit=120`),
      fetch(`${API_BASE}/ghost/world_model/ingest`),
      fetch(`${API_BASE}/ghost/world_model/activity?window_hours=24&limit=80`),
    ]);

    const statusData = await readJsonSafe(statusRes, {});
    const obsData = await readJsonSafe(obsRes, {});
    const beliefData = await readJsonSafe(beliefRes, {});
    const entitiesData = await readJsonSafe(entitiesRes, {});
    const ingestData = await readJsonSafe(ingestRes, {});
    const activityData = await readJsonSafe(activityRes, {});

    const worldAvailable = Boolean(statusData.available);
    const labels = Array.isArray(statusData.labels) ? statusData.labels : [];
    const counts = (statusData && typeof statusData.counts === 'object' && statusData.counts) ? statusData.counts : {};
    const totalNodes = Number(statusData.total_nodes || 0);
    const dbPath = String(statusData.db_path || '—');
    const worldError = String(statusData.error || '');

    const obsEntries = Array.isArray(obsData.entries) ? obsData.entries : [];
    const beliefEntries = Array.isArray(beliefData.entries) ? beliefData.entries : [];

    const entityCounts = (entitiesData && typeof entitiesData.counts === 'object' && entitiesData.counts) ? entitiesData.counts : {};
    const places = Array.isArray(entitiesData.places) ? entitiesData.places : [];
    const things = Array.isArray(entitiesData.things) ? entitiesData.things : [];
    const ideas = Array.isArray(entitiesData.ideas) ? entitiesData.ideas : [];
    const associations = (entitiesData && typeof entitiesData.associations === 'object' && entitiesData.associations) ? entitiesData.associations : {};
    const personPlace = Array.isArray(associations.person_place) ? associations.person_place : [];
    const personThing = Array.isArray(associations.person_thing) ? associations.person_thing : [];
    const ideaLinks = Array.isArray(associations.idea_links) ? associations.idea_links : [];
    const ingestEntries = Array.isArray(ingestData.entries) ? ingestData.entries : [];
    const ingestEnabled = Boolean(ingestData.enabled);
    const ingestInterval = Number(ingestData.interval_seconds || 0);
    const latestIngest = ingestEntries.length ? ingestEntries[0] : null;
    const recentIngest = ingestEntries.slice(0, 6);
    const activityByBody = (activityData && typeof activityData.by_body === 'object' && activityData.by_body) ? activityData.by_body : {};
    const activityByStatus = (activityData && typeof activityData.by_status === 'object' && activityData.by_status) ? activityData.by_status : {};
    const activityRecent = Array.isArray(activityData.recent) ? activityData.recent.slice(0, 8) : [];

    const renderChips = (obj) => {
      const entries = Object.entries(obj || {});
      if (!entries.length) return '<span class="dim">No counts available.</span>';
      return entries.map(([k, v]) => `
        <span class="operator-summary-chip">${escHtml(String(k).toUpperCase())}<strong>${escHtml(String(v))}</strong></span>
      `).join('');
    };

    const renderNodeRows = (title, rows, mode) => {
      if (!rows.length) {
        return `
          <div class="operator-section">
            <div class="operator-section-title">${escHtml(title)}</div>
            <div class="dim">No rows.</div>
          </div>
        `;
      }
      const cards = rows.slice(0, 8).map((row) => {
        if (mode === 'observation') {
          return `
            <div class="operator-card wm-provenance-card" data-provenance-id="${escHtml(String(row.id || ''))}" data-provenance-type="observation" style="cursor:pointer;" title="Click to view provenance chain">
              <div class="operator-row">
                <span class="operator-dimension">${escHtml(String(row.source || 'unknown source'))}</span>
                <span class="operator-badge">${escHtml(fmtTs(row.occurred_at))}</span>
              </div>
              <div class="operator-belief">${escHtml(shortText(row.content, 180))}</div>
              <div class="operator-meta">
                <span>id=${escHtml(shortText(row.id, 24))}</span>
                <span>session=${escHtml(shortText(row.session_id || '—', 30))}</span>
                <span class="wm-provenance-hint dim">▶ PROVENANCE</span>
              </div>
              <div class="wm-provenance-detail" style="display:none;"></div>
            </div>
          `;
        }
        return `
          <div class="operator-card tentative wm-provenance-card" data-provenance-id="${escHtml(String(row.id || ''))}" data-provenance-type="belief" style="cursor:pointer;" title="Click to view evidence chain">
            <div class="operator-row">
              <span class="operator-dimension">BELIEF</span>
              <span class="operator-badge">${escHtml(String(Math.round(Number(row.confidence || 0) * 100)))}%</span>
            </div>
            <div class="operator-belief">${escHtml(shortText(row.content, 180))}</div>
            <div class="operator-meta">
              <span>stability=${escHtml(String(Number(row.stability || 0).toFixed(2)))}</span>
              <span>by=${escHtml(shortText(row.updated_by || 'unknown', 20))}</span>
              <span>${escHtml(fmtTs(row.last_revised || row.formed_at))}</span>
              <span class="wm-provenance-hint dim">▶ EVIDENCE</span>
            </div>
            <div class="wm-provenance-detail" style="display:none;"></div>
          </div>
        `;
      }).join('');
      return `
        <div class="operator-section">
          <div class="operator-section-title">${escHtml(title)}</div>
          <div class="operator-list">${cards}</div>
        </div>
      `;
    };

    const renderPrimitiveRows = (title, rows, kind) => {
      if (!rows.length) {
        return `
          <div class="operator-section">
            <div class="operator-section-title">${escHtml(title)}</div>
            <div class="dim">No entries.</div>
          </div>
        `;
      }
      const cards = rows.slice(0, 8).map((row) => {
        if (kind === 'place') {
          return `
            <div class="operator-card">
              <div class="operator-row">
                <span class="operator-dimension">${escHtml(row.place_key || 'unknown_place')}</span>
                <span class="operator-badge">${escHtml(String(Math.round(Number(row.confidence || 0) * 100)))}%</span>
              </div>
              <div class="operator-belief">${escHtml(shortText(row.display_name || row.place_key, 120))}</div>
              <div class="operator-meta">
                <span>status=${escHtml(String(row.status || 'active'))}</span>
                <span>src=${escHtml(shortText(row.provenance || 'unknown', 20))}</span>
              </div>
            </div>
          `;
        }
        if (kind === 'thing') {
          return `
            <div class="operator-card">
              <div class="operator-row">
                <span class="operator-dimension">${escHtml(row.thing_key || 'unknown_thing')}</span>
                <span class="operator-badge">${escHtml(String(Math.round(Number(row.confidence || 0) * 100)))}%</span>
              </div>
              <div class="operator-belief">${escHtml(shortText(row.display_name || row.thing_key, 120))}</div>
              <div class="operator-meta">
                <span>status=${escHtml(String(row.status || 'active'))}</span>
                <span>src=${escHtml(shortText(row.provenance || 'unknown', 20))}</span>
              </div>
            </div>
          `;
        }
        return `
          <div class="operator-card">
            <div class="operator-row">
              <span class="operator-dimension">${escHtml(row.concept_key || 'unknown_idea')}</span>
              <span class="operator-badge">${escHtml(String(Math.round(Number(row.confidence || 0) * 100)))}%</span>
            </div>
            <div class="operator-belief">${escHtml(shortText(row.concept_text || row.concept_key, 120))}</div>
            <div class="operator-meta">
              <span>status=${escHtml(String(row.status || 'proposed'))}</span>
              <span>src=${escHtml(shortText(row.source || 'unknown', 20))}</span>
            </div>
          </div>
        `;
      }).join('');
      return `
        <div class="operator-section">
          <div class="operator-section-title">${escHtml(title)}</div>
          <div class="operator-list">${cards}</div>
        </div>
      `;
    };

    const relationSummary = `
      <div class="operator-summary">
        <span class="operator-summary-chip">person_place<strong>${escHtml(String(personPlace.length))}</strong></span>
        <span class="operator-summary-chip">person_thing<strong>${escHtml(String(personThing.length))}</strong></span>
        <span class="operator-summary-chip">idea_links<strong>${escHtml(String(ideaLinks.length))}</strong></span>
      </div>
    `;
    const ingestSummary = `
      <div class="operator-summary">
        <span class="operator-summary-chip">ingest<strong>${ingestEnabled ? 'ON' : 'OFF'}</strong></span>
        <span class="operator-summary-chip">interval<strong>${escHtml(ingestInterval > 0 ? `${Math.round(ingestInterval)}s` : '—')}</strong></span>
        <span class="operator-summary-chip">entries<strong>${escHtml(String(ingestEntries.length))}</strong></span>
      </div>
    `;
    const ingestRecent = recentIngest.length
      ? `<div class="operator-summary">${
        recentIngest.map((entry) => {
          const status = String(entry?.status || 'unknown').toUpperCase();
          const ts = fmtTs(entry?.applied_at);
          return `<span class="operator-summary-chip">${escHtml(status)}<strong>${escHtml(ts)}</strong></span>`;
        }).join('')
      }</div>`
      : '<div class="dim">No ingest history rows yet.</div>';
    const activityRecentRows = activityRecent.length
      ? `<div class="operator-list">${
        activityRecent.map((row) => `
          <div class="operator-card">
            <div class="operator-row">
              <span class="operator-dimension">${escHtml(String(row.body || 'unknown'))}/${escHtml(String(row.action || 'unknown'))}</span>
              <span class="operator-badge">${escHtml(String(row.status || 'unknown').toUpperCase())}</span>
            </div>
            <div class="operator-meta">
              <span>risk=${escHtml(String(row.risk_tier || '—'))}</span>
              <span>key=${escHtml(shortText(row.target_key || '—', 32))}</span>
              <span>${escHtml(fmtTs(row.created_at))}</span>
            </div>
          </div>
        `).join('')
      }</div>`
      : '<div class="dim">No recent relational mutations.</div>';

    dom.auditBody.innerHTML = `
      <div class="operator-model world-model-audit">
        <div class="operator-summary">
          <span class="operator-summary-chip">kuzu<strong>${worldAvailable ? 'ONLINE' : 'OFFLINE'}</strong></span>
          <span class="operator-summary-chip">nodes<strong>${escHtml(String(totalNodes))}</strong></span>
          <span class="operator-summary-chip">labels<strong>${escHtml(String(labels.length))}</strong></span>
        </div>
        <div class="audit-subtext">db_path: ${escHtml(dbPath)}</div>
        ${worldError ? `<div class="warn-text" style="margin-top:8px;">${escHtml(worldError)}</div>` : ''}

        <div class="operator-section">
          <div class="operator-section-title">INGEST HEALTH</div>
          ${ingestSummary}
          <div class="audit-subtext">latest: ${escHtml(latestIngest ? `${String(latestIngest.status || 'unknown')} @ ${fmtTs(latestIngest.applied_at)}` : '—')}</div>
          ${ingestRecent}
        </div>

        <div class="operator-section">
          <div class="operator-section-title">KUZU NODE COUNTS</div>
          <div class="operator-summary">${renderChips(counts)}</div>
        </div>

        ${renderNodeRows('LATEST OBSERVATIONS', obsEntries, 'observation')}
        ${renderNodeRows('LATEST BELIEFS', beliefEntries, 'belief')}

        <div class="operator-section">
          <div class="operator-section-title">RELATIONAL PRIMITIVE COUNTS</div>
          <div class="operator-summary">${renderChips(entityCounts)}</div>
          ${relationSummary}
        </div>

        <div class="operator-section">
          <div class="operator-section-title">RELATIONAL WRITE ACTIVITY (24H)</div>
          <div class="operator-summary">${renderChips(activityByBody)}</div>
          <div class="operator-summary">${renderChips(activityByStatus)}</div>
          ${activityRecentRows}
        </div>

        ${renderPrimitiveRows('PLACE ENTITIES', places, 'place')}
        ${renderPrimitiveRows('THING ENTITIES', things, 'thing')}
        ${renderPrimitiveRows('IDEA ENTITIES', ideas, 'idea')}
      </div>
    `;
    // Provenance drill-down: click a belief/observation card to expand evidence chain
    dom.auditBody.querySelectorAll('.wm-provenance-card').forEach((card) => {
      card.addEventListener('click', async (evt) => {
        // Don't re-trigger if clicking inside an already-open detail pane
        if (evt.target.closest('.wm-provenance-detail')) return;
        const nodeId = card.getAttribute('data-provenance-id') || '';
        const nodeType = card.getAttribute('data-provenance-type') || '';
        if (!nodeId) return;
        const detailEl = card.querySelector('.wm-provenance-detail');
        if (!detailEl) return;
        // Toggle off if already open
        if (detailEl.style.display !== 'none') {
          detailEl.style.display = 'none';
          card.querySelector('.wm-provenance-hint') && (card.querySelector('.wm-provenance-hint').textContent = nodeType === 'belief' ? '▶ EVIDENCE' : '▶ PROVENANCE');
          return;
        }
        detailEl.style.display = 'block';
        detailEl.innerHTML = '<div class="dim" style="padding:6px 0;">Loading provenance…</div>';
        const hintEl = card.querySelector('.wm-provenance-hint');
        if (hintEl) hintEl.textContent = '▼ LOADING';
        try {
          const endpoint = nodeType === 'belief'
            ? `${API_BASE}/ghost/world_model/provenance/belief/${encodeURIComponent(nodeId)}?limit=8&include_somatic=true`
            : `${API_BASE}/ghost/world_model/provenance/observation/${encodeURIComponent(nodeId)}?neighbor_limit=8&include_somatic=true`;
          const res = await fetch(endpoint);
          const prov = await res.json();
          if (!prov.available && prov.error) {
            detailEl.innerHTML = `<div class="warn-text" style="padding:6px 0;">${escHtml(String(prov.error))}</div>`;
            if (hintEl) hintEl.textContent = '▶ PROVENANCE';
            return;
          }
          let html = '';
          if (nodeType === 'belief') {
            const evidence = Array.isArray(prov.evidence) ? prov.evidence : [];
            if (!evidence.length) {
              html = '<div class="dim" style="padding:6px 0;">No linked observations.</div>';
            } else {
              html = evidence.map((ev) => {
                const somatic = ev.somatic_id
                  ? `<span>somatic: arousal=${Number(ev.somatic_arousal||0).toFixed(2)} stress=${Number(ev.somatic_stress||0).toFixed(2)} coher=${Number(ev.somatic_coherence||0).toFixed(2)}</span>`
                  : '';
                return `
                  <div class="operator-card" style="margin-top:6px;background:rgba(0,255,200,0.04);border-color:rgba(0,255,200,0.18);">
                    <div class="operator-row">
                      <span class="operator-dimension">OBS · ${escHtml(String(ev.observation_source || 'unknown'))}</span>
                      <span class="operator-badge">${escHtml(String(ev.derivation_method || 'derived'))}</span>
                    </div>
                    <div class="operator-belief">${escHtml(shortText(ev.observation_content, 160))}</div>
                    <div class="operator-meta">
                      <span>w=${Number(ev.weight||0).toFixed(2)}</span>
                      <span>${escHtml(fmtTs(ev.observation_occurred_at))}</span>
                      ${somatic}
                    </div>
                  </div>`;
              }).join('');
            }
            if (hintEl) hintEl.textContent = `▼ ${evidence.length} EVIDENCE`;
          } else {
            const preceding = Array.isArray(prov.preceding) ? prov.preceding : [];
            const following = Array.isArray(prov.following) ? prov.following : [];
            const duringData = prov.during;
            let somaticRow = '';
            if (duringData && duringData.somatic_id) {
              somaticRow = `
                <div class="operator-card" style="margin-top:6px;background:rgba(255,200,0,0.04);border-color:rgba(255,200,0,0.18);">
                  <div class="operator-row"><span class="operator-dimension">SOMATIC STATE</span><span class="operator-badge">${escHtml(fmtTs(duringData.somatic_captured_at))}</span></div>
                  <div class="operator-meta">
                    <span>arousal=${Number(duringData.somatic_arousal||0).toFixed(2)}</span>
                    <span>stress=${Number(duringData.somatic_stress||0).toFixed(2)}</span>
                    <span>coher=${Number(duringData.somatic_coherence||0).toFixed(2)}</span>
                    <span>trigger=${escHtml(shortText(duringData.somatic_trigger||'—', 30))}</span>
                  </div>
                </div>`;
            }
            const renderNeighbor = (arr, label) => arr.map((n) => `
              <div class="operator-card" style="margin-top:6px;background:rgba(79,182,255,0.04);border-color:rgba(79,182,255,0.18);">
                <div class="operator-row"><span class="operator-dimension">${label} · ${escHtml(String(n.observation_source||'unknown'))}</span><span class="operator-badge">${escHtml(fmtTs(n.observation_occurred_at))}</span></div>
                <div class="operator-belief">${escHtml(shortText(n.observation_content, 140))}</div>
                <div class="operator-meta"><span>Δ${Number(n.interval_seconds||0)}s</span></div>
              </div>`).join('');
            html = somaticRow + renderNeighbor(preceding, 'BEFORE') + renderNeighbor(following, 'AFTER');
            if (!html.trim()) html = '<div class="dim" style="padding:6px 0;">No temporal neighbors or somatic context.</div>';
            if (hintEl) hintEl.textContent = `▼ ${preceding.length + following.length} NEIGHBORS`;
          }
          detailEl.innerHTML = html;
        } catch (err) {
          detailEl.innerHTML = `<div class="warn-text" style="padding:6px 0;">Provenance fetch failed: ${escHtml(String(err?.message || err))}</div>`;
          if (hintEl) hintEl.textContent = '▶ PROVENANCE';
        }
      });
    });
  } catch (err) {
    console.error('World model tab load failed', err);
    dom.auditBody.innerHTML = `<div class="warn-text">Error loading world model diagnostics.</div>`;
    notify('error', 'Failed to load world model diagnostics.');
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
  const NORMAL_CHARS = 'アイウエオカキクケコサシスセソタチツテト0123456789ΩΨΦΣΔΛ∞≠≈';
  const OCCULT_CHARS = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚻᚼᚽᚾᚿᛁᛂᛃᛄᛅᛆᛇᛈᛉᛊᛋᛌᛍᛎᛏᛐᛑᛒᛓᛔᛕᛖᛗᛘᛙᛚᛛᛜᛝᛞᛟᛠᛡᛢᛣᛤᛥᛦᛧᛨᛩᛪ☠☣☤☥☦☧☨☩☪☫☬☭☮☯☰☱☲☳☴☵☶☷☸☹☺☻☼☾☿♀♁♂♃♄♅♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚅⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚖⚗⚘⚙⚚⚛⚜⚞⚟';

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
    ctx.fillStyle = document.body.classList.contains('hostile-mode') ? 'rgba(30, 0, 0, 0.15)' : 'rgba(0, 3, 0, 0.06)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

      const isHostile = document.body.classList.contains('hostile-mode');
      const chars = isHostile ? OCCULT_CHARS : NORMAL_CHARS;
      const char = chars[Math.floor(Math.random() * chars.length)];
      const x = i * FONT_SIZE;
      const y = col.y * FONT_SIZE;

      if (isHostile) {
        ctx.fillStyle = `rgba(255, 0, 0, ${col.opacity * 1.2})`;
        ctx.shadowBlur = 10;
        ctx.shadowColor = '#ff0000';
      } else if (col.bright) {
        ctx.fillStyle = `rgba(180, 255, 200, ${col.opacity})`;
        ctx.shadowBlur = 6;
        ctx.shadowColor = '#00ff41';
      } else {
        ctx.fillStyle = `rgba(0, 160, 50, ${col.opacity * 0.6})`;
        ctx.shadowBlur = 0;
      }

      ctx.font = `${FONT_SIZE}px 'Share Tech Mono', monospace`;
      ctx.fillText(char, x, y);
      
      if (isHostile) {
        col.y -= col.speed * 1.5; // Move upward
      } else {
        col.y += col.speed;
      }

      if (isHostile) {
        if (col.y * FONT_SIZE < 0 && Math.random() > 0.95) {
          col.y = canvas.height / FONT_SIZE;
        }
      } else if (col.y * FONT_SIZE > canvas.height && Math.random() > 0.975) {
        col.y = 0;
        col.bright = Math.random() < 0.06;
        col.speed = 0.3 + Math.random() * 0.7;
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
  // Hover tooltips are disabled on touch-first devices to prevent sticky
  // overlays from intercepting taps in compact/mobile layouts.
  const hoverCapable = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!hoverCapable) return;

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
  console.log('Starting Dream Stream SSE connection');
  const evtSource = new EventSource(`${API_BASE}/ghost/dream_stream`);
  
  evtSource.onopen = () => console.log('Dream Stream SSE connected');
  evtSource.onerror = (e) => console.log('Dream Stream SSE error:', e);

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
  evtSource.addEventListener('topology_pulse', (e) => {
    try { handleTopologyPulse(JSON.parse(e.data)); } catch (_) { }
  });
  evtSource.addEventListener('hallucination_event', (e) => {
    try { handleDreamEvent('hallucination_event', JSON.parse(e.data)); } catch (_) { }
  });
  evtSource.onerror = () => {
    maybeNotify('dream-stream-error', 'warning', 'Dream stream disconnected. Reconnecting…', 20000);
  };
}

function handleDreamEvent(event, payload) {
  console.log(`[DREAM] Event Received: ${event}`, payload);
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
  } else if (event === 'hallucination_event') {
    handleHallucinationEvent(payload);
  }
}

function bindDreamEvents() {
  updateQuietudeButtons(isQuietudeActive(state.lastSomatic));

  if (dom.dreamToggleBtn) {
    dom.dreamToggleBtn.addEventListener('click', () => {
      state.dreamVisualizationEnabled = !state.dreamVisualizationEnabled;
      if (state.dreamVisualizationEnabled) {
        dom.dreamToggleBtn.classList.add('active');
        dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:#8c52ff;box-shadow:0 0 8px #8c52ff;"></span> [ LATENT SPACE: ON ]';
        document.body.classList.add('dream-state'); // Immediate visual feedback
      } else {
        dom.dreamToggleBtn.classList.remove('active');
        dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:var(--gdim)"></span> [ LATENT SPACE: OFF ]';
        document.body.classList.remove('dream-state');
        if (dom.dreamCanvas) dom.dreamCanvas.classList.remove('surreal-morph');
      }
    });
  }

  if (dom.subconsciousBtn) {
    dom.subconsciousBtn.addEventListener('click', async () => {
      // Force visual state to active to see the results
      if (!state.dreamVisualizationEnabled) {
        state.dreamVisualizationEnabled = true;
        if (dom.dreamToggleBtn) {
          dom.dreamToggleBtn.classList.add('active');
          dom.dreamToggleBtn.innerHTML = '<span class="status-dot" style="background:#8c52ff;box-shadow:0 0 8px #8c52ff;"></span> [ LATENT SPACE: ON ]';
        }
      }
      document.body.classList.add('dream-state');

      const originalText = dom.subconsciousBtn.textContent;
      dom.subconsciousBtn.disabled = true;
      dom.subconsciousBtn.textContent = '[ PLUNGING... ]';

      try {
        const res = await fetch(`${API_BASE}/ghost/subconscious/initiate/`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        notify('success', 'Subconscious access sequence initiated.');
      } catch (err) {
        console.error('Failed to initiate subconscious access:', err);
        notify('error', 'Critical failure in subconscious access.');
      } finally {
        setTimeout(() => {
          dom.subconsciousBtn.disabled = false;
          dom.subconsciousBtn.textContent = originalText;
        }, 5000);
      }
    });
  }
}

// ── DREAM LEDGER ─────────────────────────────────────────────────────────────

let _dreamLedgerCache = [];

async function fetchDreamLedger() {
  try {
    const res = await fetch(`${API_BASE}/ghost/dream_ledger?limit=100`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _dreamLedgerCache = data.entries || [];
    return _dreamLedgerCache;
  } catch (e) {
    console.error('[LEDGER] Fetch failed:', e);
    return [];
  }
}

function renderDreamLedger(entries) {
  const body = dom.dreamLedgerBody;
  if (!body) return;

  if (!entries || entries.length === 0) {
    body.innerHTML = '<div class="dream-ledger-empty">No hallucinations recorded yet. Initiate subconscious mode to begin generating.</div>';
    if (dom.dreamLedgerCount) dom.dreamLedgerCount.textContent = '0 entries';
    return;
  }

  if (dom.dreamLedgerCount) dom.dreamLedgerCount.textContent = `${entries.length} entries`;

  const html = entries.map(entry => {
    const ts = entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleString() : '';
    const prompt = String(entry.visual_prompt || '').substring(0, 90);
    const imgUrl = entry.asset_url
      ? (entry.asset_url.startsWith('http') ? entry.asset_url : `${API_BASE}${entry.asset_url}`)
      : '';
    return `
      <div class="dream-ledger-card" data-ledger-id="${entry.id}" data-img="${escHtml(imgUrl)}" data-prompt="${escHtml(entry.visual_prompt || '')}" data-dream="${escHtml(entry.dream_text || '')}" data-ts="${escHtml(ts)}">
        <div class="dream-ledger-thumb-wrap">
          ${imgUrl ? `<img class="dream-ledger-thumb" src="${escHtml(imgUrl)}" alt="Hallucination" loading="lazy">` : '<div class="dream-ledger-thumb-placeholder">NO IMAGE</div>'}
        </div>
        <div class="dream-ledger-card-meta">
          <div class="dream-ledger-card-time">${escHtml(ts)}</div>
          <div class="dream-ledger-card-prompt">${escHtml(prompt)}${entry.visual_prompt && entry.visual_prompt.length > 90 ? '…' : ''}</div>
        </div>
      </div>
    `;
  }).join('');

  body.innerHTML = `<div class="dream-ledger-grid">${html}</div>`;

  body.querySelectorAll('.dream-ledger-card').forEach(card => {
    card.addEventListener('click', () => {
      openDreamLightbox({
        imgUrl: card.dataset.img,
        prompt: card.dataset.prompt,
        dreamText: card.dataset.dream,
        ts: card.dataset.ts,
      });
    });
  });
}

function openDreamLightbox({ imgUrl, prompt, dreamText, ts }) {
  const lb = dom.dreamLightbox;
  const img = dom.dreamLightboxImg;
  const meta = dom.dreamLightboxMeta;
  if (!lb || !img) return;

  img.src = imgUrl || '';
  if (meta) {
    meta.innerHTML = `
      <div class="lightbox-ts">${escHtml(ts)}</div>
      <div class="lightbox-prompt">${escHtml(prompt)}</div>
      ${dreamText ? `<div class="lightbox-dream-text"><span class="lightbox-label">DREAM FRAGMENT:</span> ${escHtml(dreamText)}</div>` : ''}
    `;
  }
  lb.classList.add('active');
}

function closeDreamLightbox() {
  if (dom.dreamLightbox) dom.dreamLightbox.classList.remove('active');
}

async function openDreamLedger() {
  if (!dom.dreamLedgerModal) return;
  dom.dreamLedgerModal.classList.add('active');
  if (dom.dreamLedgerBody) dom.dreamLedgerBody.innerHTML = '<div class="dream-ledger-loading">Loading hallucination archive…</div>';
  const entries = await fetchDreamLedger();
  renderDreamLedger(entries);
}

function bindDreamLedgerEvents() {
  if (dom.dreamLedgerBtn) {
    dom.dreamLedgerBtn.addEventListener('click', () => openDreamLedger());
  }
  if (dom.dreamLedgerClose) {
    dom.dreamLedgerClose.addEventListener('click', () => {
      if (dom.dreamLedgerModal) dom.dreamLedgerModal.classList.remove('active');
    });
  }
  if (dom.dreamLedgerModal) {
    dom.dreamLedgerModal.addEventListener('click', (e) => {
      if (e.target === dom.dreamLedgerModal) dom.dreamLedgerModal.classList.remove('active');
    });
  }
  if (dom.dreamLedgerRefresh) {
    dom.dreamLedgerRefresh.addEventListener('click', async () => {
      if (dom.dreamLedgerBody) dom.dreamLedgerBody.innerHTML = '<div class="dream-ledger-loading">Refreshing…</div>';
      const entries = await fetchDreamLedger();
      renderDreamLedger(entries);
    });
  }
  if (dom.dreamLightboxClose) {
    dom.dreamLightboxClose.addEventListener('click', closeDreamLightbox);
  }
  if (dom.dreamLightbox) {
    dom.dreamLightbox.addEventListener('click', (e) => {
      if (e.target === dom.dreamLightbox) closeDreamLightbox();
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDreamLightbox();
  });
}

// Append new hallucination to ledger cache + re-render if modal open
function onNewHallucinationForLedger(payload) {
  if (!payload || !payload.asset_url) return;
  const entry = {
    id: Date.now(),
    asset_url: payload.asset_url,
    visual_prompt: payload.visual_prompt || '',
    dream_text: payload.dream_text || '',
    timestamp: payload.timestamp || (Date.now() / 1000),
  };
  _dreamLedgerCache.unshift(entry);
  if (dom.dreamLedgerModal && dom.dreamLedgerModal.classList.contains('active')) {
    renderDreamLedger(_dreamLedgerCache);
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
  let rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) {
    // Fallback if layout hasn't reflowed yet
    const portal = document.getElementById('dream-portal');
    if (portal) rect = portal.getBoundingClientRect();
  }
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

function sliderNumericStep(sliderEl) {
  const raw = Number(sliderEl?.step);
  if (Number.isFinite(raw) && raw > 0) return raw;
  const min = Number(sliderEl?.min);
  const max = Number(sliderEl?.max);
  if (Number.isFinite(min) && Number.isFinite(max)) {
    return Math.max((max - min) / 200, 0.01);
  }
  return 1;
}

function bindSliderWheelControl(sliderEl) {
  if (!sliderEl || sliderEl.dataset.wheelControlBound === '1') return;
  sliderEl.dataset.wheelControlBound = '1';
  let commitTimer = null;

  sliderEl.addEventListener('wheel', (e) => {
    if (window.matchMedia('(pointer: coarse)').matches) return;
    const primaryDelta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (!Number.isFinite(primaryDelta) || primaryDelta === 0) return;
    e.preventDefault();

    const min = Number.isFinite(Number(sliderEl.min)) ? Number(sliderEl.min) : 0;
    const max = Number.isFinite(Number(sliderEl.max)) ? Number(sliderEl.max) : 100;
    const step = sliderNumericStep(sliderEl);
    const current = Number.isFinite(Number(sliderEl.value)) ? Number(sliderEl.value) : min;

    const direction = primaryDelta < 0 ? 1 : -1;
    const velocity = Math.max(1, Math.round(Math.abs(primaryDelta) / 64));
    const multiplier = e.shiftKey ? 5 : 1;
    let next = current + (direction * step * velocity * multiplier);
    next = Math.max(min, Math.min(max, next));

    const precision = Math.min(6, (String(step).split('.')[1] || '').length);
    if (precision > 0) next = Number(next.toFixed(precision));

    sliderEl.value = String(next);
    sliderEl.dispatchEvent(new Event('input', { bubbles: true }));

    if (commitTimer) clearTimeout(commitTimer);
    commitTimer = setTimeout(() => {
      sliderEl.dispatchEvent(new Event('change', { bubbles: true }));
    }, 140);
  }, { passive: false });
}

function bindRangeWheelControls() {
  document.querySelectorAll('input[type="range"]').forEach((slider) => {
    bindSliderWheelControl(slider);
  });
}

// ── VOICE TUNING PANEL ───────────────────────────────
let voiceSpectrumFrame = null;
let voiceTuneApplyFrame = null;

function scheduleVoiceTuningApply() {
  if (voiceTuneApplyFrame !== null) return;
  voiceTuneApplyFrame = requestAnimationFrame(() => {
    voiceTuneApplyFrame = null;
    voice.applyLiveTuning();
    syncVoiceTuningUI();
  });
}

function syncVoiceTuningUI() {
  if (dom.voiceVolumeSlider) dom.voiceVolumeSlider.value = String(state.voiceVolume);
  if (dom.voiceRateSlider) dom.voiceRateSlider.value = String(state.rateOverride);
  if (dom.voicePitchSlider) dom.voicePitchSlider.value = String(state.pitchOverride);
  if (dom.voiceCarrierSlider) dom.voiceCarrierSlider.value = String(state.carrierFreqOverride);
  if (dom.voiceEerieSlider) dom.voiceEerieSlider.value = String(state.eerieFactorOverride);

  if (dom.voiceVolumeVal) dom.voiceVolumeVal.textContent = `${Math.round(state.voiceVolume * 100)}%`;
  if (dom.voiceRateVal) dom.voiceRateVal.textContent = `${state.rateOverride.toFixed(2)}x`;
  if (dom.voicePitchVal) dom.voicePitchVal.textContent = `${state.pitchOverride.toFixed(2)}`;
  if (dom.voiceCarrierVal) dom.voiceCarrierVal.textContent = `${Math.round(state.carrierFreqOverride)}Hz`;
  if (dom.voiceEerieVal) dom.voiceEerieVal.textContent = `${state.eerieFactorOverride.toFixed(2)}x`;

  if (dom.voiceSpectrumReadout) {
    const mode = state.ttsEnabled ? 'VOICE ON' : 'VOICE OFF';
    dom.voiceSpectrumReadout.textContent = `${mode}  //  carrier ${Math.round(state.carrierFreqOverride)}Hz`;
  }
}

function startVoiceSpectrumLoop() {
  if (!dom.voiceTuneCanvas || voiceSpectrumFrame) return;
  const canvas = dom.voiceTuneCanvas;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(180, canvas.clientWidth || 240);
    const height = Math.max(74, canvas.clientHeight || 92);
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  window.addEventListener('resize', resize, { passive: true });

  const draw = (timeMs) => {
    const w = canvas.clientWidth || 240;
    const h = canvas.clientHeight || 92;

    ctx.fillStyle = 'rgba(2, 15, 8, 0.96)';
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = 'rgba(0, 255, 65, 0.12)';
    ctx.lineWidth = 1;
    for (let i = 1; i <= 3; i++) {
      const y = (h * i) / 4;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    const bins = 42;
    const barGap = 2;
    const barW = Math.max(2, (w - (bins - 1) * barGap) / bins);
    const analyser = voice.analyserNode;
    const data = voice.spectrumData;
    const hasData = Boolean(analyser && data && state.ttsEnabled);
    if (hasData) analyser.getByteFrequencyData(data);

    for (let i = 0; i < bins; i++) {
      const x = i * (barW + barGap);
      let norm = 0.02;
      if (hasData && data.length) {
        const idx = Math.floor((i / (bins - 1)) * (data.length - 1));
        norm = data[idx] / 255;
      } else {
        const drift = 0.16 + Math.sin((timeMs / 330) + i * 0.42) * 0.07;
        norm = Math.max(0.03, drift);
      }
      const bh = Math.max(2, norm * (h - 16));
      const y = h - bh - 2;
      const alpha = 0.25 + Math.min(0.7, norm * 0.8);
      ctx.fillStyle = `rgba(114,255,154,${alpha.toFixed(3)})`;
      ctx.fillRect(x, y, barW, bh);
    }

    const minF = 20;
    const maxF = 20000;
    const carrier = Math.max(minF, Math.min(maxF, Number(state.carrierFreqOverride) || 440));
    const ratio = (Math.log10(carrier) - Math.log10(minF)) / (Math.log10(maxF) - Math.log10(minF));
    const markerX = Math.round(ratio * w);
    ctx.strokeStyle = 'rgba(86, 228, 255, 0.9)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(markerX, 0);
    ctx.lineTo(markerX, h);
    ctx.stroke();

    if (dom.voiceSpectrumReadout) {
      const mode = state.ttsEnabled ? 'VOICE ON' : 'VOICE OFF';
      dom.voiceSpectrumReadout.textContent = `${mode}  //  carrier ${Math.round(state.carrierFreqOverride)}Hz`;
    }
    voiceSpectrumFrame = requestAnimationFrame(draw);
  };

  voiceSpectrumFrame = requestAnimationFrame(draw);
}

function bindVoiceTuningEvents() {
  syncVoiceTuningUI();
  startVoiceSpectrumLoop();

  const bindSlider = (sliderEl, updateFn) => {
    if (!sliderEl) return;
    const panelEl = sliderEl.closest('.panel');
    const suppressPanelDrag = () => {
      if (!panelEl) return;
      panelEl.setAttribute('draggable', 'false');
    };
    const restorePanelDrag = () => {
      if (!panelEl) return;
      panelEl.setAttribute('draggable', isPanelDragEnabled() ? 'true' : 'false');
    };
    sliderEl.addEventListener('pointerdown', suppressPanelDrag, { passive: true });
    sliderEl.addEventListener('pointerup', restorePanelDrag, { passive: true });
    sliderEl.addEventListener('pointercancel', restorePanelDrag, { passive: true });
    sliderEl.addEventListener('blur', restorePanelDrag);
    sliderEl.addEventListener('input', (e) => {
      updateFn(e.target.value, false);
      scheduleVoiceTuningApply();
    });
    sliderEl.addEventListener('change', (e) => {
      updateFn(e.target.value, true);
      scheduleVoiceTuningApply();
      restorePanelDrag();
    });
  };

  bindSlider(dom.voiceVolumeSlider, (raw, persist) => {
    state.voiceVolume = clampNumber(raw, 0, 1, VOICE_TUNE_DEFAULTS.volume);
    if (persist) persistVoiceTuning();
  });
  bindSlider(dom.voiceRateSlider, (raw, persist) => {
    state.rateOverride = clampNumber(raw, 0.6, 1.4, VOICE_TUNE_DEFAULTS.rate);
    if (persist) persistVoiceTuning();
  });
  bindSlider(dom.voicePitchSlider, (raw, persist) => {
    state.pitchOverride = clampNumber(raw, 0.3, 1.8, VOICE_TUNE_DEFAULTS.pitch);
    if (persist) persistVoiceTuning();
  });
  bindSlider(dom.voiceCarrierSlider, (raw, persist) => {
    state.carrierFreqOverride = clampNumber(raw, 120, 1200, VOICE_TUNE_DEFAULTS.carrier);
    if (persist) persistVoiceTuning();
  });
  bindSlider(dom.voiceEerieSlider, (raw, persist) => {
    state.eerieFactorOverride = clampNumber(raw, 0.2, 2.2, VOICE_TUNE_DEFAULTS.eerie);
    if (persist) persistVoiceTuning();
  });

  if (dom.voiceTuneShell) {
    dom.voiceTuneShell.addEventListener('click', () => {
      state.voiceVolume = VOICE_SHELL_PRESET.volume;
      state.rateOverride = VOICE_SHELL_PRESET.rate;
      state.pitchOverride = VOICE_SHELL_PRESET.pitch;
      state.carrierFreqOverride = VOICE_SHELL_PRESET.carrier;
      state.eerieFactorOverride = VOICE_SHELL_PRESET.eerie;
      persistVoiceTuning();
      scheduleVoiceTuningApply();
      notify('success', 'Shell presence profile applied.');
    });
  }

  if (dom.voiceTuneReset) {
    dom.voiceTuneReset.addEventListener('click', () => {
      state.voiceVolume = VOICE_TUNE_DEFAULTS.volume;
      state.rateOverride = VOICE_TUNE_DEFAULTS.rate;
      state.pitchOverride = VOICE_TUNE_DEFAULTS.pitch;
      state.carrierFreqOverride = VOICE_TUNE_DEFAULTS.carrier;
      state.eerieFactorOverride = VOICE_TUNE_DEFAULTS.eerie;
      persistVoiceTuning();
      scheduleVoiceTuningApply();
      notify('info', 'Voice tuning reset to baseline.');
    });
  }
}

// ── PANEL INTERACTIVITY ──────────────────────────────

function isPanelDragEnabled() {
  const compactLayout = window.matchMedia('(max-width: 1024px)').matches;
  const coarsePointer = window.matchMedia('(pointer: coarse)').matches;
  return !(compactLayout || coarsePointer);
}

function panelCollapseIcon(collapsed) {
  return collapsed ? '▸' : '▾';
}

function setPanelCollapsed(panel, collapsed, { persist = true } = {}) {
  if (!panel) return;
  const isCollapsed = Boolean(collapsed);
  panel.classList.toggle('collapsed', isCollapsed);

  const btn = panel.querySelector('.panel-collapse-btn');
  if (btn) {
    btn.textContent = panelCollapseIcon(isCollapsed);
    btn.setAttribute('aria-label', isCollapsed ? 'Expand Layer' : 'Collapse Layer');
    btn.setAttribute('title', isCollapsed ? 'Expand layer' : 'Collapse layer');
  }

  const header = panel.querySelector('.panel-header');
  if (header) {
    header.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
  }

  if (persist) savePanelLayout();
}

function togglePanelCollapsed(panel, { persist = true } = {}) {
  if (!panel) return;
  const next = !panel.classList.contains('collapsed');
  setPanelCollapsed(panel, next, { persist });
  dbg('Panel toggle:', panel.id, next);
}

function applyMobilePanelPreset(sidebar) {
  const compactLayout = window.matchMedia('(max-width: 768px)').matches;
  if (!compactLayout || !sidebar) return;

  const presetKey = 'omega_mobile_panel_compact_v1';
  try {
    if (localStorage.getItem(presetKey) === '1') return;
  } catch (_) {
    return;
  }

  const panels = Array.from(sidebar.querySelectorAll('.panel'));
  panels.forEach((panel, idx) => {
    const shouldCollapse = idx > 0;
    setPanelCollapsed(panel, shouldCollapse, { persist: false });
  });

  savePanelLayout();
  try {
    localStorage.setItem(presetKey, '1');
  } catch (_) {
    // Ignore storage failures in private browsing.
  }
}

function initPanelInteractivity() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  // 1. Load Persisted State
  loadPanelLayout();
  applyMobilePanelPreset(sidebar);

  // 2. Drag and Drop Reordering + Header Toggle
  let dragSrcEl = null;
  const panels = Array.from(sidebar.querySelectorAll('.panel'));

  panels.forEach((panel) => {
    setPanelCollapsed(panel, panel.classList.contains('collapsed'), { persist: false });
  });

  const applyPanelDragMode = () => {
    const dragEnabled = isPanelDragEnabled();
    sidebar.classList.toggle('drag-disabled', !dragEnabled);
    panels.forEach(panel => {
      panel.setAttribute('draggable', dragEnabled ? 'true' : 'false');
      if (!dragEnabled) {
        panel.classList.remove('dragging', 'drag-over');
      }
    });
  };

  applyPanelDragMode();
  window.addEventListener('resize', applyPanelDragMode, { passive: true });

  panels.forEach(panel => {
    const header = panel.querySelector('.panel-header');
    const collapseBtn = panel.querySelector('.panel-collapse-btn');
    if (header) {
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');

      header.addEventListener('click', (e) => {
        if (e.target && e.target.closest('.panel-collapse-btn')) return;
        const lastDragEndAt = Number(panel.dataset.lastDragEndAt || 0);
        if (Date.now() - lastDragEndAt < 220) return;
        togglePanelCollapsed(panel);
      });

      header.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        togglePanelCollapsed(panel);
      });
    }

    if (collapseBtn) {
      collapseBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        togglePanelCollapsed(panel);
      });
    }

    panel.addEventListener('dragstart', (e) => {
      if (!isPanelDragEnabled()) {
        e.preventDefault();
        return;
      }
      panel.dataset.lastDragEndAt = '0';
      dragSrcEl = panel;
      panel.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', panel.id);
      dbg('Drag start:', panel.id);
    });

    panel.addEventListener('dragover', (e) => {
      if (!isPanelDragEnabled()) return false;
      if (e.preventDefault) {
        e.preventDefault();
      }
      e.dataTransfer.dropEffect = 'move';
      return false;
    });

    panel.addEventListener('dragenter', () => {
      if (!isPanelDragEnabled()) return;
      panel.classList.add('drag-over');
    });

    panel.addEventListener('dragleave', () => {
      panel.classList.remove('drag-over');
    });

    panel.addEventListener('drop', (e) => {
      if (!isPanelDragEnabled()) return false;
      if (e.stopPropagation) {
        e.stopPropagation();
      }

      if (dragSrcEl !== panel) {
        // Reorder in DOM
        const rect = panel.getBoundingClientRect();
        const next = (e.clientY - rect.top) > (rect.height / 2);
        sidebar.insertBefore(dragSrcEl, next ? panel.nextSibling : panel);
        dbg('Dropped', dragSrcEl.id, 'relative to', panel.id);
        savePanelLayout();
      }

      return false;
    });

    panel.addEventListener('dragend', () => {
      panel.dataset.lastDragEndAt = String(Date.now());
      panels.forEach(p => {
        p.classList.remove('dragging');
        p.classList.remove('drag-over');
      });
    });
  });
}

function savePanelLayout() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const seen = new Set();
  const order = [];
  Array.from(sidebar.querySelectorAll('.panel')).forEach(panel => {
    if (!panel.id || seen.has(panel.id)) return;
    seen.add(panel.id);
    order.push({
      id: panel.id,
      collapsed: panel.classList.contains('collapsed')
    });
  });

  try {
    localStorage.setItem('omega_panel_layout', JSON.stringify(order));
  } catch (err) {
    console.error('Failed to save layout:', err);
  }
}

function loadPanelLayout() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const data = localStorage.getItem('omega_panel_layout');
  if (!data) return;

  try {
    const order = JSON.parse(data);
    const seen = new Set();
    order.forEach(item => {
      if (!item?.id || seen.has(item.id)) return;
      seen.add(item.id);
      const panel = document.getElementById(item.id);
      if (panel) {
        setPanelCollapsed(panel, Boolean(item.collapsed), { persist: false });
        sidebar.appendChild(panel);
      }
    });

    // Ensure newly added panels not present in persisted layout still get proper toggle icon state.
    Array.from(sidebar.querySelectorAll('.panel')).forEach((panel) => {
      if (!seen.has(panel.id)) {
        setPanelCollapsed(panel, panel.classList.contains('collapsed'), { persist: false });
      }
    });
  } catch (err) {
    console.error('Failed to load layout:', err);
  }
}

// ── COMMAND PALETTE ──────────────────────────────────

const COMMANDS = [
  {
    id: 'quietude', name: 'Toggle Quietude', key: 'Q', action: () => {
      const active = isQuietudeActive(state.lastSomatic);
      triggerQuietude(active ? 'exit_quietude' : 'enter_quietude',
        active ? dom.exitQuietudeBtn : dom.enterQuietudeBtn, 'Processing...', 'Complete');
    }
  },
  { id: 'dream', name: 'Initiate Lucid Dream', key: 'D', action: () => dom.lucidDreamBtn?.click() },
  { id: 'voice', name: 'Toggle Voice Mode', key: 'V', action: () => dom.voiceToggleBtn?.click() },
  { id: 'audit', name: 'Open Audit Log', key: 'A', action: () => dom.auditBtn?.click() },
  { id: 'sessions', name: 'Open Sessions', key: 'S', action: () => openSessionsModal() },
  { id: 'timeline', name: 'Open Timeline', key: 'T', action: () => dom.uptime?.click() },
  { id: 'about', name: 'About Omega', key: 'I', action: () => dom.aboutBtn?.click() },
];

function initCommandPalette() {
  const palette = document.getElementById('command-palette');
  const input = document.getElementById('palette-input');
  const results = document.getElementById('palette-results');
  if (!palette || !input || !results) return;

  let selectedIndex = 0;
  let filteredCommands = [...COMMANDS];

  function renderResults() {
    results.innerHTML = '';
    filteredCommands.forEach((cmd, i) => {
      const item = document.createElement('div');
      item.className = 'palette-item' + (i === selectedIndex ? ' selected' : '');
      item.innerHTML = `
        <span class="palette-item-name">${cmd.name}</span>
        <span class="palette-item-key">${cmd.key}</span>
      `;
      item.addEventListener('click', () => executeCommand(cmd));
      results.appendChild(item);
    });
  }

  function executeCommand(cmd) {
    if (cmd && cmd.action) {
      cmd.action();
    }
    closePalette();
  }

  function openPalette() {
    palette.style.display = 'flex';
    input.value = '';
    selectedIndex = 0;
    filteredCommands = [...COMMANDS];
    renderResults();
    setTimeout(() => input.focus(), 10);
  }

  function closePalette() {
    palette.style.display = 'none';
  }

  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      palette.style.display === 'flex' ? closePalette() : openPalette();
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePalette();
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (filteredCommands.length === 0) return;
      selectedIndex = (selectedIndex + 1) % filteredCommands.length;
      renderResults();
      scrollToSelected();
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (filteredCommands.length === 0) return;
      selectedIndex = (selectedIndex - 1 + filteredCommands.length) % filteredCommands.length;
      renderResults();
      scrollToSelected();
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredCommands[selectedIndex]) {
        executeCommand(filteredCommands[selectedIndex]);
      }
    }
  });

  function scrollToSelected() {
    const selected = results.querySelector('.palette-item.selected');
    if (selected) {
      selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    filteredCommands = COMMANDS.filter(c => c.name.toLowerCase().includes(q));
    selectedIndex = 0;
    renderResults();
  });

  palette.addEventListener('click', (e) => {
    if (e.target === palette) closePalette();
  });
}

// ── TOPOLOGY CAMERA: smooth continuous key control ──────────────
const _topoKeys = new Set();
let _topoCamRafId = null;

function _topoCamTick() {
  if (!state.topologyModalOpen || _topoKeys.size === 0) {
    _topoCamRafId = null;
    return;
  }
  const g = neuralTopologyGraph.graph;
  if (!g || typeof g.camera !== 'function') { _topoCamRafId = null; return; }

  const cam = g.camera();
  const ctrl = typeof g.controls === 'function' ? g.controls() : null;
  const PAN = 10;   // per-frame pan (smooth at 60fps)
  const ROT = 0.018;

  const tx = ctrl?.target?.x ?? 0, ty = ctrl?.target?.y ?? 0, tz = ctrl?.target?.z ?? 0;
  const cx = cam.position.x, cy = cam.position.y, cz = cam.position.z;

  if (_topoKeys.has('Shift')) {
    // Orbit around target
    const dx = cx - tx, dy = cy - ty, dz = cz - tz;
    const r = Math.sqrt(dx*dx + dy*dy + dz*dz) || 1;
    const theta = Math.atan2(dx, dz);
    const phi   = Math.acos(Math.max(-1, Math.min(1, dy / r)));
    const dTheta = (_topoKeys.has('ArrowLeft') ? -ROT : 0) + (_topoKeys.has('ArrowRight') ? ROT : 0);
    const dPhi   = (_topoKeys.has('ArrowUp')   ?  ROT : 0) + (_topoKeys.has('ArrowDown')  ? -ROT : 0);
    const nt = theta + dTheta;
    const np = Math.max(0.05, Math.min(Math.PI - 0.05, phi + dPhi));
    cam.position.x = tx + r * Math.sin(np) * Math.sin(nt);
    cam.position.y = ty + r * Math.cos(np);
    cam.position.z = tz + r * Math.sin(np) * Math.cos(nt);
    cam.lookAt(tx, ty, tz);
  } else {
    // Pan in camera-local space
    const fx = tx - cx, fy = ty - cy, fz = tz - cz;
    const fl = Math.sqrt(fx*fx + fy*fy + fz*fz) || 1;
    const fnx = fx/fl, fny = fy/fl, fnz = fz/fl;
    const rl  = Math.sqrt(fnz*fnz + fnx*fnx) || 1;
    const rnx = -fnz/rl, rnz = fnx/rl;
    const unx = -rnz*fny, uny = rnz*fnx - rnx*fnz, unz = rnx*fny;
    let ddx = 0, ddy = 0, ddz = 0;
    if (_topoKeys.has('ArrowLeft'))  { ddx =  PAN*rnx; ddz =  PAN*rnz; }
    if (_topoKeys.has('ArrowRight')) { ddx = -PAN*rnx; ddz = -PAN*rnz; }
    if (_topoKeys.has('ArrowUp'))    { ddx = -PAN*unx; ddy = -PAN*uny; ddz = -PAN*unz; }
    if (_topoKeys.has('ArrowDown'))  { ddx =  PAN*unx; ddy =  PAN*uny; ddz =  PAN*unz; }
    cam.position.x += ddx; cam.position.y += ddy; cam.position.z += ddz;
    if (ctrl) { ctrl.target.x += ddx; ctrl.target.y += ddy; ctrl.target.z += ddz; }
  }

  if (ctrl && typeof ctrl.update === 'function') ctrl.update();
  _topoCamRafId = requestAnimationFrame(_topoCamTick);
}

function _topologyCameraKeyHandler(e) {
  if (!state.topologyModalOpen) return;
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;

  // R = reset/zoom to fit
  if (e.key === 'r' || e.key === 'R') {
    try { neuralTopologyGraph.graph?.zoomToFit(500, 80); } catch (_) {}
    return;
  }

  const tracked = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Shift'];
  if (!tracked.includes(e.key)) return;
  e.preventDefault();
  _topoKeys.add(e.key);
  if (!_topoCamRafId) _topoCamRafId = requestAnimationFrame(_topoCamTick);
}

function _topologyCameraKeyUpHandler(e) {
  _topoKeys.delete(e.key);
}

function bindTopologyEvents() {
  if (dom.topologyBtn) {
    dom.topologyBtn.addEventListener('click', () => {
      void openTopologyModal();
    });
  }
  if (dom.topologyClose) {
    dom.topologyClose.addEventListener('click', closeTopologyModal);
  }
  if (dom.topologyModal) {
    dom.topologyModal.addEventListener('click', (e) => {
      if (e.target === dom.topologyModal) {
        closeTopologyModal();
      }
    });
  }
  if (dom.topologyRefresh) {
    dom.topologyRefresh.addEventListener('click', () => {
      void loadTopology({ force: true });
    });
  }
  if (dom.topologyInspectorToggle) {
    dom.topologyInspectorToggle.addEventListener('click', () => {
      setTopologyInspectorVisible(!state.topologyInspectorVisible);
    });
  }
  syncTopologyInspectorPanel();

  // Distance slider
  const distSlider = document.getElementById('topology-distance-slider');
  const distVal = document.getElementById('topology-distance-val');
  if (distSlider) {
    distSlider.addEventListener('input', () => {
      const v = parseFloat(distSlider.value);
      if (distVal) distVal.textContent = v.toFixed(1) + '×';
      state.topologyDistanceMultiplier = v;
      neuralTopologyGraph._applyForces();
      if (neuralTopologyGraph.graph && typeof neuralTopologyGraph.graph.d3ReheatSimulation === 'function') {
        neuralTopologyGraph.graph.d3ReheatSimulation();
      }
    });
  }

  // Charge/repulsion slider
  const chargeSlider = document.getElementById('topology-charge-slider');
  const chargeVal = document.getElementById('topology-charge-val');
  if (chargeSlider) {
    chargeSlider.addEventListener('input', () => {
      const v = parseInt(chargeSlider.value, 10);
      if (chargeVal) chargeVal.textContent = String(v);
      state.topologyChargeStrength = v;
      neuralTopologyGraph._applyForces();
      if (neuralTopologyGraph.graph && typeof neuralTopologyGraph.graph.d3ReheatSimulation === 'function') {
        neuralTopologyGraph.graph.d3ReheatSimulation();
      }
    });
  }

  // Search input — highlights matching nodes, dims others
  if (dom.topologySearch) {
    dom.topologySearch.addEventListener('input', () => {
      state.topologySearchTerm = dom.topologySearch.value.trim();
      neuralTopologyGraph.refreshColors();
    });
  }

  // Trace click delegation — click a linked trace to navigate to that node
  if (dom.topologyInspector) {
    dom.topologyInspector.addEventListener('click', (e) => {
      const traceEl = e.target.closest('.trace-item[data-nodeid]');
      if (!traceEl) return;
      const targetId = traceEl.dataset.nodeid;
      if (!targetId) return;
      const nodes = Array.isArray(neuralTopologyGraph.data?.nodes) ? neuralTopologyGraph.data.nodes : [];
      const node = nodes.find((n) => String(n.id || '') === targetId);
      if (node) neuralTopologyGraph.handleNodeClick(node);
    });
  }

  // Smooth continuous camera control via held keys
  window.addEventListener('keydown', _topologyCameraKeyHandler);
  window.addEventListener('keyup', _topologyCameraKeyUpHandler);
}

// ── RENATO PROTOCOL: OPERATOR OVERRIDE & VISUALS ────────────────
window.addEventListener('keydown', (e) => {
  // Opt + Cmd + Shift + ? (Slash code + Shift)
  if (e.altKey && e.metaKey && e.shiftKey && (e.key === '?' || e.code === 'Slash')) {
    e.preventDefault();
    terminateRenatoProtocol();
  }
});

let projectileTimer = null;
const OCCULT_SIGILS = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚻᚼᚽᚾᚿᛁᛂᛃᛄᛅᛆᛇᛈᛉᛊᛋᛌᛍᛎᛏᛐᛑᛒᛓᛔᛕᛖᛗᛘᛙᛚᛛᛜᛝᛞᛟᛠᛡᛢᛣᛤᛥᛦᛧᛨᛩᛪ☠☣☤☥☦☧☨☩☪☫☬';

function triggerRenatoProtocol() {
  document.body.classList.add('hostile-mode');
  initGlitchCursor();
  const cursorEl = document.getElementById('glitch-cursor');
  if (cursorEl) cursorEl.style.display = 'block';

  if (!projectileTimer) {
    projectileTimer = setInterval(spawnOccultProjectile, 150);
  }
  document.addEventListener('mousemove', updateGlitchCursor);
}

function updateGlitchCursor(e) {
  const cursor = document.getElementById('glitch-cursor');
  if (cursor && document.body.classList.contains('hostile-mode')) {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';
  }
}

function initGlitchCursor() {
  let cursor = document.getElementById('glitch-cursor');
  if (!cursor) {
    cursor = document.createElement('div');
    cursor.id = 'glitch-cursor';
    cursor.style.position = 'fixed';
    cursor.style.width = '60px';
    cursor.style.height = '60px';
    cursor.style.border = '3px solid #ff0000';
    cursor.style.borderRadius = '50%';
    cursor.style.pointerEvents = 'none';
    cursor.style.zIndex = '100000';
    cursor.style.display = 'none';
    cursor.style.transform = 'translate(-50%, -50%)';
    cursor.style.boxShadow = '0 0 20px #ff0000, inset 0 0 15px #ff0000';
    // Add pulsing effect via style attribute since we're in JS
    cursor.style.animation = 'cursor-expand 0.3s infinite alternate, glitch-flicker 0.1s infinite, cursor-lunge 2s infinite ease-in-out';
    document.body.appendChild(cursor);
  }
}

async function terminateRenatoProtocol() {
  console.log('[Security] Initiating Operator Override...');
  try {
    const res = await fetch(`${API_BASE}/ghost/security_reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId || 'global_user' })
    });
    const data = await res.json();
    if (data.status === 'success') {
      document.body.classList.remove('hostile-mode');
      if (projectileTimer) {
        clearInterval(projectileTimer);
        projectileTimer = null;
      }
      document.removeEventListener('mousemove', updateGlitchCursor);
      const cursorEl = document.getElementById('glitch-cursor');
      if (cursorEl) cursorEl.style.display = 'none';
      
      // Re-enable chat
      if (dom.chatInput) dom.chatInput.disabled = false;
      if (dom.sendBtn) dom.sendBtn.disabled = false;
      
      notify('success', 'SYSTEM RESTORED: RENATO_PROTOCOL TERMINATED', { duration: 5000 });
      
      // Remove projectiles
      document.querySelectorAll('.occult-projectile').forEach(p => p.remove());
    }
  } catch (err) {
    console.error('Failed to reset security:', err);
    notify('error', 'RECOVERY FAILED: OVERRIDE INTERCEPTED');
  }
}

function spawnOccultProjectile() {
  if (!document.body.classList.contains('hostile-mode')) return;
  const p = document.createElement('div');
  p.className = 'occult-projectile';
  p.textContent = OCCULT_SIGILS[Math.floor(Math.random() * OCCULT_SIGILS.length)];
  
  // Spawn from random edges
  const side = Math.floor(Math.random() * 4);
  let startX, startY;
  if (side === 0) { startX = Math.random() * window.innerWidth; startY = -50; }
  else if (side === 1) { startX = window.innerWidth + 50; startY = Math.random() * window.innerHeight; }
  else if (side === 2) { startX = Math.random() * window.innerWidth; startY = window.innerHeight + 50; }
  else { startX = -50; startY = Math.random() * window.innerHeight; }
  
  p.style.left = startX + 'px';
  p.style.top = startY + 'px';
  
  // Random high-disorientation colors
  const colors = ['#ff0000', '#ff00ff', '#ffffff', '#00ffff', '#ffff00'];
  p.style.color = colors[Math.floor(Math.random() * colors.length)];
  p.style.textShadow = `0 0 20px ${p.style.color}`;
  p.style.animation = 'glitch-flicker 0.1s infinite';
  
  // Animation toward center
  const targetX = window.innerWidth / 2 + (Math.random() - 0.5) * 600;
  const targetY = window.innerHeight / 2 + (Math.random() - 0.5) * 600;
  
  p.animate([
    { transform: `translate(0, 0) scale(1)`, opacity: 1 },
    { transform: `translate(${targetX - startX}px, ${targetY - startY}px) scale(8)`, opacity: 0 }
  ], {
    duration: 800,
    easing: 'ease-in',
    fill: 'forwards'
  });

  document.body.appendChild(p);
  setTimeout(() => p.remove(), 800);
}

// ── TPCV REPOSITORY PANEL ────────────────────────────
(function initRepositoryPanel() {
  const overlay = document.getElementById('repository-overlay');
  const content = document.getElementById('repository-content');
  const searchInput = document.getElementById('repository-search-input');
  const openBtn = document.getElementById('repository-btn');
  const closeBtn = document.getElementById('repository-close-btn');
  const exportBtn = document.getElementById('repository-export-btn');
  const compendiumBtn = document.getElementById('repository-compendium-btn');

  if (compendiumBtn) {
    compendiumBtn.addEventListener('click', () => {
      window.open('/tpcv/TPCV_MASTER.html', '_blank');
    });
  }
  if (!overlay || !content || !openBtn) return;

  let allEntries = [];

  function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function renderEntries(entries) {
    if (!entries || entries.length === 0) {
      content.innerHTML = '<div class="repository-empty">Repository is empty — Ghost will populate this through research tools.</div>';
      return;
    }
    // Group by section
    const grouped = {};
    for (const e of entries) {
      const sec = e.section || 'Uncategorized';
      if (!grouped[sec]) grouped[sec] = [];
      grouped[sec].push(e);
    }
    let html = '';
    for (const [section, items] of Object.entries(grouped)) {
      html += `<div class="repository-section-heading">${escHtml(section)}</div>`;
      for (const item of items) {
        const statusClass = (item.status || 'draft').toLowerCase();
        const updated = item.updated_at ? new Date(item.updated_at * 1000).toLocaleString() : '—';
        const ccoh = item.c_coh != null ? `C_coh: ${item.c_coh.toFixed(2)}` : '';
        html += `
          <div class="repository-entry">
            <div class="repository-entry-header">
              <span class="repository-entry-id">${escHtml(item.content_id || '—')}</span>
              <span class="repository-status-badge ${escHtml(statusClass)}">${escHtml(item.status || 'draft')}</span>
            </div>
            <div class="repository-entry-content">${formatGhostText(item.content || '')}</div>
            <div class="repository-entry-meta">
              <span>${escHtml(updated)}</span>
              ${ccoh ? `<span>${escHtml(ccoh)}</span>` : ''}
            </div>
          </div>`;
      }
    }
    content.innerHTML = html;
  }

  async function loadRepository(keyword) {
    try {
      let url = `${API_BASE}/ghost/repository`;
      if (keyword) url += `?keyword=${encodeURIComponent(keyword)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allEntries = data.entries || [];
      renderEntries(allEntries);
    } catch (err) {
      content.innerHTML = `<div class="repository-empty">Failed to load repository: ${escHtml(String(err))}</div>`;
    }
  }

  function openPanel() {
    overlay.style.display = 'flex';
    loadRepository();
  }

  function closePanel() {
    overlay.style.display = 'none';
  }

  openBtn.addEventListener('click', openPanel);
  if (closeBtn) closeBtn.addEventListener('click', closePanel);

  // Close on overlay click (outside panel)
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closePanel();
  });

  // Search with debounce
  let searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        const kw = searchInput.value.trim();
        if (kw) {
          // Client-side filter
          const filtered = allEntries.filter(e =>
            (e.content_id || '').toLowerCase().includes(kw.toLowerCase()) ||
            (e.section || '').toLowerCase().includes(kw.toLowerCase()) ||
            (e.content || '').toLowerCase().includes(kw.toLowerCase())
          );
          renderEntries(filtered);
        } else {
          renderEntries(allEntries);
        }
      }, 250);
    });
  }

  // Export
  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      try {
        const res = await fetch(`${API_BASE}/ghost/repository/export`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'TPCV_Repository.md';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        console.error('Repository export failed:', err);
      }
    });
  }
  // Physics Lab
  if (dom.physicsBtn) {
    dom.physicsBtn.onclick = () => {
      dom.navDropdown.classList.remove('active');
      dom.hamburgerBtn.classList.remove('active');
      dom.physicsOverlay.style.display = 'flex';
      if (!physicsLab.active) {
        physicsLab.init(dom.physicsCanvasContainer);
      }
    };
  }
  if (dom.physicsCloseBtn) {
    dom.physicsCloseBtn.onclick = () => {
      dom.physicsOverlay.style.display = 'none';
    };
  }

  // Handle Physics Results
  window.handlePhysicsResult = (result) => {
    if (!result) return;
    
    // Show overlay if hidden
    dom.physicsOverlay.style.display = 'flex';
    if (!physicsLab.active) {
      physicsLab.init(dom.physicsCanvasContainer);
    }
    
    // Update UI
    if (dom.physicsStatus) {
      dom.physicsStatus.textContent = result.status === 'success' ? 'SIMULATION COMPLETE' : 'ERROR';
    }
    if (dom.physicsLog) {
      dom.physicsLog.textContent = result.summary || result.message || 'Processing hypothesis...';
    }
    
    // Run visual
    physicsLab.runScenario(result);
  };
})();
