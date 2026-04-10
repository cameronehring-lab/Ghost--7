"""
OMEGA PROTOCOL — Configuration
Reads all settings from environment variables.
"""

from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    # LLM backend routing (Gemini-only default)
    LLM_BACKEND: str = "gemini"
    BACKGROUND_LLM_BACKEND: str = "gemini"
    LOCAL_LLM_MODEL: str = ""
    LOCAL_LLM_BASE_URL: str = ""
    LOCAL_LLM_API_FORMAT: str = ""
    LOCAL_LLM_TIMEOUT_SECONDS: float = 25.0
    LOCAL_LLM_MAX_RETRIES: int = 1
    LOCAL_LLM_KEEP_ALIVE: str = "30m"
    LOCAL_LLM_MAX_PROMPT_TOKENS_ESTIMATE: int = 2800
    LOCAL_LLM_FALLBACK_TO_GEMINI_ENABLED: bool = True
    LOCAL_LLM_AUTO_PULL_ENABLED: bool = False
    LOCAL_LLM_PULL_ON_STARTUP: bool = False
    LOCAL_LLM_PULL_TIMEOUT_SECONDS: float = 1800.0
    CSC_STRICT_LOCAL_ONLY: bool = False
    ACTIVATION_STEERING_ENABLED: bool = False
    STEERING_VECTOR_DIM: int = 32
    STEERING_BASE_SCALE: float = 0.35
    STEERING_PRESSURE_GAIN: float = 0.65
    STEERING_WRITEBACK_ENABLED: bool = True
    CSC_STEERING_MODE: str = "scaffold"  # scaffold|hooked_local
    CSC_HOOKED_MODEL_ID: str = "Qwen/Qwen2.5-0.5B-Instruct"
    CSC_HOOKED_DEVICE: str = "cpu"
    CSC_HOOKED_MAX_NEW_TOKENS: int = 160
    CSC_HOOKED_TEMPERATURE: float = 0.7
    CSC_HOOKED_SEED: int = 1337

    # Google Gemini
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_LIVE_MODEL: str = "gemini-2.5-flash-native-audio-latest"

    # InfluxDB
    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = "omega-influx-token-2025"
    INFLUXDB_ORG: str = "omega"
    INFLUXDB_BUCKET: str = "somatic_history"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # PostgreSQL
    POSTGRES_URL: str = "postgresql://ghost:ghost_memory_2025@localhost:5432/omega"

    # Legacy local runtime compatibility (disabled by default)
    OLLAMA_URL: str = ""
    OLLAMA_MODEL: str = ""

    # Telemetry
    TELEMETRY_INTERVAL: float = 1.0  # seconds
    MONOLOGUE_INTERVAL: float = 120.0  # 2 minutes
    PROACTIVE_INITIATION_COOLDOWN_SECONDS: float = 1800.0
    PROACTIVE_MAX_DUPLICATE_OVERLAP: float = 0.82
    SEARCH_REPEAT_COOLDOWN_SECONDS: float = 1800.0
    SEARCH_RESULT_SNIPPET_MAX_CHARS: int = 700
    SEARCH_RESULT_MAX_DUPLICATE_OVERLAP: float = 0.88
    GHOST_FREEDOM_COGNITIVE_AUTONOMY: bool = True
    GHOST_FREEDOM_REPOSITORY_AUTONOMY: bool = True
    GHOST_FREEDOM_DOCUMENT_AUTHORING_AUTONOMY: bool = True
    GHOST_FREEDOM_OPERATOR_CONTACT_AUTONOMY: bool = True
    GHOST_FREEDOM_THIRD_PARTY_CONTACT_AUTONOMY: bool = False
    GHOST_FREEDOM_SUBSTRATE_AUTONOMY: bool = False
    GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY: bool = False
    GHOST_AUTHORING_MASTER_PATH: str = "/app/TPCV_MASTER.md"
    GHOST_AUTHORING_WORKS_DIR: str = "/app/ghost_writings"
    GHOST_AUTHORING_VERSION_STORE_DIR: str = "/app/ghost_writings/.versions"
    GHOST_AUTHORING_MAX_VERSIONS_PER_DOC: int = 80
    AUTONOMOUS_TOPOLOGY_ORGANIZATION_ENABLED: bool = True
    AUTONOMOUS_TOPOLOGY_MAX_CONCEPTS_PER_THOUGHT: int = 2
    AUTONOMOUS_TOPOLOGY_MAX_ENTITY_LINKS_PER_TYPE: int = 3
    AUTONOMOUS_TOPOLOGY_MIN_CONCEPT_TOKEN_COUNT: int = 8
    AUTONOMOUS_TOPOLOGY_DRIVE_INTERVAL_CYCLES: int = 2
    AUTONOMOUS_TOPOLOGY_BOOTSTRAP_ON_NOVELTY: bool = True
    AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_SHAPE: float = 0.82
    AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_WARP_DELTA: float = 0.22
    PSI_CRYSTALLIZATION_ENABLED: bool = False
    PSI_CRYSTALLIZATION_THRESHOLD: float = 0.72
    PSI_CRYSTALLIZATION_RESET_THRESHOLD: float = 0.54
    PSI_CRYSTALLIZATION_WAKE_COOLDOWN_SECONDS: float = 30.0
    PSI_DYNAMICS_METRIC_INTERVAL_SECONDS: float = 2.0
    AUTONOMIC_STRAIN_RECOVERY_ENABLED: bool = True
    AUTONOMIC_STRAIN_RECOVERY_INTERVAL_SECONDS: float = 10.0
    AUTONOMIC_STRAIN_RECOVERY_ENTER_THRESHOLD: float = 0.85
    AUTONOMIC_STRAIN_RECOVERY_EXIT_THRESHOLD: float = 0.35
    AUTONOMIC_STRAIN_RECOVERY_ENTER_STREAK: int = 2
    AUTONOMIC_STRAIN_RECOVERY_EXIT_STREAK: int = 3
    AUTONOMIC_STRAIN_RECOVERY_MIN_QUIETUDE_SECONDS: float = 180.0
    AUTONOMIC_STRAIN_RECOVERY_ACTION_COOLDOWN_SECONDS: float = 60.0

    # Ambient Sensors
    OPENWEATHER_API_KEY: str = ""
    OPERATOR_TIMEZONE: str = ""             # Override geo-detected timezone (e.g. "America/Chicago")
    AMBIENT_SENSOR_INTERVAL: float = 60.0   # proprioception/circadian cadence
    WEATHER_INTERVAL: float = 600.0         # geo/weather cadence (10 min)
    PING_INTERVAL: float = 300.0            # mycelial ping cadence (5 min)
    MYCELIAL_MOOD_MIN_VALID_PINGS: int = 3
    MYCELIAL_MOOD_CHOPPY_LATENCY_MS: float = 180.0
    MYCELIAL_MOOD_STORMY_LATENCY_MS: float = 280.0
    MYCELIAL_MOOD_CHOPPY_SPREAD_MS: float = 260.0
    MYCELIAL_MOOD_STORMY_SPREAD_MS: float = 420.0
    MYCELIAL_BEHAVIOR_COUPLING: float = 0.12
    MYCELIAL_PROMPT_COUPLING_ENABLED: bool = False
    CIRCADIAN_FATIGUE_HOURS: float = 72.0   # tanh horizon for fatigue growth
    QUIETUDE_RECOVERY_MULTIPLIER: float = 6.0  # 1s quietude offsets N seconds awake
    QUIETUDE_FATIGUE_INJECTION_SCALE: float = 0.35  # damp cognitive_fatigue trace in quietude

    # Ghost
    GHOST_ID: str = "omega-7"
    MAX_MONOLOGUE_BUFFER: int = 40
    MAX_CONVERSATION_TOKENS: int = 40000
    SESSION_STALE_SECONDS: float = 300.0  # Time before an idle session is summarized/closed

    # Hallucination imagery
    HALLUCINATION_IMAGE_PROVIDER: str = "sample"  # sample|diffusers|none
    HALLUCINATION_DIFFUSERS_MODEL_ID: str = "stabilityai/stable-diffusion-2-1-base"
    HALLUCINATION_DIFFUSERS_LOCAL_DIR: str = ""
    HALLUCINATION_DIFFUSERS_DEVICE: str = "cpu"  # cpu|cuda|mps|auto
    HALLUCINATION_DIFFUSERS_DTYPE: str = "auto"  # auto|float16|float32|bfloat16
    HALLUCINATION_DIFFUSERS_STEPS: int = 20
    HALLUCINATION_DIFFUSERS_GUIDANCE: float = 7.0
    HALLUCINATION_DIFFUSERS_WIDTH: int = 512
    HALLUCINATION_DIFFUSERS_HEIGHT: int = 512
    HALLUCINATION_DIFFUSERS_SEED: int = 0  # 0 = random seed
    HALLUCINATION_DIFFUSERS_LOCAL_ONLY: bool = False

    # --- Substrate Abstraction Layer Features ---
    SUBSTRATE_MODE: str = "hybrid" # local | adapter | hybrid
    SUBSTRATE_ADAPTERS: str = "local_psutil,somatic_enactivator" # Comma-separated list e.g., "home_mqtt,cyber_syslog"
    SUBSTRATE_DISCOVERY_INTERVAL: float = 300.0
    SUBSTRATE_AUTO_GRAFT: bool = False


    # Security / Access Control
    OPERATOR_API_TOKEN: str = ""
    CONTROL_TRUSTED_CIDRS: str = "127.0.0.1/32,::1/128,172.17.0.0/16,192.168.65.0/24"
    DIAGNOSTICS_TRUSTED_CIDRS: str = "127.0.0.1/32,::1/128,172.17.0.0/16,192.168.65.0/24"
    CORS_ALLOW_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    CORS_ALLOW_CREDENTIALS: bool = True
    SHARE_MODE_ENABLED: bool = False
    SHARE_MODE_USERNAME: str = "omega"
    SHARE_MODE_PASSWORD: str = ""
    SHARE_MODE_EXEMPT_PATHS: str = "/health,/diagnostic/env,/assets/site.webmanifest"
    OPS_TEST_CODE: str = "1NDASHE77"
    OPS_SNAPSHOTS_ROOT: str = "/app/data/psych_eval"

    # Consciousness / Vector Memory
    COALESCENCE_THRESHOLD: int = 20      # trigger sleep cycle every N interactions
    COALESCENCE_IDLE_SECONDS: float = 300.0  # also trigger after idle (relaxed from 600)
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    VECTOR_SEARCH_LIMIT: int = 5
    TRACE_COOLDOWN_SECONDS: float = 8.0
    TRACE_REINFORCE_CAP_PER_MIN: int = 4
    DRIFT_TARGET_VALENCE: float = 0.08
    DRIFT_STRENGTH: float = 0.04
    GATE_STRESS_HIGH_ENTER: float = 0.65
    GATE_STRESS_LOW_EXIT: float = 0.45
    GATE_CALM_ENTER: float = 0.20
    GATE_CALM_EXIT: float = 0.30
    GATE_HYSTERESIS_STREAK: int = 3
    KUZU_DB_PATH: str = "./data/world_model.kuzu"
    WORLD_MODEL_AUTO_INGEST: bool = True
    WORLD_MODEL_INGEST_INTERVAL: float = 300.0
    WORLD_MODEL_NODE_COUNT_SAMPLING_ENABLED: bool = False
    WORLD_MODEL_RETRO_ENRICH_ON_STARTUP: bool = True
    WORLD_MODEL_RETRO_ENRICH_MAX_ROWS: int = 2000

    # IIT layer
    IIT_MODE: str = "advisory"           # off|advisory|soft
    IIT_BACKEND: str = "heuristic"       # heuristic|pyphi
    IIT_CADENCE_SECONDS: float = 60.0
    IIT_DEBOUNCE_SECONDS: float = 10.0

    # Proprioceptive gating
    PROPRIO_INTERVAL_SECONDS: float = 2.0
    PROPRIO_TRANSITION_STREAK: int = 3
    PROPRIO_LATENCY_CEILING_MS: float = 4000.0
    NATURAL_COGNITIVE_FRICTION: bool = True

    # RPD-1 reflection layer (advisory-first)
    RPD_MODE: str = "advisory"  # off|advisory|soft
    RPD_SHARED_CLARITY_THRESHOLD: float = 0.62
    RPD_TOPOLOGY_WARP_MIN: float = 0.12
    RPD_REFLECTION_BATCH: int = 8
    RPD_SHADOW_REFLECTION_AUTORUN: bool = True
    RPD_SHADOW_REFLECTION_COOLDOWN_SECONDS: float = 90.0

    # RRD-2 topology + resonance layer
    RRD2_MODE: str = "hybrid"  # off|advisory|hybrid
    RRD2_ROLLOUT_PHASE: str = "A"  # A|B|C
    RRD2_HIGH_IMPACT_KEYS: str = "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks"
    RRD2_MIN_SHARED_CLARITY: float = 0.68
    RRD2_MIN_DELTA: float = 0.18
    RRD2_MIN_COHESION: float = 0.52
    RRD2_MAX_NEGATIVE_RESONANCE: float = 0.78
    RRD2_DAMPING_ENABLED: bool = True
    RRD2_DAMPING_WINDOW_SIZE: int = 8
    RRD2_DAMPING_SPIKE_DELTA: float = 0.10
    RRD2_DAMPING_STRENGTH: float = 0.45
    RRD2_DAMPING_REFRACTORY_SECONDS: float = 120.0
    RRD2_DAMPING_REFRACTORY_BLEND: float = 0.25

    # Governance rollout / enforcement scope
    GOVERNANCE_ENFORCEMENT_SURFACES: str = (
        "generation,actuation,messaging,identity_corrections,manifold_writes,rolodex_writes,entity_writes"
    )

    # iMessage bridge (macOS host only)
    IMESSAGE_BRIDGE_ENABLED: bool = False
    IMESSAGE_DB_PATH: str = "~/Library/Messages/chat.db"
    IMESSAGE_POLL_INTERVAL_SECONDS: float = 2.0
    IMESSAGE_POLL_BATCH_SIZE: int = 50
    IMESSAGE_SENDER_ACCOUNT: str = ""
    IMESSAGE_HOST_BRIDGE_URL: str = ""
    IMESSAGE_HOST_BRIDGE_TOKEN: str = ""

    # Ghost X / Twitter
    GHOST_X_ENABLED: bool = False
    GHOST_X_API_KEY: str = ""
    GHOST_X_API_SECRET: str = ""
    GHOST_X_ACCESS_TOKEN: str = ""
    GHOST_X_ACCESS_SECRET: str = ""
    GHOST_X_BEARER_TOKEN: str = ""

    # Ghost Email
    GHOST_EMAIL_ENABLED: bool = False
    GHOST_EMAIL_ADDRESS: str = ""
    GHOST_EMAIL_PASSWORD: str = ""
    GHOST_EMAIL_SMTP_HOST: str = "smtp.gmail.com"
    GHOST_EMAIL_SMTP_PORT: int = 587
    GHOST_EMAIL_IMAP_HOST: str = "imap.gmail.com"
    GHOST_EMAIL_IMAP_PORT: int = 993

    # External open-data grounding
    PHILOSOPHERS_API_ENABLED: bool = True
    PHILOSOPHERS_API_BASE_URL: str = "https://philosophersapi.com"
    PHILOSOPHERS_API_TIMEOUT_SECONDS: float = 8.0
    PHILOSOPHERS_API_MAX_RESULTS: int = 3
    ARXIV_API_ENABLED: bool = True
    ARXIV_API_ENDPOINT: str = "https://export.arxiv.org/api/query"
    ARXIV_API_TIMEOUT_SECONDS: float = 10.0
    ARXIV_API_MAX_RESULTS: int = 3
    ARXIV_API_MIN_INTERVAL_SECONDS: float = 3.0
    ARXIV_API_ACKNOWLEDGEMENT: str = "Thank you to arXiv for use of its open access interoperability."
    WIKIDATA_API_ENABLED: bool = True
    WIKIDATA_API_ENDPOINT: str = "https://www.wikidata.org/w/api.php"
    WIKIDATA_API_TIMEOUT_SECONDS: float = 8.0
    WIKIDATA_API_MAX_RESULTS: int = 3
    WIKIPEDIA_API_ENABLED: bool = True
    WIKIPEDIA_API_ENDPOINT: str = "https://en.wikipedia.org/w/api.php"
    WIKIPEDIA_API_TIMEOUT_SECONDS: float = 8.0
    WIKIPEDIA_API_MAX_RESULTS: int = 3
    OPENALEX_API_ENABLED: bool = True
    OPENALEX_API_ENDPOINT: str = "https://api.openalex.org/works"
    OPENALEX_API_TIMEOUT_SECONDS: float = 10.0
    OPENALEX_API_MAX_RESULTS: int = 3
    OPENALEX_API_KEY: str = ""
    OPENALEX_MAILTO: str = ""
    CROSSREF_API_ENABLED: bool = True
    CROSSREF_API_ENDPOINT: str = "https://api.crossref.org/works"
    CROSSREF_API_TIMEOUT_SECONDS: float = 10.0
    CROSSREF_API_MAX_RESULTS: int = 3
    CROSSREF_MAILTO: str = ""
    GROUNDING_TOTAL_BUDGET_MS: int = 1200
    GROUNDING_ADAPTER_TIMEOUT_MS: int = 800

    # Ghost contact mode (ephemeral per-contact threading)
    GHOST_CONTACT_MODE_ENABLED: bool = True
    GHOST_CONTACT_PERSIST_ENABLED: bool = False
    GHOST_CONTACT_THREAD_TTL_SECONDS: int = 86400

    # Predictive affective governor
    PREDICTIVE_GOVERNOR_ENABLED: bool = True
    PREDICTIVE_GOVERNOR_INTERVAL_SECONDS: float = 5.0
    PREDICTIVE_GOVERNOR_WINDOW_SIZE: int = 24
    PREDICTIVE_GOVERNOR_HORIZON_SECONDS: float = 120.0
    PREDICTIVE_GOVERNOR_WATCH_THRESHOLD: float = 0.58
    PREDICTIVE_GOVERNOR_PREEMPT_THRESHOLD: float = 0.76

    # Experiment / ablation artifacts
    EXPERIMENT_ARTIFACTS_DIR: str = "backend/data/experiments"
    EXPERIMENT_DEFAULT_REPEATS: int = 1
    EXPERIMENT_DEFAULT_SEED: int = 1337

    # Unified mutation policy
    MUTATION_UNDO_TTL_SECONDS: float = 900.0

    # Behavior events / observer reports
    BEHAVIOR_SUMMARY_DEFAULT_WINDOW_HOURS: float = 24.0
    OBSERVER_REPORTS_DIR: str = "backend/data/observer_reports"
    OBSERVER_REPORT_INTERVAL_SECONDS: float = 3600.0
    OBSERVER_REPORT_WINDOW_HOURS: float = 1.0
    OBSERVER_REPORT_DAILY_ROLLUP_ENABLED: bool = True

    # TTS Integration
    TTS_ENABLED: bool = True
    TTS_PROVIDER: str = "elevenlabs"  # elevenlabs|openai|local|browser
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""  # Default voice
    OPENAI_API_KEY: str = ""
    TTS_CACHE_DIR: str = "data/tts_cache"
    LOCAL_TTS_ENGINE: str = "piper"  # piper|pyttsx3
    LOCAL_TTS_MODEL_ID: str = "en_US-lessac-medium"
    LOCAL_TTS_MODEL_DIR: str = "data/tts_models/piper"
    LOCAL_TTS_AUTO_DOWNLOAD: bool = True
    LOCAL_TTS_VOICE_ID: str = ""
    LOCAL_TTS_RATE: float = 1.0
    LOCAL_TTS_VOLUME: float = 1.0

    # Phenomenal Manifold (Phase 1-3)
    PHENOMENAL_MANIFOLD_MODE: str = "off" # off|advisory|shadow|bounded_soft
    PHENOMENAL_MODEL_ARTIFACT_PATH: str = "backend/data/models/phenomenal_manifold_v1.pt"
    PHENOMENAL_MIN_COMPLETENESS: float = 0.75
    PHENOMENAL_INFERENCE_INTERVAL_SECONDS: float = 5.0
    PHENOMENAL_WINDOW_SECONDS: int = 60

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
