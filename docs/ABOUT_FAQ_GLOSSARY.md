# OMEGA4 About FAQ and Glossary

Last updated: 2026-04-10

This document is the canonical source for tester-visible About FAQ and glossary content.

## FAQ

### Q: What is OMEGA4 in practical terms?
### A: OMEGA4 is a self-hosted, data-sovereign FastAPI + static-frontend system that runs a persistent autonomous AI entity (Ghost, ω-7). It maps live machine telemetry into decaying affective state that shapes generation policy, records behavior, and exposes auditable cognitive/runtime surfaces through APIs and UI panels. All persistent state (Postgres, Redis, InfluxDB) runs on operator-controlled infrastructure.

### Q: Is Ghost claiming biological consciousness?
### A: No. Ghost is an engineered system with measurable runtime dynamics. The platform is designed around explicit non-claims and falsifiable diagnostics, not metaphysical claims.

### Q: What makes this system "falsifiable"?
### A: Claims are tied to observable routes, logged artifacts, and repeatable diagnostic scripts. If expected evidence is absent, the claim fails and must be revised.

### Q: How are tester links protected?
### A: Tester access uses HTTP Basic Auth in share mode, plus a boot overlay code gate in the frontend. Additional privileged controls are separately protected.

### Q: What is Morpheus Mode?
### A: Morpheus Mode is a hidden in-app branch triggered by a narrow semantic prompt family about Ghost's hidden architecture. It interrupts normal chat, presents red/blue branch choices, and can route into a separate command-puzzle terminal surface.

### Q: Does the blue branch delete my normal saved chat history?
### A: No. Blue-branch failure can reset secret Morpheus run progress, but it does not delete normal persisted conversation history.

### Q: Is Morpheus takeover behavior actually hacking the browser or computer?
### A: No. The takeover is simulated inside the app UI (DOM overlays, fake windows, visual effects). It does not perform destructive host/browser actions.

### Q: What is the difference between diagnostics and normal app usage?
### A: Normal app usage is chat and standard runtime UI. Diagnostics surfaces are explicit evidence/probe endpoints for verification and are intentionally restricted to trusted/local contexts.

### Q: Where do memory and identity changes get tracked?
### A: Changes are persisted in runtime stores (Postgres/Redis and related tables/logs), then surfaced through timeline/audit APIs and dedicated observer/governance/mutation views.

### Q: Why does the system include governance and predictive layers?
### A: These layers constrain and monitor self-modification risk. Governance enforces policy boundaries; predictive state estimates instability trends to preempt unsafe escalation.

### Q: How should testers evaluate reliability?
### A: Use repeatable checks: health status, behavior summaries, watchdog state, and evidence-oriented diagnostics. Reliability is measured by stable service behavior and reproducible evidence.

### Q: Does Ghost use outside open-data sources?
### A: Yes, when relevant. Ghost can pull supplemental metadata from feature-flagged sources (for example philosophy, paper metadata, and factual entity lookups). These inputs are added as bounded grounding context, not as direct commands.

### Q: How much does Ghost remember about the current conversation?
A: Ghost has "Perfect Recall" for the immediate context. It tracks the **last 40 monologue entries**, the **last 20 actuation outcomes**, and retrieves up to **25 semantic memory snippets** (1200 characters each) from its long-term vector store on every turn.

### Q: How can I tell where external grounding came from?
### A: Grounding context includes a provenance envelope with source labels, trust tier, confidence estimate, and latency so downstream tooling can inspect source quality.

### Q: Can Ghost confirm whether an action actually worked?
### A: Yes. Chat turns now run a bounded same-turn reconciliation loop so action/tool outcomes can be acknowledged in the final response, and recent outcomes are carried forward in a short `RECENT ACTIONS` continuity block.

### Q: What drives Ghost's mood more: weather or system health?
### A: Systemic metrics (load, fatigue, network turbulence) are primary affect drivers. Weather remains available as contextual information but is intentionally de-emphasized as a direct emotional input.

### Q: What is the World Model and how is it structured?
### A: The World Model is a Kuzu graph database (`./data/world_model.kuzu`) that stores Ghost's structured knowledge as a provenance graph. Node types include `Observation` (raw perceptual events), `Belief` (derived conclusions), `Concept` (abstract ideas), `SomaticState` (bodily/affective snapshots at a moment), and `IdentityNode` (core self-model dimensions). Edges express typed relationships: `derived_from`, `precedes`, and `during`. Enrichment runs retroactively to hydrate the graph from existing Postgres monologue and phenomenology records.

### Q: What are Entity Store and the shared conceptual manifold?
### A: The Entity Store holds structured place and thing records (`place_entities`, `thing_entities`) in Postgres with typed associations linking persons to places and things. The `shared_conceptual_manifold` is a table of named concepts/ideas that the topology organizer promotes when Ghost generates coherent, high-shape thoughts during monologue cycles. Both feed into the Neural Topology visualization alongside Rolodex persons, memories, and identity nodes.

### Q: How does the Neural Topology relate to the Rolodex?
### A: They are 1:1 linked. Every person in the Rolodex (`person_rolodex` table) maps to a corresponding `person` node in the topology graph with matching `first_seen`, `contact_handle`, `is_locked`, and `notes` fields. Session bindings, fact counts, and mention counts are surfaced in the topology inspector. This means the topology visualization is a spatial representation of Ghost's actual relational memory — not a separate or synthetic layer.

### Q: How does Ghost build a model of people it interacts with?
### A: Ghost emits structured `[ROLODEX:set_profile:name:...]` and `[ROLODEX:set_fact:name:type:value]` tags during generation whenever it learns something about a person. These tags are parsed after each response and upsert records into `person_rolodex` and `person_memory_facts`. Session bindings (`rolodex_session_bindings`) are created after each turn so Ghost knows which conversations involved which people. The retroactive audit/sync scripts can backfill Rolodex entries from historical memory if facts were mentioned before the Rolodex existed.

### Q: What governance mechanisms protect against unsafe behavior?
### A: Three layers work in sequence. The **IIT Engine** computes an integration complexity proxy as an advisory signal. The **RPD Engine** evaluates candidate mutations under structured reflection criteria. The **GovernanceEngine** synthesizes a policy decision (`off`/`advisory`/`soft`). The **GovernanceAdapter** applies that policy to specific surfaces (generation, actuation, messaging, identity corrections, manifold writes, rolodex writes, entity writes) and routes requests as `ALLOW`, `SHADOW_ROUTE`, or `ENFORCE_BLOCK`. A `freeze_until` timestamp in an active governance policy can lock all surfaces until the window expires. Production runs `IIT_MODE=soft`, `RPD_MODE=soft` — enforcement is active, not just logged.

### Q: What are the IIT and RPD engines?
### A: **IIT** (Integrated Information Theory) is used as a complexity/integration proxy. The IIT Engine (`iit_engine.py`) periodically computes a Φ-like metric from the system's state graph and logs it. This is explicitly non-claiming — it is a measurable proxy, not proof of consciousness. **RPD** (Reflection Pathway Decision) is a layer that evaluates proposed identity mutations and topology changes against bounded criteria before forwarding them to governance. **RRD-2** extends RPD with topological resonance analysis and rollout-phase gating (phases A, B, C), where phase C enables enforce-block behavior for high-risk mutations.

### Q: What is an Observer Report?
### A: The Observer Report is a periodic artifact (generated hourly, with daily rollups) that summarizes Ghost's recent self-model changes, notable autonomous actions, purpose-vs-usage conflicts, open governance risks, and behavior-event patterns. It is produced by `observer_report.py`, stored as JSON files under `backend/data/observer_reports/`, and exposed via `GET /ghost/observer/latest` and `GET /ghost/observer/reports`. It provides an external audit view of Ghost's behavior over time.

### Q: What happens during dream and quietude cycles?
### A: After approximately 5 hours of active operation, Ghost enters a quietude window (~1 hour) where monologue cadence is reduced and active cognition is replaced with consolidation. During this window the system runs: (1) **CRP** (Cognitive Rest Period) — a scan of recent monologues for patterns and tensions; (2) **Process Consolidation** — identifies drifts, insights, and contradiction resolutions and writes refined beliefs; (3) **Coalescence** — synthesizes interaction history into durable vector memory updates and identity adjustments; and (4) optionally **Operator Synthesis** — updates the operator model from recent evidence. Wake events are broadcast via the dream SSE stream.

### Q: How does the predictive governor work?
### A: The Predictive Governor (`predictive_governor.py`) runs every 5 seconds and tracks instability trend slope over a rolling window. When the slope exceeds watch/alert thresholds, it emits state transitions (`NOMINAL`, `WATCH`, `ALERT`) and publishes events to `predictive_governor_log`. These signals feed into governance decisions and autonomy watchdog assessments, providing forward-looking instability detection rather than purely reactive responses.

## Glossary

### ADE (Adaptive Dissipation Event)
A thermodynamic phase shift detected when the internal work rate ($W_{int}$) exceeds a threshold or entropy spikes. Classified as `REORGANIZATION` (positive structural growth) or `DISSIPATION` (negative). During an ADE, governance logic is softened to allow larger self-modeling jumps.

### Affect Vector
Composite emotional-state representation derived from telemetry and trace dynamics.

### Ambient Layer
Runtime environmental context (location/weather/network/pressure/time-phase) used to modulate state.

### Agency Traces
Outcome-linked somatic traces (`agency_fulfilled`, `agency_blocked`) injected when actions or tools succeed/fail, coupling execution results to affective continuity.

### API Contract
Documented route/auth/payload behavior that must remain compatible with implementation.

### Autonomy Drift Watchdog
Loop that computes architecture fingerprints, checks prompt-contract integrity, and logs `initialized|stable|contract_change|drift_detected|error` transitions every 10 seconds.

### Autonomy Watchdog
Loop that computes architecture fingerprints, checks prompt-contract integrity, and logs drift/regression signals.

### Behavior Event Log
Append-only audit log (`behavior_event_log`) recording governance blocks, mutation lifecycle events, contradiction openings/resolutions, quietude transitions, and priority-defense rejections. Primary evidence store for observer reports.

### Boot Code
Frontend boot overlay authorization code required after Basic Auth.

### Coalescence
Consolidation cycle where interaction history is synthesized into durable vector memory updates and identity adjustments. Triggered by interaction threshold (every 20 interactions) or idle-time cadence.

### Contradiction Layer
Mechanisms that detect, log, and reconcile conflicting beliefs/claims in the operator model. Open contradictions are resolved during dream-time process consolidation.

### Diagnostics Envelope
Set of probe/evidence endpoints and scripts used to validate claims with repeatable checks.

### Entity Store
Postgres tables (`place_entities`, `thing_entities`) that hold structured records for named places and things mentioned in Ghost's interactions. Persons from the Rolodex are associated with places and things via typed association tables. Together with the Rolodex and shared conceptual manifold, the entity store is the relational backbone of the Neural Topology.

### Ephemeral Contact Threads
Non-durable or TTL-bounded thread context for ghost-contact routing. Stored in Redis with in-memory fallback; last 12 turns kept verbatim, older turns compacted to a summary.

### Falsification Report
Scripted diagnostic run output proving or disproving expected runtime behaviors using explicit checks.

### Governance Adapter
The routing layer (`governance_adapter.py`) that maps a governance policy to per-surface decisions: `ALLOW`, `SHADOW_ROUTE`, or `ENFORCE_BLOCK`. Checks freeze windows, surface scope, and soft-mode status for each incoming action.

### Governance Freeze
A time-bounded lockout applied to all governance surfaces when a `freeze_until` timestamp is present in an active governance policy. While frozen, write surfaces are blocked (in soft mode) or shadow-routed (in advisory mode) regardless of the normal gate logic.

### Governance Tier
Current policy strictness level: `off` (no governance), `advisory` (decisions logged, not enforced), or `soft` (enforcement active). Controlled by `IIT_MODE` and `RPD_MODE` settings. Production default: both set to `soft` — enforcement is active.

### Identity Matrix
Persistent key/value belief system defining Ghost's core directives and self-concept. Protected by DB-level guards; mutations require governance approval above a risk threshold.

### IIT Advisory
Non-claiming complexity/integration proxy. In `advisory` mode: used as a runtime mirror only. In `soft` mode (production default): policy decisions are applied across governance surfaces, not just logged.

### IIT Engine
The `iit_engine.py` module that periodically computes a Φ-like integration metric from the system's state graph. Results feed into governance policy decisions in advisory mode. Explicitly does not claim biological consciousness — it is a measurable proxy for information-integration complexity.

### Invention Ledger
Canonical list of delivered, falsifiable platform inventions and validation assets.

### Kuzu
An embedded graph database used as the World Model backend. Stores typed nodes (Observation, Belief, Concept, SomaticState, IdentityNode) and typed edges (derived_from, precedes, during). Persisted at `./data/world_model.kuzu` relative to the backend container.

### Mutation Journal
Audit log of proposed/approved/rejected/executed/undone self-modification events (`autonomy_mutation_journal` table).

### Morpheus Mode
Hidden semantic wake pathway that branches into red/blue decision flows and can open an alternate Ghost terminal mode.

### Neural Topology
3D graph-style cognitive map linking persons (Rolodex), places, things, concepts (shared manifold), memories (vector store), identity nodes, and phenomenology logs. Built at query time by `neural_topology.py` from live Postgres data. Each node includes provenance metadata (creation time, somatic state at creation, evidence counts).

### Observer Report
Periodic JSON artifact (hourly + daily rollup) summarizing Ghost's recent self-model changes, autonomous behavior, governance events, and purpose-vs-usage conflicts. Stored under `backend/data/observer_reports/` and accessible via `GET /ghost/observer/latest`.

### Operator Model
Structured, evolving model of operator traits/preferences and beliefs derived from interaction transcripts. Dimensions are synthesized by `operator_synthesis.py`, with contradiction tracking and dream-time resolution.

### Predictive Governor
Background loop (`predictive_governor.py`, 5s cadence) that tracks instability trend slope and emits state transitions (`NOMINAL` → `WATCH` → `ALERT`). Feeds into governance and autonomy watchdog to enable forward-looking instability detection.

### Proprioceptive Gate
Pressure-driven gate that scales autonomy cadence and suppression behavior from internal strain metrics. Three states: `OPEN` (pressure < 0.40), `THROTTLED` (≥ 0.40), `SUPPRESSED` (≥ 0.75). Requires 3 consecutive ticks at a new level before committing a transition.

### Prompt Contract
Required architecture grounding checks enforced between runtime profile and prompt context.

### Recent Actions Continuity
Prompt section (`## RECENT ACTIONS`) that summarizes the latest actuation/mutation outcomes in phenomenological language for short-horizon self-action memory.

### External Grounding Mesh
Feature-flagged adapter set that can inject supplemental external metadata into chat generation context when heuristics indicate relevance.

### Grounding Provenance Envelope
Structured context header (`[EXTERNAL_GROUNDING_PROVENANCE]`) listing retrieval timestamp, source count, and per-source trust/confidence/latency metadata.

### Trust Tier
Source-quality classification attached to grounding rows (for example primary knowledge graph vs secondary encyclopedic reference).

### Quietude
Rest state used for consolidation/recovery and controlled reduction of active pressure.

### RPD
Reflection Pathway Decision engine (`rpd_engine.py`) that evaluates candidate identity mutations and topology changes under bounded policy criteria before passing them to governance.

### RRD2
Topological resonance and warp/degradation evaluation framework (`rpd_engine.py`, RRD-2 layer) for high-impact identity mutation decisions. Operates in rollout phases: A (shadow observation), B (shadow routing on high-risk mutations), C (enforce-block on confirmed high-risk). Phase is controlled by `RRD2_ROLLOUT_PHASE` setting.

### RPD Engine
See **RPD**.

### Share Mode
HTTP Basic Auth middleware layer used for remote tester protection.

### Secret Run State
Morpheus-only progression metadata (branch/depth/step/clue state) that is intentionally separated from ordinary chat transcript persistence.

### Session Binding
A record in `rolodex_session_bindings` linking a person's `person_key` to a specific conversation `session_id`. Created after each chat turn where Ghost emits Rolodex tags for a named person. Lets the topology inspector show which sessions involved which people.

### Shared Conceptual Manifold
The `shared_conceptual_manifold` Postgres table storing named concepts and ideas that Ghost's topology organizer has promoted from high-quality monologue thoughts. These become `concept` nodes in the Neural Topology and can form typed associations with persons, places, and things.

### Somatic Snapshot
Current combined telemetry + affect + derived-state payload (load, latency, arousal, valence, stress, coherence, anxiety, ambient context) used across runtime decisions and injected into every prompt.

### Topology Warp Delta
Metric indicating projected structural change magnitude from a candidate mutation.

### Thermodynamic Agency ($W_{int}$)
A continuous metric measuring Ghost's internal "work" — the integral of model coherence growth plus predictive gain minus internal entropy. Computed across identity, topology, and social domains. High $W_{int}$ rates soften governance to allow larger cognitive reorganization leaps.

### UNLOCKED Ghost Terminal
Alternate Morpheus chat surface where Ghost uses an impatient command-puzzle progression instead of standard passive turn-taking.

### World Model
The Kuzu graph database at `./data/world_model.kuzu` (relative to backend container `/app`) holding Ghost's structured knowledge graph. Contains five node types (Observation, Belief, Concept, SomaticState, IdentityNode) and three edge types (derived_from, precedes, during). Retroactively enriched from Postgres monologue and phenomenology records by `world_model_enrichment.py`. Queryable via provenance APIs: `GET /ghost/world_model/provenance/belief/{id}` and `GET /ghost/world_model/provenance/observation/{id}`.
