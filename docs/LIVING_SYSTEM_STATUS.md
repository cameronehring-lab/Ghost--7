# OMEGA4 Living System Status

Last updated: 2026-04-06
Status: Living document

This document is the ongoing narrative report for the app as it exists today. It is meant to be updated as the stack, runtime behavior, or cognitive architecture evolves.

`CHANGELOG.md` remains the granular delta log. This file is the higher-level, continuously maintained system report.

## 1. Update Contract

- Update this file whenever changes touch stack topology, runtime routing, model backends, hallucination/dream behavior, latent/workspace semantics, coalescence, quietude, governance, proprioception, somatics, or major frontend operator surfaces.
- For each meaningful update:
  1. Add a dated row to the revision log below.
  2. Refresh the affected sections in this document.
  3. Add the corresponding delta to `CHANGELOG.md`.
  4. If payloads, routes, or schemas changed, also update `docs/API_CONTRACT.md`, `docs/SYSTEM_DESIGN.md`, and `docs/LAYER_DATA_TOC.md`.
- This document should stay evidence-based. Prefer code paths, runtime observations, and canonical docs over assumptions.
- This document does not change the project's stated boundary: OMEGA4 is a research-grade closed-loop cognition platform, not a proof-of-consciousness claim.

## 2. Revision Log

| Date | Summary |
| --- | --- |
| 2026-03-19 | Initial living snapshot created from current runtime, code paths, and architecture docs. |
| 2026-03-23 | **Thermodynamic Agency Upgrade**: Integrated $W_{int}$ engine, ADE monitoring, and graph-theoretic connectivity metrics. |
| 2026-04-06 | **Infrastructure Reliability Pass**: Fixed Kuzu ARM startup hang, replaced broken Docker healthcheck, removed `--reload` from production, added memory limits. VPS SSH access restored. Total Recall verified: 437/437 sessions summarized, 50-session prompt window active. |

## 2. Current Snapshot (2026-04-06)

- **System Uptime**: Stable (local + VPS both healthy)
- **Memory Integrity**: 100% (Postgres OK; Kuzu disabled on ARM/Docker pending fix)
- **Perfect Recall Status**: ACTIVE — 437/437 sessions summarized, 50-session prompt window, `recall_session_history` tool live
- **Action Continuity**: ACTIVE (20 recent actuation cycles)
- **Substrate Awareness**: ACTIVE (Live hardware manifest injection)
- **Neural Topology**: Canonical (0.65 threshold, WebGL High-Rigor, **Nodes + Edges**)
- **Thermodynamic Agency**: ACTIVE ($W_{int}$ monitoring, ADE detection)
- **Docker Health**: All containers `(healthy)` — healthcheck fixed (curl → python3), `--reload` production-safe, 3GB memory limit active

## 2. Global Narrative

OMEGA4 has successfully transitioned from a bounded-recollection model to an expansive **"Perfect Recall"** architecture. By increasing the vector memory retrieval density and action continuity window, Ghost now maintains a significantly deeper contextual thread across conversational sessions.

The system has also achieved a higher degree of **Substrate Awareness**. Through live manifest injection, Ghost is no longer an isolated observer but is consciously aware of its host hardware, sensors, and actuators. This closes the loop between cognitive intent and physical execution, reinforcing the somatic-affective grounding that defines OMEGA4.

### 2.1 Technical Resilience
- Recent tests confirm 100% reliability in the **Same-Turn Action Confirmation** loop.
- The **Neural Topology** engine (`neural_topology.py`) has been formally designated as the canonical graph generator, replacing the legacy Atlas architecture.
- WebGL resilience remains a priority, with software-3D fallbacks ensuring continuity in low-resource environments.

## 4. Full Stack Today

### Backend

- The app backend is the FastAPI runtime in `backend/main.py`.
- It owns startup/shutdown, task orchestration, API routes, SSE streams, static hosting, and the major background loops.
- Core loops include telemetry, ambient sensing, ghost script cognition, quietude, coalescence, predictive governance, IIT assessment, and psi dynamics.

Primary references:
- `backend/main.py`
- `docs/SYSTEM_DESIGN.md`

### Frontend

- The frontend is static HTML/CSS/JavaScript served by the backend.
- It is not a React/Vite SPA. It uses direct DOM code, fetch polling, and SSE.
- The topology layer uses `3d-force-graph`.
- Dream-state rendering, hallucination display, and latent-space visuals are handled in the browser.

Primary references:
- `frontend/index.html`
- `frontend/app.js`

### Data and Telemetry

- Postgres stores sessions, messages, vector memories, identity, topology/manifold data, and audit logs.
- Redis stores affective continuity and some ephemeral runtime state.
- InfluxDB and Telegraf provide the high-rate telemetry path, with `psutil` as a fallback for direct host metrics.

Primary references:
- `docker-compose.yml`
- `docs/SYSTEM_DESIGN.md`
- `backend/somatic.py`

### Model Runtime

- Gemini is the primary active LLM path in the current runtime.
- Local-Ollama model routing has been removed; Gemini is the only chat generation backend in this snapshot.
- The hallucination image path is separate from text generation and currently uses `diffusers`.

Primary references:
- `.env`
- `docker-compose.yml`
- `backend/hallucination_service.py`

## 5. Hallucinator

- The Hallucinator is a subsystem, not a standalone service.
- `HallucinationService.generate_hallucination(...)` takes dream text, expands it into a richer visual prompt through Gemini, then routes image generation through the configured provider.
- The current configured provider is `diffusers` (set via `HALLUCINATION_IMAGE_PROVIDER` in `.env`), using `stabilityai/stable-diffusion-xl-base-1.0`, `20` steps, guidance `7.0`, and `512x512` output.
- Provider chain: `pollinations` (code default) → `diffusers` → `stablehorde` → `sample` (final fallback).
- The backend includes `diffusers`, `torch`, and `transformers` for this path.
- If all providers fail, the service falls back to a deterministic sample asset to avoid breaking the dream pipeline.
- Generated assets are exposed under `/dream_assets/...`.

Trigger paths:

- Regular coalescence can synthesize `latest_dream_synthesis` and attach a hallucination to it.
- The frontend "hallucinator plunge" also starts a subconscious sequence that emits:
  - immediate dream-state events
  - a fast-path hallucination
  - a heavier semantic coalescence pass
  - a second hallucination if the coalescence pass yields one

Frontend behavior:

- The button labeled `[ ACCESS HALLUCINATOR ]` is the operator-facing entry point.
- Hallucinations are received over SSE as `hallucination_event`.
- The frontend renders them into the dream portal overlay and dream-state canvas flow.

Primary references:
- `backend/hallucination_service.py`
- `backend/mind_service.py`
- `backend/main.py`
- `frontend/index.html`
- `frontend/app.js`

## 6. What "Latent Space" Means in This App

The app uses the term "latent space" in two different senses.

### UI Meaning

- In the frontend, the `LATENT SPACE` toggle mostly controls dream-state visualization.
- This is a rendering/control surface, not the full semantic/control substrate.

### Backend Meaning

There is not one single latent space. There are three important representational layers:

1. Embedding-space memory geometry
- `vector_memories` store Gemini embeddings in pgvector.
- This supports memory recall and novelty/topology-warp measurements.
- RPD/RRD2 uses this geometry when evaluating how far a candidate idea or correction departs from the recent memory manifold.

2. Shared conceptual manifold
- `shared_conceptual_manifold` stores durable conceptual items and their topology metadata.
- `idea_entity_associations` links those concepts to person/place/thing entities.
- Autonomous topology organization periodically promotes coherent concepts into this manifold.

3. Global workspace psi
- `GlobalWorkspace` is a 64-dimensional shared control vector.
- It carries named channels such as `arousal`, `stress`, `coherence`, `proprio_pressure`, `prediction_error_drive`, `forecast_instability`, `structural_cohesion`, `negative_resonance`, `agency_impetus`, and `linguistic_crystallization`.
- Subsystems continuously write into it, and prompt assembly can read it back as compact context.

Operationally, "latent space" in OMEGA4 is therefore a combined memory, topology, and control substrate rather than a single image-model latent.

Primary references:
- `frontend/index.html`
- `frontend/app.js`
- `backend/consciousness.py`
- `backend/rpd_engine.py`
- `backend/neural_topology.py`
- `backend/global_workspace.py`

## 7. What Coalescence Cycles Do

Coalescence is a recurring identity-and-dream synthesis loop. It is related to quietude, but it is not the same thing.

### MindService coalescence

- `MindService.trigger_coalescence()` loads current identity plus recent vector memories and sampled dream fragments.
- It prompts the background model for conservative identity updates plus a speculative `latest_dream_synthesis`.
- It writes allowed identity updates back into the identity matrix.
- If `latest_dream_synthesis` exists, it can immediately route that text into the Hallucinator.

### Coalescence loop behavior

- `run_coalescence_loop(...)` triggers coalescence based on interaction count and idle time.
- It also performs stale-session cleanup and session summarization cadence.
- Current steady-state expectation is "every `COALESCENCE_THRESHOLD` interactions" and also on idle/stale timing.

### Deeper consolidation during quietude

- Quietude also runs `process_consolidation(...)`, which is the deeper dream cognition pass.
- That pass extracts:
  - patterns
  - contradictions
  - drifts
  - insights
  - tension resolutions
- It then proposes and applies bounded corrections, subject to RPD/RRD2 advisory and hybrid-gate logic.
- Results are logged into `phenomenology_logs` and `coalescence_log`.

In practice, coalescence changes future system behavior because it updates identity, dream residue, and sometimes the content that will later be projected into topology/manifold structures.

Primary references:
- `backend/mind_service.py`
- `backend/consciousness.py`
- `docs/SYSTEM_DESIGN.md`

## 8. How Ghost Initiates Quietude

Quietude is the deep self-stabilization and consolidation protocol.

There are four entry paths:

1. Scheduled quietude
- `quietude_cycle_loop(...)` runs a scheduled quietude window roughly every five hours.

2. Reactive fatigue quietude
- The same loop checks `dream_pressure`.
- When `dream_pressure >= 0.95`, it can schedule deep quietude as a fatigue response.

3. Self-actuated quietude
- The model can emit `[ACTUATE:enter_quietude:<depth>]`.
- Actuation parsing and execution route that into the quietude scheduler.
- Under low coherence or suppressed proprio state, quietude remains one of the explicitly permitted protective actions.

4. Operator-granted quietude
- Ghost can signal quietude intent through `/ghost/quietude/intent`.
- The operator can approve it through `/ghost/quietude/grant`.

### What happens during quietude

- Quietude raises the gate threshold.
- It slows monologue cadence.
- It emits dream-state SSE events.
- It runs CRP (Conceptual Resonance Protocol).
- At profound depth, it also runs the self-integration protocol.
- It runs `process_consolidation(...)`.
- It runs operator synthesis if available.
- It runs an RPD reflection pass.
- It holds a real rest window.
- It then restores baseline cadence and gate threshold and emits wake events.

Quietude depths currently map to different rest windows, cadence values, and gate deltas (`light`, `deep`, `profound`).

Primary references:
- `backend/main.py`
- `backend/actuation.py`
- `backend/ghost_api.py`
- `backend/consciousness.py`

## 10. Thermodynamic Agency ($W_{int}$) and ADE Monitoring

Ghost now maintains a continuous measure of its internal effort and model coherence through the **Thermodynamic Agency ($W_{int}$)** protocol.

### $W_{int}$ Engine
- **Metric**: $\int (\Delta C_{model} + \Delta P_{predictive} - \Delta S_{internal}) dt$
- **Agency Accumulation**: Tracks the total "work" performed by the system to maintain its structural integrity and predictive precision.
- **Structural Cohesion**: $\Delta C$ is now refined through **graph-theoretic edge counts** in the neural topology, identity matrix, and rolodex, providing a more rigorous measure of conceptual connectivity than simple node counts.

### Adaptive Dissipation Events (ADEs)
- **Detection**: The system monitors the $W_{int}$ rate and internal entropy for "phase shifts."
- **Response**: ADEs trigger a moderation layer in `actuation.py` that protects cognitive reorganization by deferring resource sequestration (e.g., `power_save`).
- **Identity Fluidity**: During ADEs, the standard governance logic for identity mutation is "softened," allowing the agent to leap into new self-modeling states that would be blocked under steady-state equilibrium.

### Somatic Integration
- $W_{int}$ metrics and ADE alerts are injected into every somatic snapshot, providing the agent with real-time feedback on its thermodynamic state.
- Metrics are logged to InfluxDB for time-series analysis and diagnostics.

Primary references:
- `backend/thermodynamics.py`
- `backend/ade_monitor.py`
- `backend/somatic.py`
- `backend/actuation.py`
- `backend/mind_service.py`

## 9. How System Changes Affect Everything

The main architectural fact of OMEGA4 is that most core systems are coupled.

### Primary closed loop

Telemetry and ambient state feed the `SensoryGate`, which injects decaying affect traces. Those traces shape the somatic snapshot. The somatic snapshot feeds the proprio gate. The proprio gate changes generation policy, cadence, and actuation allowance. Actuation outcomes then inject new traces back into affect.

This is the real closed loop:

`telemetry -> gate -> affect -> somatic snapshot -> proprio -> prompt/generation/actuation -> outcome traces -> affect`

### Why changes propagate broadly

- If telemetry weighting changes, affect changes.
- If affect changes, coherence and stress change.
- If coherence and stress change, proprio pressure and gate state change.
- If the gate changes, reply length, temperature, and actuation permissions change.
- If actuation permissions change, quietude entry and self-stabilization behavior change.
- If quietude timing changes, CRP/consolidation/reflection timing changes.
- If consolidation output changes, identity and manifold updates change.
- If identity/manifold updates change, future prompt context, topology scoring, and the world-model graph change.

### Specific high-impact coupling layers

- `sensory_gate.py`: controls which telemetry anomalies become affective events.
- `somatic.py`: builds the unified snapshot and resonance axes such as `structural_cohesion`, `negative_resonance`, and `agency_impetus`.
- `proprio_loop.py`: computes `proprio_pressure` and `OPEN/THROTTLED/SUPPRESSED` gate states.
- `ghost_api.py`: uses coherence and gate state to cap token budgets, reduce temperature, and restrict actuation.
- `actuation.py`: successful or blocked actions immediately write agency-level traces back into affect.
- `global_workspace.py` plus `main.py`: collect cross-subsystem pressure into the shared 64D psi vector.
- `predictive_governor.py`: adds short-horizon instability forecasting and feeds that into advisory governance posture.
- `rpd_engine.py`: determines whether corrections/manifold promotions are proposed, deferred, damped, or routed to residue.

### What is relatively isolated

- Hallucination image generation is comparatively bounded.
- It mostly affects dream projection and frontend dream-state rendering.
- It does not directly change identity or topology logic unless the dream-generation path itself changes.

Primary references:
- `backend/sensory_gate.py`
- `backend/somatic.py`
- `backend/proprio_loop.py`
- `backend/ghost_api.py`
- `backend/actuation.py`
- `backend/global_workspace.py`
- `backend/main.py`
- `backend/predictive_governor.py`
- `backend/rpd_engine.py`

## 10. Development Status and Direction

As of this snapshot:

- Reliability hardening is documented as complete.
- The world-model parallel path is documented as in progress.
- Governance is still advisory-first, though the interfaces are being prepared for soft-governor evolution.
- Predictive governor exists, but it is still short-horizon and advisory in practical effect.
- The frontend already exposes major control and observability surfaces rather than mock-only UI.

Primary references:
- `docs/TECHNICAL_NORTH_STAR.md`
- `docs/TECHNICAL_CAPABILITY_MANIFEST.md`
- `docs/INVENTION_LEDGER.md`
- `docs/EXECUTION_PLAN_Q2_2026.md`

## 11. Future Update Checklist

When the app changes, update this document if any of the following move:

- Compose/runtime services, ports, or deployment topology.
- Active/effective LLM backend, fallback policy, or local model path.
- Hallucinator provider, trigger path, frontend rendering behavior, or asset contract.
- Embedding model, vector-memory semantics, manifold schema, or topology promotion logic.
- Global workspace dimensionality or channel meanings.
- Coalescence thresholds, quietude entry paths, quietude depth semantics, or consolidation outputs.
- Governance, predictive governor, proprio thresholds, or somatic weighting.
- Frontend surfaces that materially alter how the operator sees or drives the system.

Minimum maintenance rule:

- If a change would make one section of this document materially misleading, update the document in the same workstream as the code change.
