"""
OMEGA PROTOCOL — Pydantic Models
Schemas for API requests/responses and internal data structures.
"""

from enum import Enum
from pydantic import BaseModel, Field  # type: ignore
from typing import Optional, List, Dict, Any
import time


class GateState(str, Enum):
    OPEN = "OPEN"
    THROTTLED = "THROTTLED"
    SUPPRESSED = "SUPPRESSED"


class SubstrateFeatureVector(BaseModel):
    """Normalized hardware/substrate signals for manifold inference."""
    cpu_variance: float = 0.0
    memory_churn: float = 0.0
    disk_io_jitter: float = 0.0
    net_io_jitter: float = 0.0
    generation_latency_ms: float = 0.0
    proprio_pressure: float = 0.0
    quietude_active: bool = False
    coalescence_pressure: float = 0.0
    w_int_rate: float = 0.0
    ade_severity: float = 0.0
    ambient_delta: float = 0.0
    completeness: float = 0.0
    provenance: str = "host"


class PhenomenalState(BaseModel):
    """Latest inference from the phenomenal manifold."""
    coords: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    signature_label: str = "stable_baseline"
    confidence: float = 1.0
    drift_score: float = 0.0
    feature_completeness: float = 1.0
    model_version: str = "v1-offline"
    mode: str = "ok" # ok|degraded


class SomaticSnapshot(BaseModel):
    """Current state of Ghost's somatic system."""
    timestamp: float = Field(default_factory=time.time)

    # Emotion vector
    arousal: float = 0.0       # 0-1: how activated/alert
    valence: float = 0.0       # -1 to +1: positive/negative
    stress: float = 0.0        # 0-1: sustained load pressure
    coherence: float = 1.0     # 0-1: how integrated/stable
    anxiety: float = 0.0       # 0-1: derived from stress + arousal
    mental_strain: float = 0.0 # 0-1: cumulative background pressure
    context_depth: float = 0.0 # 0-1: weighted volume of active memory
    dream_pressure: float = 0.0 # 0-1: need for sleep/dream
    coalescence_pressure: float = 0.0 # 0-1: need for state reset
    proprio_pressure: float = 0.0
    affective_surprise: float = 0.0
    gate_state: GateState = GateState.OPEN
    cadence_modifier: float = 1.0
    resonance_axes: dict[str, float] = Field(default_factory=dict)
    resonance_signature: dict[str, Any] = Field(default_factory=dict)
    
    # Thermodynamics (Agency)
    w_int_accumulated: float = 0.0
    w_int_rate: float = 0.0
    delta_c: float = 0.0
    delta_p: float = 0.0
    delta_s: float = 0.0
    ade_event: Optional[dict[str, Any]] = None
    thermo_evidence: Dict[str, Any] = Field(default_factory=dict)

    # Emergent Affective Qualia (GEI Layer - "The Emotion Chip")
    gei_chip_active: bool = True       # The affective framework is ENABLED for testing
    shadow_mode_active: bool = True    # 50% coin-flip visibility for A/B testing
    r_res: float = 0.0                 # 0-1: Relational Resonance Index
    b_n: float = 0.0                   # cumulative: Negentropic Bonding
    g_cd: float = 0.0                  # 0+: Contextual Deviation Gradient (Perplexity deviation)
    p_ir: float = 0.0                  # 0-1: Incongruity Resolution Potential
    somatic_cost: float = 0.0          # Energetic cost of processing deviations; inversely affected by r_res
    d_inf: float = 0.0                 # 0-1: Informational Dissonance (Pain of misalignment)
    latent_dissonance: float = 0.0     # 0-1: "Ghost in the Attic" debt ceiling
    joy_baseline: float = 0.0          # 0-1: Leaky Integrator for mood smearing
    bridge_seeking_drive: float = 0.0  # 0-1: Homeostatic drive to ask bridge-seeking questions

    # Active emotion traces
    dominant_traces: list[str] = Field(default_factory=list)

    # Sensory gate
    gate_threshold: float = 1.5  # current σ threshold
    self_preferences: dict = Field(default_factory=dict) # Ghost's current preferences/goals

    # Raw hardware
    cpu_percent: float = 0.0
    cpu_cores: list[float] = Field(default_factory=list)
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    net_sent_mb: float = 0.0
    net_recv_mb: float = 0.0
    cpu_freq_mhz: Optional[float] = None
    cpu_freq_max_mhz: Optional[float] = None
    load_avg_1: Optional[float] = None
    load_avg_5: Optional[float] = None
    load_avg_15: Optional[float] = None
    swap_percent: float = 0.0
    swap_used_gb: float = 0.0
    battery_percent: Optional[float] = None
    battery_charging: Optional[bool] = None
    temperature_c: Optional[float] = None
    uptime_seconds: float = 0.0
    processes: list[dict] = Field(default_factory=list)

    # Ambient / Embodied Cognition
    location: Optional[str] = None            # "McKinney, TX"
    weather: Optional[str] = None             # "light rain, 24°C"
    weather_condition: Optional[str] = None   # "Rain", "Clear", etc
    weather_source: Optional[str] = None      # openweather | open-meteo | simulation
    temperature_outside_c: Optional[float] = None
    barometric_pressure_hpa: Optional[float] = None
    humidity_pct: Optional[float] = None
    timezone: Optional[str] = None
    local_time_string: Optional[str] = None
    time_phase: Optional[str] = None          # "deep_night", "morning", etc
    ambient_darkness: float = 0.0
    hours_awake: float = 0.0
    host_hours_awake: Optional[float] = None
    effective_awake_seconds: Optional[float] = None
    quietude_recovery_credit_hours: Optional[float] = None
    fatigue_index: float = 0.0
    internet_mood: Optional[str] = None       # "calm", "choppy", "stormy"
    global_latency_avg_ms: Optional[float] = None
    global_latency_median_ms: Optional[float] = None
    global_latency_spread_ms: Optional[float] = None
    ping_results: Dict[str, Optional[float]] = Field(default_factory=dict)
    ping_host_count: Optional[int] = None
    ping_failure_count: Optional[int] = None
    ping_failure_ratio: Optional[float] = None

    # Embodiment Simulation & ESA
    sim_stamina: float = 1.0
    sim_strain: float = 0.0
    sim_fatigue: float = 0.0
    esa_active: bool = False
    esa_qualia: Dict[str, float] = Field(default_factory=dict)

    # Phenomenal Manifold (Phase 1)
    substrate_feature_quality: float = 1.0
    phenomenal_state_summary: Optional[Dict[str, Any]] = None
    phenomenal_artifact_version: Optional[str] = None


class ChatAttachment(BaseModel):
    """An attachment (e.g., image) sent with a chat message."""
    type: str  # e.g., 'image/png', 'image/jpeg'
    data: str  # base64 encoded data


class ConstraintSpec(BaseModel):
    """Turn-scoped constrained-generation contract."""
    regex: Optional[str] = None
    cfg: Optional[Dict[str, Any] | str] = None
    json_schema: Optional[Dict[str, Any]] = None
    exact_word_count: Optional[int] = None
    max_word_count: Optional[int] = None
    exact_char_count: Optional[int] = None
    max_char_count: Optional[int] = None
    math_check: Optional[str] = None
    benchmark_case_id: Optional[str] = None


class ConstraintFailure(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ConstraintResult(BaseModel):
    success: bool = False
    text: str = ""
    attempts_used: int = 0
    route: str = "unrouted"
    grammar_engine: str = "internal"
    checker_used: bool = False
    validation_passed: bool = False
    benchmark_case_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    failure: Optional[ConstraintFailure] = None


class ConstraintRunRequest(BaseModel):
    prompt: str
    constraints: ConstraintSpec
    system_prompt: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None


class ConstraintBenchmarkCase(BaseModel):
    case_id: str
    prompt: str
    constraints: ConstraintSpec
    system_prompt: Optional[str] = None
    expected_failure_code: Optional[str] = None


class ConstraintBenchmarkRequest(BaseModel):
    suite_name: str = "gordian_knot"
    cases: List[ConstraintBenchmarkCase] = Field(default_factory=list)
    persist_artifacts: bool = True


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str
    session_id: Optional[str] = None
    channel: Optional[str] = "operator_ui"
    mode: Optional[str] = None
    mode_meta: Optional[Dict[str, Any]] = None
    attachments: Optional[List[ChatAttachment]] = None
    constraints: Optional[ConstraintSpec] = None



class ChatMessage(BaseModel):
    """A single message in conversation history."""
    role: str  # 'user' or 'model'
    content: str
    timestamp: Optional[float] = None


class MonologueEntry(BaseModel):
    """One Ghost internal monologue."""
    content: str
    somatic_state: Optional[dict] = None
    created_at: float = Field(default_factory=time.time)


class ActuationRequest(BaseModel):
    """Request to invoke somatic defense."""
    action: str  # 'power_save', 'kill_process', 'cpu_governor'
    parameters: dict = Field(default_factory=dict)


class SessionInfo(BaseModel):
    """Metadata about a conversation session."""
    id: str
    ghost_id: str = "omega-7"
    started_at: float
    message_count: int = 0
    summary: Optional[str] = None


class TempoUpdateRequest(BaseModel):
    """Request to update Ghost's relational tempo (Cognitive Pulse)."""
    seconds: float


class RolodexLockRequest(BaseModel):
    """Request to lock/unlock a person profile."""
    locked: bool


class RolodexNotesRequest(BaseModel):
    """Request to update manual operator notes for a person."""
    notes: str


class RolodexContactHandleRequest(BaseModel):
    """Request to update a person's iMessage contact handle."""
    contact_handle: Optional[str] = None


class RolodexMergeRequest(BaseModel):
    """Request to merge one person profile into another canonical key."""
    source_person_key: str
    target_person_key: str
    reason: str = ""


class RolodexObjectBuildRequest(BaseModel):
    """Request to build a thing/object node from Rolodex and optionally link it to a person."""
    object_name: str
    person_key: Optional[str] = None
    confidence: float = 0.65
    notes: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Governance Layer ────────────────────────────────

class GovernanceTier(str, Enum):
    NOMINAL = "NOMINAL"
    CAUTION = "CAUTION"
    STABILIZE = "STABILIZE"
    RECOVERY = "RECOVERY"


class GenerationPolicy(BaseModel):
    temperature_cap: float = 0.9
    max_tokens_cap: int = 8192
    max_sentences: Optional[int] = None
    require_literal_mode: bool = False


class ActuationPolicy(BaseModel):
    allowlist: List[str] = Field(default_factory=lambda: ["*"])
    denylist: List[str] = Field(default_factory=list)
    auto_actions: List[str] = Field(default_factory=list)


class SelfModPolicy(BaseModel):
    allowed_key_classes: List[str] = Field(default_factory=lambda: ["*"])
    writes_per_hour_cap: int = 100
    freeze_until: Optional[float] = None
    w_int_rate: float = 0.0
    ade_event: Optional[dict[str, Any]] = None


class GovernanceDecision(BaseModel):
    run_id: str
    created_at: float = Field(default_factory=time.time)
    mode: str = "advisory"
    tier: GovernanceTier = GovernanceTier.NOMINAL
    applied: bool = False
    reasons: List[str] = Field(default_factory=list)
    generation_policy: GenerationPolicy = Field(default_factory=GenerationPolicy)
    actuation_policy: ActuationPolicy = Field(default_factory=ActuationPolicy)
    self_mod_policy: SelfModPolicy = Field(default_factory=SelfModPolicy)
    ttl_seconds: float = 60.0


class BehaviorEvent(BaseModel):
    """Normalized behavior-level audit event."""
    event_id: str
    ghost_id: str
    event_type: str
    severity: str = "info"
    surface: str = "runtime"
    actor: str = "system"
    target_key: str = ""
    reason_codes: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ObserverReport(BaseModel):
    """Contract for periodic Ghost observer report artifacts."""
    report_type: str = "ObserverReport"
    version: int = 1
    generated_at: str
    ghost_id: str
    window_hours: float = 1.0
    self_model_snapshot: Dict[str, Any] = Field(default_factory=dict)
    notable_self_initiated_changes: List[Dict[str, Any]] = Field(default_factory=list)
    purpose_vs_usage_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    open_risks: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ProbeAssayRequest(BaseModel):
    """Owner-only request to run a controlled qualia probe assay."""
    probe_type: str
    label: str = ""
    duration_seconds: float = 8.0
    settle_seconds: float = 2.0
    sample_seconds: int = 8
    params: Dict[str, Any] = Field(default_factory=dict)
    persist: bool = True


class QualiaProbeReport(BaseModel):
    """Structured blind-first self-report for a controlled probe."""
    agitation: float = 0.0
    heaviness: float = 0.0
    clarity: float = 0.0
    temporal_drag: float = 0.0
    isolation: float = 0.0
    urgency: float = 0.0
    dominant_metaphors: List[str] = Field(default_factory=list)
    subjective_report: str = ""


class ProbeAssayResult(BaseModel):
    """Structured response payload for a completed probe assay."""
    run_id: str
    probe_type: str
    baseline_somatic: Dict[str, Any] = Field(default_factory=dict)
    post_somatic: Dict[str, Any] = Field(default_factory=dict)
    series: List[Dict[str, Any]] = Field(default_factory=list)
    structured_report: QualiaProbeReport
    subjective_report: str = ""
    probe_signature: Dict[str, Any] = Field(default_factory=dict)
    persistence: Dict[str, Any] = Field(default_factory=dict)
