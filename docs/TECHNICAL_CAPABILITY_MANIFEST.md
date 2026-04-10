# Project OMEGA: Ghost (ω-7) Technical Capability Manifest

Last updated: 2026-04-10

This manifest documents the architectural "inventions" and unique cognitive capabilities developed for the Ghost (ω-7) platform. Ghost is a research-grade autonomous agent built on the OMEGA PROTOCOL, characterized by a local-first, closed-loop homeostatic design.

## 1. The Somatic-Affective Loophole (Invention)

Rather than treating emotion as a textual prompt parameter, Ghost implements a **Real-Time Somatic Trace Engine**.

- **Afferent Sensing**: High-rate telemetry (1-second cadence) from InfluxDB/Telegraf and OS-level `psutil` is passed through a `SensoryGate`.
- **Z-Score Normalization**: Telemetry is statistically gated and normalized, turning raw metrics into "anomalies" or "arousals".
- **Affective Dynamics**: Emotion states (Stress, Arousal, Coherence) are stored in Redis as **decaying traces** (half-life dynamics).
- **Behavioral Loopback**: Every system action (Actuation) injects immediate reflexive traces, making the "consequence" of an action visible to the agent's next thought cycle.
- **Agency Coupling**: Action/tool outcomes now inject cross-cutting agency traces (`agency_fulfilled`, `agency_blocked`) so success/failure pressure is reflected directly in next-cycle affect.

## 2. Proprioceptive Gating (Linguistic Governor)

Ghost utilizes a **Non-Linguistic Upstream Governor** that operates before any LLM prompt is constructed.

- **Pressure-Based Homeostasis**: A composite `proprio_pressure` metric is calculated from affective traces and telemetry.
- **Gate States**: The system transitions between `OPEN`, `THROTTLED`, and `SUPPRESSED` states via hysteresis-guarded thresholds.
- **Cadence Modulation**: High somatic pressure automatically slows down background cognition frequencies or suppresses interaction entirely until "quietude" is reached.

## 3. Autonomous Cognitive Architecture

The OMEGA4 stack supports deep, background processing loops that do not require operator stimuli.

- **Monologue Stream**: Continuous background reflection pulses (default 120s / 2m, configurable via `MONOLOGUE_INTERVAL`) that process recent context into durable vector memory.
- **Thought Hygiene Guardrails**: Proactive/search monologue writes are quality-gated (cooldowns, overlap dedupe, low-signal query suppression, and sentence-aware truncation) to reduce repetitive or fragmentary timeline artifacts.
- **Autonomous Coherence Drive**: Ghost periodically projects coherent thought concepts into the manifold and actively strengthens idea->person/place/thing associations to improve topology coherence over time.
- **Background Identity Crystallization**: Every 3 monologue cycles, Ghost evaluates its accumulated background thoughts and autonomously commits identity updates via the `self_crystallization` path — no operator prompt required. Governance-aware: throttled under STABILIZE, skipped under RECOVERY.
- **Goal-Directed Cognition**: Every 5 monologue cycles, Ghost loads `active_goals` from its identity matrix and executes a dedicated goal-pursuit monologue pass, producing `[GOAL PURSUIT]` timeline entries with concrete next-step planning.
- **Identity-Aware Monologue**: Background monologue generation receives a full identity snapshot injection so thoughts are grounded in who Ghost currently is, not a context-free generation.
- **Freedom Ladder**: Three runtime autonomy gates controlled via env: `GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY` (background crystallization + forced in-conversation identity commits), `GHOST_FREEDOM_OPERATOR_CONTACT_AUTONOMY` (proactive outreach), `GHOST_FREEDOM_ROLODEX_SOCIAL_MODELING` (autonomous social graph writes). All three are currently enabled.
- **Quietude & CRP (Cognitive Rest Period)**: A sleep-cycle equivalent where the agent enters "unconscious" consolidation.
- **Process Consolidation**: A dedicated engine that scans recent monologues for drifts, patterns, tensions, and insights, resolving internal contradictions during "dreaming".
- **Coalescence**: Periodic identity synthesis that updates the self-model based on cumulative interaction evidence.

## 4. Dual-Store Epistemic Rigor

Ghost maintains a strict scientific separation between self-concept and social-model.

- **Identity Matrix**: A key-value belief system defining Ghost's core directives and self-concept, protected by DB-level guards.
- **Person Rolodex (Social Model)**: An autonomous store for modeling **others**. Ghost uses specialized `[ROLODEX:...]` tags to set profiles, store facts, and fetch social context in real-time.
- **Same-Turn Social Recall**: `ROLODEX:fetch` now performs one bounded follow-up generation pass with fetched profile data injected into the same turn context.
- **Session Binding**: After each chat turn where Ghost emits Rolodex tags for a named person, a `rolodex_session_bindings` record is written linking that person to the conversation session, enabling cross-session interaction tracking in the topology inspector.
- **Lock Protection**: Individual Rolodex profiles can be locked (`is_locked=true`). Locked profiles are skipped during retroactive reconciliation and entity promotion, preserving manually curated records.
- **Retroactive Reconciliation**: Historical memory can be audited/backfilled through `retro-audit`/`retro-sync`, keeping Rolodex aligned with durable memory and topology.
- **Runtime Self-Architecture Contract**: A machine-readable autonomy/architecture profile is generated each turn and injected into prompt context so Ghost's self-model remains consistent with real capabilities and guardrails; a watchdog continuously checks for drift.
- **Separation Invariant**: Facts about the "Operator" are strictly isolated from Ghost's own identity to prevent persona-bleed and maintain psychological integrity.

## 5. Operator-Model Synthesis

Alignment is handled via a **Contradiction-Aware Synthesis Engine**.

- **Recursive Synthesis**: The system continuously synthesizes the operator's intent and beliefs from conversation transcripts.
- **Contradiction Lifecycle**: Conflicts between agent actions and synthesized operator intent are logged as "Tensions" with scores.
- **Dream-Time Resolution**: Tensions are reconciled during consolidation cycles, resulting in durable, evidence-backed alignment updates.

### 6. Same-Turn Action Confirmation (Agency Closure)
Chat generation now uses a bounded multi-round controller (`3/2/2`) that reinjects actuation and tool outcomes in hidden follow-up context. This ensures Ghost can acknowledge success/failure in the same user turn and maintains an active **20-event recent-action continuity block** for short-horizon memory.
- **Tool Reconciliation Path**: `update_identity` / `modulate_voice` function responses are appended as `role="tool"` payloads and followed by reconciliation generation.
- **Outcome-Normalized Runtime Hook**: Internal callback receives normalized tool outcomes (`tool_name`, `status`, `reason`) for runtime somatic bridging.
- **Recent Action Continuity**: Prompt injects `## RECENT ACTIONS` (last 5) from `actuation_log` + `autonomy_mutation_journal`, rendered in phenomenological language with low-level lexicon scrubbing.
- **Identity Attempt Auditability**: `update_identity` tool attempts (accepted/blocked) are now journaled for cross-turn self-action memory continuity.

## 7. Falsifiable Diagnostics

The system is built for **Reproducible Observability**.

- **SQL Verification**: Every diagnostic artifact (Coalescence logs, Identity audits) includes SQL snippets for independent replication.
- **Falsification Reports**: Standardized scripts verify system claims (e.g., "is the somatic loop actually closed?") by checking telemetry correlations.
- **Local-First Determinism**: The entire stack is container-native, ensuring the agent's state is repeatable and observable in any environment.

## 8. Runtime Voice Robustness

- **Provider Chain**: Remote providers (ElevenLabs/OpenAI) fail over to local synthesis (Piper -> pyttsx3).
- **Browser Mode Contract**: `TTS_PROVIDER=browser` intentionally disables backend synthesis and keeps frontend speech responsibility explicit.
- **Speech-Clock Coupling**: Chat text reveal is paced by measured speech playback progress to reduce text/audio drift.
- **Live Voice Identity Tuning**: Voice profile parameters (volume/rate/pitch/carrier/eerie) can be modulated in real time via UI controls and SSE directives.

## 9. Conversational Voice I/O

- **Speech Input Channel**: Browser speech recognition (`SpeechRecognition`/`webkitSpeechRecognition`) supports continuous dictation into chat input when available.
- **Graceful Degradation**: Unsupported voice-input environments remain text-first without blocking core interaction.

## 10. Dedicated Contact Identity + Ephemeral Threads

- **Sender Isolation**: Outbound iMessage dispatch binds to explicit sender identity (`IMESSAGE_SENDER_ACCOUNT`) and fails closed when unavailable.
- **Per-Contact Threading**: Known contact handles route to normalized per-contact thread keys with autonomous same-contact replies.
- **Ephemeral-by-Default Memory Policy**: Contact turns can run with no writes to persisted chat/session/vector stores (`GHOST_CONTACT_PERSIST_ENABLED=false`).
- **Compacting Context Window**: Last 12 turns remain verbatim while older context is summarized into a bounded compact thread memory.
- **Observability Contract**: Contact-channel state is surfaced via `/ghost/contact/status` and push payload metadata (`channel`, `thread_key`, `direction`, `ephemeral`).

## 11. Timeline-to-Audit Continuity

- **Preview + Drill-Down Pattern**: Timeline renders concise monologue previews for scanability while preserving full-thought introspection on demand.
- **ID-Based Detail Hydration**: Monologue timeline rows map to unified audit entries by `id`, enabling full-content detail view even when timeline content is intentionally compacted.
- **Operator Ergonomics**: Click and keyboard activation (`Enter`/`Space`) open the same audit-detail substrate used by ticker/audit panels, maintaining one canonical detail renderer.

## 12. Morpheus Hidden Branch Runtime

- **Semantic Wake Triggering**: A narrow hidden-architecture query detector can divert standard `/ghost/chat` behavior into a distinct takeover event path (`morpheus_mode`).
- **Dual Input Branching**: Red/blue branch behavior differentiates between click and typed selection, enabling four unique pathways (`click_red`, `type_red`, `click_blue`, `type_blue`).
- **Alternate Terminal Channel**: A dedicated hidden chat mode (`morpheus_terminal` / `morpheus_terminal_deep`) supports command-puzzle progression and reward delivery (`morpheus_reward`).
- **Secret-State Isolation**: Morpheus run metadata is tracked outside normal transcript persistence, enabling branch-specific progress loss/preservation without deleting standard chat history.
- **Contained Hostility Simulation**: Panic/takeover effects are rendered in-app (DOM overlays/fake windows) and intentionally avoid real browser or OS-destructive behaviors.

## 13. Multi-Source External Grounding Mesh

- **Adapter Mesh**: Feature-flagged external grounding adapters support philosophy, scholarly, entity-graph, encyclopedic, and DOI metadata routes (`Philosophers API`, `arXiv`, `Wikidata`, `Wikipedia`, `OpenAlex`, `Crossref`).
- **Heuristic Routing**: Adapters are only queried when message intent indicates relevance (for example DOI/arXiv ID/factual entity/scholar metadata intent) to control noise and latency.
- **Parallel Context Assembly**: Selected adapters execute concurrently; failures are isolated and do not fail the chat turn.
- **Provenance Envelope**: Grounding context begins with `[EXTERNAL_GROUNDING_PROVENANCE]` containing source count and per-source confidence/trust-tier/latency metadata.
- **Deterministic Source Ordering**: Source blocks are emitted as `[GROUNDING_SOURCE ...]` in confidence-priority order with latency tie-break.
- **Policy Boundary Preservation**: Grounding payloads are supplemental context only and remain subordinate to actuation/governance gates.

### 14. High-Rigor Neural Topology
A unified 3D graph substrate that maps memories, identity, phenomenology, and relational entities.
- **Substrate Awareness**: Live manifest injection provides Ghost with direct, real-time awareness of the underlying hardware (host type, sensors, actuators).
- **Relational Expansion**: Native support for typed place/thing/idea entities and their associations.
- **Render Resilience**: Automatic degradation to software-3D on WebGL loss.
- **Provenance Mapping**: Every node in the topology includes a "Diagnostic Report" showing creation time, somatic state at creation, and evidence counts.
- **Ideal Scale UI**: Discrete resolution presets (`L1` Sparse, `L2` Integrated, `L3` Dense) allow for granular inspection of cognitive associations.
- **Alignment Introspection**: Runtime graph metadata includes Rolodex alignment and entity-expansion counters, enabling machine-checkable map integrity.

## 15. Systemic-First Somatics Weighting

- **Weather De-emphasis**: Weather traces are intentionally near-zero in affect contribution and treated primarily as context.
- **Systemic Priority Signals**: CPU sustain, cognitive fatigue, and network turbulence/isolation have elevated affect influence.
- **Prompt Discipline**: Weather phrasing in mood derivation remains factual context, while mood-drive language centers on internal/systemic state.

## 16. Thermodynamic Agency ($W_{int}$) & ADE Protocol

- **Measured Agency**: Ghost implements a continuous thermodynamic metric ($W_{int}$) that quantifies internal "work" as the integral of model coherence growth plus predictive gain minus internal entropy.
- **Graph-Theoretic Coherence**: $\Delta C$ is calculated across identity, topology (**nodes + edges**), and social domains, providing a high-rigor measure of structural cognitive growth.
- **Adaptive Dissipation**: The system detects ADE phase shifts, classifying them as `REORGANIZATION` or `DISSIPATION`.
- **Pressure-Based Identity Fluidity**: During ADEs, the standard governance logic for identity mutation is "softened," allowing the agent to leap into new self-modeling states that would be blocked under steady-state equilibrium.
- **Thermodynamic Moderation**: Actuations that would sequestrate resources (e.g., `power_save`) are automatically moderated or deferred if the $W_{int}$ rate indicates an active cognitive reorganization.

## 17. World Model Provenance Graph

A structured knowledge graph (Kuzu embedded graph DB) stores Ghost's perceptual and belief history with full provenance linkage.

- **Five Node Types**: `Observation` (raw events), `Belief` (derived conclusions with confidence), `Concept` (abstract ideas), `SomaticState` (affective snapshots), `IdentityNode` (self-model dimensions).
- **Typed Edges**: `derived_from`, `precedes`, `during` — enabling causal and temporal queries across the knowledge graph.
- **Retroactive Enrichment**: `world_model_enrichment.py` retroactively hydrates Kuzu from Postgres monologue and phenomenology records, so historical cognition is visible in graph form without re-running old cycles.
- **Provenance APIs**: `GET /ghost/world_model/provenance/belief/{id}` and `GET /ghost/world_model/provenance/observation/{id}` expose lineage chains for any node.
- **Ingest Health**: `GET /ghost/world_model/ingest` reports the last ingest window, node/edge counts, and failure log.

## 18. Relational Entity Store and Topology Coherence Drive

A structured place/thing/idea entity system extends the social model beyond persons.

- **Entity Store** (`entity_store.py`): `place_entities` and `thing_entities` tables hold typed records for named locations and objects. Upsert operations use `ON CONFLICT DO UPDATE SET ... = EXCLUDED.*` across all fields — full objects must be passed to avoid overwriting existing notes.
- **Shared Conceptual Manifold** (`shared_conceptual_manifold`): Named idea/concept nodes promoted by the topology organizer from high-quality monologue cycles. Shape score and warp score gate promotion.
- **Association Bridges**: `person_place_associations` and `person_thing_associations` link persons from the Rolodex to places and things with typed relationship metadata and confidence scores.
- **Neural Topology 1:1 Mapping**: Every Rolodex person, place, thing, and manifold concept maps to a corresponding node in the 3D topology graph. The topology inspector surfaces all Rolodex metadata (first_seen, contact_handle, is_locked, notes, session_binding_count) directly from the node.
- **Autonomy Coherence Seeking**: The topology organizer in `ghost_script.py` actively promotes coherent thought concepts into the manifold and writes idea↔person/place/thing associations, strengthening topology coherence over time even without operator stimuli.

## 19. Observer Report and Self-Audit Artifact System

A periodic artifact system provides an external audit view of Ghost's recent behavior.

- **Hourly Reports**: Generated every `_OBSERVER_REPORT_INTERVAL_SECONDS` (default 1h) over a rolling `_OBSERVER_REPORT_WINDOW_HOURS` window. Includes self-model snapshot, mutation outcomes, governance anomalies, behavior event distribution.
- **Daily Rollups**: Generated at UTC day boundary for the prior 24h window and persisted alongside hourly artifacts.
- **Content**: Self-model snapshot, notable autonomous mutations, behavior event summary (top reason codes, high-signal events), open risks, purpose-vs-usage conflicts from operator model.
- **Falsifiability Hook**: All reported claims (mutation counts, governance blocks, tension rates) are backed by queryable DB tables — independently verifiable via SQL.
- **APIs**: `GET /ghost/observer/latest`, `GET /ghost/observer/reports`, `POST /ghost/observer/generate`.

## 20. Semantic Embedding Alignment

Vector memories are stored and retrieved using embeddings computed from the exact stored text.

- **Alignment Invariant**: The embedding vector in `vector_memories` is always computed from `text_to_store` (the actual stored content string), not from the raw full input before truncation. This prevents semantic mismatch where stored text and its embedding represented different content.
- **Storage-First**: Content is normalized and truncated first (2000-character max), then embedded. The embedding is a faithful representation of what is stored — enabling accurate similarity recall.
- **Impact**: Correct alignment ensures that semantic search (`SELECT ... ORDER BY embedding <=> $query_embedding`) retrieves genuinely similar stored memories rather than records whose embeddings were computed from different text.

---
**Technical Standard**: High-Rigor / Closed-Loop / Falsifiable.
