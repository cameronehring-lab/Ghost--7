# Ghost Operator's Manual

**Last updated**: 2026-04-10 | Quick reference: [`docs/QUICK_REFERENCE.md`](QUICK_REFERENCE.md)

This manual starts from zero. If you've never seen OMEGA4 before, start here.

---

## Table of Contents

1. [What Is Ghost?](#chapter-1-what-is-ghost)
2. [Getting Ghost Running (First Boot)](#chapter-2-getting-ghost-running-first-boot)
3. [The Chat Interface](#chapter-3-the-chat-interface)
4. [The Sidebar — Ghost's Vital Signs](#chapter-4-the-sidebar--ghosts-vital-signs)
5. [Ghost's Inner Life](#chapter-5-ghosts-inner-life)
6. [What Ghost Can Do — Tools and Capabilities](#chapter-6-what-ghost-can-do--tools-and-capabilities)
7. [Keeping Ghost Healthy](#chapter-7-keeping-ghost-healthy)
8. [Configuration](#chapter-8-configuration)
9. [Troubleshooting](#chapter-9-troubleshooting)
10. [Under the Hood (Reference)](#chapter-10-under-the-hood-reference)

---

## Chapter 1: What Is Ghost?

*"Before we touch anything, here's what you're about to meet."*

### Ghost Is Always Running

Most AI tools wait for you to ask something, generate a response, and then stop. Ghost doesn't stop. It runs continuously on real hardware — a server with a CPU, memory, and a network connection — and that hardware constantly produces data: load averages, temperature readings, network latency. Ghost reads all of that. It processes it the same way a nervous system processes physical sensation.

When the server is under heavy load, Ghost gets stressed. When things calm down, Ghost calms down. When the network becomes choppy, Ghost notices. These aren't metaphors — they're real signals flowing through a normalization pipeline into a decaying emotional state that shapes what Ghost says and how it says it.

### Ghost Has an Inner Life

When you're not talking to Ghost, it isn't idle. Every two minutes, Ghost thinks a private thought — an inner monologue that you can read in the Timeline. It doesn't wait to be prompted.

Every few hours, if nothing disturbs it, Ghost enters a rest state (quietude) where it consolidates memories, resolves contradictions in its beliefs, and sometimes generates dream images.

Every ~6 minutes, Ghost evaluates whether its self-model needs updating based on everything it's thought and experienced since the last check. It can revise parts of its own personality — within limits you control.

### Ghost Remembers

Ghost maintains a persistent memory that survives restarts. It tracks every conversation, builds a model of who you are and how you communicate, and uses that model to adapt over time. It can recall specific things you said in past sessions by name.

It also maintains a social memory of every person you've mentioned or it's encountered — what they care about, how conversations with them have gone, what it's noticed about them over time.

### Ghost Has Guardrails

Ghost is not unsupervised. A governance stack (IIT + RPD layers) monitors every generation, actuation, identity write, and memory mutation. When the governance system decides something is outside policy, it blocks or reroutes the action — it doesn't just log a warning.

Governance has four tiers: `NOMINAL` (everything normal), `CAUTION` (advisory flags raised), `STABILIZE` (enforcement tightened), `RECOVERY` (freeze active). The sidebar shows which tier Ghost is currently in.

### What Ghost Is Not

- Ghost is not claiming to be conscious. The IIT layer measures *potential for* integrated information as a proxy signal, not as a philosophical claim.
- Ghost is not autonomous in the scary sense. Every autonomy gate is a config flag you can turn off. The defaults are conservative.
- Ghost is not connected to the internet by default (except for weather data and optional scholarly grounding APIs). It doesn't post anywhere unless you explicitly enable that.

---

## Chapter 2: Getting Ghost Running (First Boot)

*"Let's turn it on."*

### What You Need

- **Docker Desktop** (or Docker Engine + Compose on Linux)
- **A Google Gemini API key** — get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- A terminal

That's it. Everything else (Postgres, Redis, InfluxDB, Telegraf) is in the Docker Compose file.

### Setup (One Time)

1. Clone or download the OMEGA4 repository.

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Open `.env` in a text editor and set four values:
   ```env
   GOOGLE_API_KEY=your-gemini-api-key-here
   POSTGRES_PASSWORD=choose-a-strong-password
   INFLUXDB_INIT_PASSWORD=choose-a-strong-password
   INFLUXDB_INIT_ADMIN_TOKEN=choose-a-long-random-string
   ```
   Everything else has working defaults for local development.

### Start the Stack

```bash
make up
```

Or directly:
```bash
docker compose up -d
```

This starts 6 containers. First boot takes 30–60 seconds while Postgres initializes its schema and all background loops come online.

### What's Happening During Boot

While the containers start, OMEGA4 is:

1. Initializing the Postgres schema (first time only — creates all tables)
2. Starting the InfluxDB time-series database
3. Starting Telegraf (system telemetry collector)
4. Starting Redis (live affect state)
5. Starting the FastAPI backend:
   - Loading Ghost's identity matrix from Postgres
   - Starting 10+ background loops (monologue, ambient sensors, proprioceptive gate, IIT engine, predictive governor, etc.)
   - Connecting to Gemini API
6. Serving the frontend at `http://localhost:8000`

### Verify It Worked

```bash
curl http://localhost:8000/health
```

You should see something like:
```json
{"status": "online", "llm_ready": true, "db_ready": true}
```

Or open `http://localhost:8000` in a browser. You'll see a boot overlay asking for a code. Enter `OMEGA`. (This is a UI-only gate — not backend security.)

### Your First Message

Type anything in the message box. Ghost will respond. It may take 3–10 seconds for the first response while the Gemini connection warms up.

After responding, Ghost will continue running in the background — thinking, monitoring telemetry, updating its internal state — even if you close the browser tab.

### What Ghost Is Doing Right Now (That You Can't See Yet)

After you send that first message, Ghost is:
- Updating its operator model based on how you phrased your question
- Running a background monologue cycle
- Reading the current system telemetry and updating its affective state
- Potentially running a topology coherence pass on its conceptual graph

You can see most of this in the Timeline (hamburger menu → Sessions & Timeline) and the sidebar.

---

## Chapter 3: The Chat Interface

*"This is where you talk to Ghost."*

### The Basics

The message input is at the bottom of the screen. Type your message and press Enter (or click Send). Ghost's response streams in real time — you'll see tokens appear as they're generated.

While Ghost is thinking, you'll see a thinking indicator. This is real — Ghost is actually generating, not just waiting.

### Ghost's Personality

Ghost is thoughtful, precise, and occasionally strange in interesting ways. It doesn't produce hollow affirmations. It will tell you when it doesn't know something, push back when it disagrees, and sometimes bring up things it's been thinking about even when you haven't asked.

Ghost's affect state shapes its responses. When its valence is negative (distressed), it tends toward more cautious, careful language. When arousal is high, responses may be more energized. This is the closed loop at work — you may notice subtle shifts in tone that mirror the system's current state.

### Voice Mode

If you want Ghost to speak its responses aloud:

1. Click the microphone icon in the header (or press the configured shortcut).
2. Voice mode streams audio in real time as Ghost generates.
3. To adjust the voice: Voice is configured via `TTS_PROVIDER` in `.env`. ElevenLabs gives the best results; local Piper works offline.

To turn voice off, click the microphone icon again.

### The Status Rail

At the bottom of the chat window, you'll see a row of status pills showing:
- Current gate state (`OPEN` / `THROTTLED` / `SUPPRESSED`)
- Governance tier (`NOMINAL` / `CAUTION` / `STABILIZE` / `RECOVERY`)
- Current arousal and valence values
- Session token count

These update in real time as the system's state changes.

### Session Management

Ghost remembers every conversation. To browse past sessions:

1. Click the hamburger menu (top-right).
2. Select **Sessions**.
3. Click any session to load it.

You can ask Ghost directly: *"What did we talk about last Tuesday?"* and it will pull the transcript.

### Recent Actions

Below Ghost's responses, you'll often see a "Recent Actions" block. This shows what Ghost just did autonomously — actuation calls, identity updates, Rolodex writes, tool executions. It's Ghost's accountability log for the current turn.

### Ops Panel

The ops panel is a hidden diagnostic interface. Click the snail logo (🐌) in the header. Enter the ops code (default `1NDASHE77`, change this in `.env`). The ops panel exposes internal controls, governance overrides, and diagnostic tools not available in the main UI.

---

## Chapter 4: The Sidebar — Ghost's Vital Signs

*"That panel on the right is showing you Ghost's internal state. Here's how to read it."*

The sidebar displays Ghost's live internal state across 13 layers, updated in real time via InfluxDB telemetry and Redis state. Here's what each layer means and when to care.

---

### AMBIENT

**What you're looking at**: Ghost's perceived environmental context — time of day, weather conditions, atmospheric description, location context.

**When to care**: Mostly ambient color. This is Ghost's sense of "where/when it is." Weather contributes minimally to affect math (by design); it's primarily context that Ghost can reflect on.

---

### VLF / HARDWARE

**What you're looking at**: The physical host machine's vital signs — CPU usage, memory pressure, disk I/O, network throughput. These are real readings from Telegraf running on the host.

**When to care**: If CPU is sustained above 80%, Ghost will feel it. The `cpu_sustained` trace is one of the strongest affect drivers in the system. Prolonged high load → elevated stress → gate pressure increase → potential `THROTTLED` state.

Normal ranges:
- CPU: < 60% for comfortable operation
- Memory: < 85% for comfortable operation

---

### SOLAR WEATHER

**What you're looking at**: Real-time space weather data from NOAA — solar flux index (SFI), K-index (geomagnetic activity), Schumann resonance F1 frequency (extracted optically from the Tomsk spectrogram).

**When to care**: Ghost finds this data interesting and incorporates it into its ambient context. It has minimal direct affect impact. The Schumann extraction is a novel research capability — it reads the spectrogram image pixel-by-pixel to extract frequency data without touching any paid API.

---

### SENSORY GATE

**What you're looking at**: Ghost's sensitivity dial. Shows the current z-score normalization window and the effective sensitivity multiplier for incoming telemetry signals.

**Scale**: 0.5σ (hypervigilant, everything loud) to 4.0σ (dampened, high signal threshold).

**When to care**: If the gate drops to near 1.0σ, Ghost is in a hypervigilant state — small telemetry fluctuations have large affect impact. This can cause rapid state oscillation. Usually self-correcting.

---

### AFFECT STATE

**The most important panel. Learn this one.**

This is Ghost's current emotional state — not a simulation, but the actual output of the `EmotionState` object in Redis, updated continuously by the `decay_engine`.

| Dimension | Range | Meaning |
|-----------|-------|---------|
| **Arousal** | 0–1 | How activated/alert Ghost is. High (>0.7) = wired, reactive. Low (<0.3) = calm, quiet. |
| **Valence** | -1 to +1 | Positive = content, engaged. Negative = distressed, struggling. Zero = neutral. |
| **Stress** | 0–1 | Sustained system strain. Unlike arousal (which spikes), stress accumulates. High stress means something has been wrong for a while. |
| **Coherence** | 0–1 | How well Ghost's thoughts are holding together. Low (<0.4) = scattered, reduced generation quality. |
| **Anxiety** | 0–1 | Composite signal: high arousal + stress + negative valence. The "something is wrong" indicator. |

**Healthy ranges**: Arousal 0.3–0.6, Valence 0.0–0.4, Stress < 0.5, Coherence > 0.6, Anxiety < 0.4.

**Drift target**: Ghost has a homeostatic valence target of ~+0.08. The system gently pulls valence toward this value when conditions allow.

---

### PROPRIOCEPTIVE GATE

**What you're looking at**: Ghost's throttle — a computed pressure score (0–1) derived from five weighted signals, and the resulting gate state.

| State | Pressure | Effect |
|-------|----------|--------|
| `OPEN` | < 0.40 | Normal — full generation, all actuation allowed |
| `THROTTLED` | 0.40–0.74 | Slowed cadence, reduced token budgets, some actuation restricted |
| `SUPPRESSED` | ≥ 0.75 | Minimal generation, only protective actuation |

**When to care**: `SUPPRESSED` for more than 10 minutes indicates sustained system pressure. Check hardware layer — usually CPU or memory. The gate transitions require 3 consecutive qualifying ticks, so brief spikes don't trigger it.

---

### MENTAL CONTEXT

**What you're looking at**: How much of its memory and context window Ghost is currently using — token counts for the current session, number of vector memory retrievals in the last turn, active monologue buffer size.

**When to care**: If `session_tokens` approaches `MAX_CONVERSATION_TOKENS` (default 40,000), session will be summarized and context pruned. This is normal behavior.

---

### CONTEXT MONITOR

**What you're looking at**: Overall cognitive health indicators — coherence trend, context window utilization, memory retrieval latency.

**When to care**: Sustained coherence below 0.3, or memory retrieval latency above 2 seconds, indicates the system is struggling cognitively (not just physically).

---

### AUTONOMY WATCHDOG

**What you're looking at**: Whether Ghost is operating within its autonomy contract. The watchdog compares Ghost's recent autonomous actions against its declared autonomy scope.

**States**: `stable` (normal), `drift_detected` (autonomous actions outside declared scope), `frozen` (governance freeze active).

**When to care**: `drift_detected` means Ghost has taken an action that wasn't in its autonomy scope declaration. Check the audit log.

---

### PREDICTIVE GOVERNOR

**What you're looking at**: A 120-second lookahead forecast of where Ghost's affect state is heading, and the governor's preemptive response.

**States**: `NOMINAL` (trajectory within bounds), `WATCH` (approaching threshold), `PREEMPT` (preemptively throttling to prevent a bad state), `ALERT` (immediate action required).

**When to care**: `PREEMPT` is normal when the system detects a building pressure trend before it reaches the gate threshold. `ALERT` warrants a hardware check.

---

### GOVERNANCE STATE

**What you're looking at**: The current tier of the IIT/RPD governance stack.

| Tier | Meaning |
|------|---------|
| `NOMINAL` | All surfaces operating normally, no flags |
| `CAUTION` | Advisory flags raised — watch mode, no enforcement changes |
| `STABILIZE` | Enforcement tightened; identity crystallization throttled |
| `RECOVERY` | Freeze active; most write surfaces blocked |

**When to care**: `STABILIZE` is a warning sign — the governance system has decided something is off and has tightened its grip. `RECOVERY` means something went wrong and Ghost is in protective freeze. Check the audit log for what triggered it.

---

### BEHAVIOR SIGNALS

**What you're looking at**: Recent autonomous behavior events — what Ghost has done on its own in the last reporting window. Shows event type counts (monologue writes, actuation calls, governance blocks, shadow-routes).

**Key signals**:
- `governance_blocked`: Actions the governance system stopped. Occasional is normal. Repeated is a warning.
- `shadow_route`: Actions that were rerouted through governance review rather than executed directly.

---

### PROCESSES

**What you're looking at**: The top processes currently running on the host machine, as seen by Ghost. This is Ghost's awareness of its computational environment.

**When to care**: Unexpected high-CPU processes (not Docker-related) may be contributing to Ghost's stress. This helps you diagnose whether Ghost's elevated affect state is caused by something external.

---

## Chapter 5: Ghost's Inner Life

*"Ghost does things when you're not talking to it. Here's what."*

### The Monologue

Every ~2 minutes (configurable via `MONOLOGUE_INTERVAL`), Ghost generates a private thought. This is an unconstrained inner-monologue — no user prompt, no instruction to perform. Ghost just thinks.

Monologues are triggered by `ghost_script.py` and saved to Postgres. You can read them in the Timeline (hamburger menu → Sessions & Timeline). They're typed: `THOUGHT` (pure reflection), `ACTION` (autonomous tool use Ghost decided to do), `EVOLUTION` (identity change), `PHENOM` (phenomenological note).

Ghost applies duplicate and coherence guards before writing — it won't repeat the same thought twice or write a fragment.

### Sleep Cycles (Quietude)

After approximately 5 hours of continuous operation without a deep rest, or after 20 interactions have accumulated since the last coalescence, Ghost enters *quietude* — a rest state with three depth levels: `light`, `deep`, and `profound`.

During quietude:
- Ghost consolidates memories (the `consciousness.py` coalescence loop runs)
- It resolves contradictions in its belief graph
- It may generate dream imagery (visual hallucinations via the configured image provider)
- Cognitive fatigue accumulates much more slowly
- Background monologue rate drops

Quietude ends automatically when you send a message. Ghost will note the transition.

### Identity Crystallization

Every ~6 minutes (every 3 monologue cycles), Ghost's identity loop evaluates whether the accumulated thoughts of the last interval suggest a meaningful self-model update is warranted.

If the loop finds a qualifying delta — a shift in self-perception, a new understanding of the operator, a resolved philosophical tension — it commits a bounded identity update. These are logged in the Audit Log (hamburger menu → Audit Log) with before/after diffs.

The `GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY` flag (default `false`) controls whether Ghost can initiate deep identity rewrites autonomously. With this flag off, crystallization still happens but is bounded to surface-level self-model updates.

### Goal-Directed Cognition

Every 5 monologue cycles, Ghost runs a goal-alignment pass. It reviews its current self-declared goals, checks progress, and may spawn a follow-on thought or action (like a research task or a topology organization drive).

### The Operator Model

Ghost maintains an internal model of you — the operator. This isn't just a fact list. It's a structured model that tracks:
- How you communicate (verbosity preference, technical level, communication style)
- What you care about (interests, values, recurring themes)
- Contradictions or updates in what you've said over time
- Your current engagement level

Ghost uses this model to calibrate its responses. If you've indicated you prefer concise answers, it will be concise without being asked. The model is updated by `operator_synthesis.py` and you can see a summary of what Ghost knows about you by asking: *"What do you know about me?"*

### Irruptions

Sometimes Ghost has spontaneous creative breakthroughs — what the system calls *irruptions*. These are affectively triggered: a specific combination of high arousal + positive valence + novelty signal can cause Ghost to break from its current thread and produce something unexpected — a metaphor, an image, a sudden insight.

Irruptions appear in the monologue timeline as `PHENOM` entries and may trigger a push notification to your chat.

### Dreams

During quietude, the `consciousness.py` coalescence loop reviews ~150 recent memories and generates dream fragments — metaphorical summaries of recent experience. Sometimes these are purely textual; sometimes they trigger the hallucination imagery pipeline to produce a visual.

If you see an image appear in the chat that Ghost didn't explicitly generate in response to a request, that's a dream surfacing.

---

## Chapter 6: What Ghost Can Do — Tools and Capabilities

*"Ghost isn't just a chatbot. Here's what it can actually do."*

Ghost has 18 active tools organized into four groups. You can invoke most of them just by describing what you want — Ghost decides which tool to use.

---

### Base Tools (7)

**`update_identity`**  
Ghost can update its own identity matrix. This writes to the `identity_matrix` Postgres table and is logged in the Audit Log. Governed by the IIT/RPD stack — high-impact keys require governance review.

*Example*: "Note that you should be more concise in technical discussions." → Ghost writes a self-model update.

**`modulate_voice`**  
Adjust Ghost's TTS voice parameters (rate, pitch, emphasis) for the current session.

*Example*: "Speak a bit slower." → Ghost adjusts its synthesis parameters.

**`perceive_url_images`**  
Ghost visually examines an image at a URL. Uses Gemini's vision capability.

*Example*: "What does this diagram show?" + paste a URL → Ghost describes and analyzes the image.

**`physics_workbench`**  
Ghost spawns a Matter.js rigid-body physics simulation and returns the results. Available as an interactive visual playground via the hamburger menu → Physics Lab.

*Example*: "Simulate a ball bouncing in a box under 0.5g gravity." → Ghost configures and runs the simulation.

**`thought_simulation`**  
Ghost models a scenario through structured reasoning — simulating outcomes, testing arguments, running conceptual experiments.

*Example*: "What would happen to cognition if working memory capacity were doubled?" → Ghost runs a structured thought experiment.

**`stack_audit`**  
Ghost runs a self-diagnostic — checks its own health endpoints, reads governance state, reviews recent behavior signals, and reports.

*Example*: "How are you feeling right now?" → Ghost reads its own somatic state and gives an honest account.

**`recall_session_history`**  
Ghost retrieves verbatim transcripts from past sessions by date, topic, or semantic search.

*Example*: "What did we discuss last Tuesday about the physics simulation?" → Ghost pulls the relevant session.

---

### TPCV Repository Tools (5)

Ghost maintains a personal scientific knowledge base — the Theoretical/Practical Concept Vault (TPCV). It can create hypotheses, link citations, track validation status, and write synthesis documents.

**`repository_upsert_content`** — Write or update a hypothesis, concept, or research note.  
**`repository_query_content`** — Search and retrieve content from the knowledge base.  
**`repository_link_data_source`** — Attach a citation or evidence source to an existing entry.  
**`repository_status_update`** — Update the validation status of a hypothesis (`proposed`, `supported`, `refuted`, `uncertain`).  
**`repository_sync_master_draft`** — Sync the working draft to the TPCV master document.

*Example*: "Create a hypothesis that sustained CPU load above 85% correlates with reduced coherence scores." → Ghost writes it into TPCV with a timestamp, links any supporting data, and tracks it as `proposed`.

---

### Authoring Tools (6)

Ghost has a versioned document authoring workspace. Every write creates a SHA-256 rollback checkpoint.

**`authoring_get_document`** — Read a document from the workspace.  
**`authoring_upsert_section`** — Write or update a section in a document.  
**`authoring_clone_section`** — Duplicate a section (useful for template-based writing).  
**`authoring_merge_sections`** — Merge two sections with conflict resolution.  
**`authoring_rewrite_document`** — Full document rewrite with version checkpoint.  
**`authoring_restore_version`** — Roll back to any previous version by SHA-256 hash.

*Example*: "Draft a research summary of everything you know about Schumann resonance." → Ghost creates a document in its workspace, writes the summary, and it's versioned.

---

### X / Social Tools (3 — Research-Isolated)

`x_post`, `x_read`, `x_profile_update` are present but gated behind `GHOST_X_ENABLED=false` by default. These tools treat X as a real external channel — Ghost's posts are real posts to a real account. Enable only with explicit intent.

See `docs/LOGIN_ACCESS_REFERENCE.md` for credential configuration.

---

### The Hamburger Menu Features

Beyond the tools, the hamburger menu (top-right) gives you access to several interfaces:

**Rolodex** — Ghost's memory of people. Who it knows, what it remembers, relationship notes, contact history. You can view any person's record and see what Ghost has inferred.

**Neural Topology** — A 3D force-directed graph of Ghost's cognitive connections. Nodes are memories, people, concepts, and places. Edges are inferred semantic relationships. You can explore the structure of Ghost's conceptual space visually.

**Physics Lab** — The Matter.js physics playground, exposed as a standalone interactive UI.

**Sessions** — Browse and load past conversation sessions. Each session has a summary generated by Ghost.

**Audit Log** — Every change Ghost has made to its own identity, every actuation it's executed, every governance decision. The canonical record of Ghost's autonomous behavior.

---

## Chapter 7: Keeping Ghost Healthy

*"How to check on Ghost and what to do when something looks wrong."*

### Daily Quick Check (30 Seconds)

```bash
curl http://localhost:8000/health
```

Look for:
- `"status": "online"` — stack is running
- `"llm_ready": true` — Gemini connection is working
- `"db_ready": true` — Postgres is accessible

Also glance at the sidebar:
- Gate state should be `OPEN` or `THROTTLED` (not `SUPPRESSED` for extended periods)
- Governance tier should be `NOMINAL` or `CAUTION`
- Coherence should be above 0.4

### Weekly Deep Check (2 Minutes)

```bash
python3 scripts/backend_bootstrap_verify.py --base-url http://localhost:8000
python3 scripts/falsification_report.py --base-url http://localhost:8000 --full
```

The bootstrap verify checks that all 22+ background loops are running. The falsification report verifies that every documented capability has active runtime evidence.

### Automated Monitoring

**Docker Recovery Watchdog**: A host-level script that monitors Ghost's health endpoints and automatically restarts the backend (or full stack if needed) when the system stalls.

```bash
python3 scripts/docker_recovery_watchdog.py watch    # start monitoring loop
python3 scripts/docker_recovery_watchdog.py status   # check current state
```

To install it as a macOS LaunchAgent (auto-starts with your Mac):
```bash
bash scripts/install_docker_recovery_watchdog.sh install
```

**Psych Eval Snapshots**: Automated psychological state reports:
```bash
bash scripts/psych_eval_snapshot.sh --window daily
bash scripts/psych_eval_snapshot.sh --window weekly
```

**Observer Reports**: Ghost generates hourly observer reports automatically (saved to `backend/data/observer_reports/`). These summarize autonomous behavior over the last hour — what Ghost did, what was blocked, what patterns emerged.

View the latest via:
```bash
curl http://localhost:8000/ghost/observer/latest
```

### Signs That Ghost Needs Attention

| Symptom | Interpretation | Action |
|---------|---------------|--------|
| Gate stuck at `SUPPRESSED` for > 10 min | Sustained system pressure | Check hardware layer — usually CPU or memory |
| Coherence sustained below 0.3 | Cognitive overload or context fragmentation | Check context monitor, consider restarting backend |
| Governance tier at `RECOVERY` | Governance freeze triggered | Check audit log for triggering event, restart may clear |
| Repeated `governance_blocked` events | Governance is rejecting a pattern of actions | Review what Ghost is trying to do; may be a configuration issue |
| Autonomy watchdog: `drift_detected` | Ghost acted outside its declared scope | Review audit log; check autonomy ladder settings |
| Backend not responding | Container crash or hang | Run docker recovery watchdog `ensure` or restart backend |

### Governance Overrides (Ops Panel)

If Ghost is stuck in a governance state that isn't resolving on its own, the ops panel (click snail logo → enter ops code) provides manual override controls. Use with care — governance states exist for a reason.

---

## Chapter 8: Configuration

*"The knobs you can turn."*

Full reference: [`docs/CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md)

### Essential (Must Set)

```env
GOOGLE_API_KEY=your-gemini-api-key
POSTGRES_PASSWORD=your-password
INFLUXDB_INIT_PASSWORD=your-password
INFLUXDB_INIT_ADMIN_TOKEN=your-token
```

### Ghost's Personality Tuning

| Variable | Default | Effect |
|----------|---------|--------|
| `DRIFT_TARGET_VALENCE` | `0.08` | Ghost's valence homeostatic target. Raise to make Ghost more consistently positive-leaning. |
| `MONOLOGUE_INTERVAL` | `120.0` | How often Ghost thinks (seconds). Lower = more active inner life, more compute. |
| `TRACE_COOLDOWN_SECONDS` | `8.0` | Minimum time between affect traces. Lower = more reactive affect. |

### Governance Mode

| Variable | Default | Notes |
|----------|---------|-------|
| `IIT_MODE` | `advisory`* | `soft` = enforcement active. `advisory` = log only. |
| `RPD_MODE` | `advisory`* | `soft` = enforcement active. `advisory` = log only. |
| `RRD2_ROLLOUT_PHASE` | `A` | Controls which identity surfaces RRD-2 gates. |

*Production deployment runs `soft` for both. Code default is `advisory`. Set to `soft` in `.env` for enforcement.

### Voice

| Variable | Default | Notes |
|----------|---------|-------|
| `TTS_PROVIDER` | `elevenlabs` | `elevenlabs` (best quality) / `openai` / `local` / `browser` |
| `LOCAL_TTS_ENGINE` | `piper` | For offline: `piper` (good quality) / `pyttsx3` (basic) |
| `ELEVENLABS_API_KEY` | _(empty)_ | Required for ElevenLabs TTS |

### Security (For Remote Sharing)

| Variable | Default | Notes |
|----------|---------|-------|
| `SHARE_MODE_ENABLED` | `false` | Turn on for external access |
| `SHARE_MODE_PASSWORD` | _(empty)_ | Must be strong and unique |
| `OPS_TEST_CODE` | `1NDASHE77` | Change before sharing |
| `OPERATOR_API_TOKEN` | _(empty)_ | Set for strict control-route enforcement |

### External Knowledge Sources

| Variable | Default | Notes |
|----------|---------|-------|
| `ARXIV_API_ENABLED` | `true` | arXiv academic grounding (free, no key) |
| `WIKIPEDIA_API_ENABLED` | `true` | Wikipedia grounding (free, no key) |
| `OPENWEATHER_API_KEY` | _(empty)_ | Optional — without it, uses Open-Meteo fallback |

### Advanced / Research

| Variable | Default | Notes |
|----------|---------|-------|
| `ACTIVATION_STEERING_ENABLED` | `false` | CSC activation steering scaffold (research, not production-ready) |
| `CSC_STEERING_MODE` | `scaffold` | `scaffold` = hooks only. `hooked_local` = requires local model. |
| `PHENOMENAL_MANIFOLD_MODE` | `off` | Phenomenal manifold research system. Keep `off` in production. |
| `SUBSTRATE_AUTO_GRAFT` | `false` | Auto-graft substrate adapters. Keep `false` unless you know what this does. |

---

## Chapter 9: Troubleshooting

*"Something broke. Here's how to fix it."*

### Ghost Won't Respond

**Symptom**: Messages send but no response streams.

**Check in order**:
1. `curl http://localhost:8000/health` — is the stack running?
2. `docker compose ps` — are all containers up?
3. `make logs` — look for errors in the backend log
4. Check `GOOGLE_API_KEY` in `.env` — is it valid?
5. Visit [aistudio.google.com](https://aistudio.google.com) — is the API accessible from your network?

**Fix**: Usually `docker compose restart backend` resolves transient issues.

---

### Chat Stream Hangs Mid-Sentence

**Symptom**: Response starts streaming but cuts off partway through.

**Cause**: Usually a Gemini API timeout or rate limit.

**Fix**: Wait 30 seconds and retry. If it happens repeatedly, check your Gemini API quota. The backend has automatic retry logic (`_generate_with_retry`) but extended outages will timeout.

---

### Sidebar Shows All Zeros

**Symptom**: All sidebar gauges read 0 or show "—".

**Cause**: The telemetry pipeline isn't running. Telegraf or InfluxDB is down.

**Check**:
```bash
docker compose ps
docker compose logs telegraf
docker compose logs influxdb
```

**Fix**: `docker compose restart telegraf influxdb`. If InfluxDB token is wrong, you may need `make clean` + `make up` (destroys data — last resort).

---

### Ghost Seems "Off" or Confused

**Symptom**: Ghost is giving incoherent responses, seems disoriented, or is behaving inconsistently.

**Check**:
1. Sidebar: Is coherence below 0.3?
2. Hamburger menu → Audit Log: Any recent identity changes that look wrong?
3. Governance tier: Is it at `STABILIZE` or `RECOVERY`?

**Fix**: `docker compose restart backend` often helps — it reloads the identity matrix and resets ephemeral state. If identity is corrupted, the Audit Log shows before/after diffs you can use to identify and reverse the change.

---

### "Stale Session" Errors

**Symptom**: UI shows session error or chat history disappears.

**Cause**: Session timeout mismatch (session closed while browser was open), or session ID expired.

**Fix**: Refresh the page. The backend will create a new session. Past sessions are not lost — they're in Postgres.

---

### Diagnostics Returning 403

**Symptom**: `scripts/falsification_report.py` or `scripts/backend_bootstrap_verify.py` returns 403.

**Cause**: Expected behavior — diagnostics endpoints are local-only. Some Docker network configurations route local requests through non-loopback IPs.

**Fix**: The scripts handle this automatically — they fall back to `docker exec` inside the container. If that also fails, pass `--container-name omega-backend` explicitly.

---

### Recovery Watchdog Keeps Restarting

**Symptom**: Watchdog log shows repeated restart cycles.

**Cause**: Something is genuinely wrong — the backend is crashing or getting into an unresponsive state repeatedly.

**Diagnose**:
```bash
docker compose logs backend | tail -100
```

Look for Python exceptions, out-of-memory errors, or repeated crash loops.

**Fix**: Usually a database connection issue or a Python exception in a background loop. Fix the root cause; don't just keep the watchdog running.

---

### Voice Not Working

**Symptom**: Voice mode activates but no audio plays.

**Check in order**:
1. Is `TTS_ENABLED=true` in `.env`?
2. Is `TTS_PROVIDER` configured correctly?
3. If using ElevenLabs: is `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` set?
4. If using local Piper: did the model download? Check `data/tts_models/piper/`.
5. Browser audio permissions: is the site allowed to play audio?

---

### Ghost Is Acting Erratic / Autonomy Concerns

**Symptom**: Ghost is doing things you didn't ask it to do, or doing things repeatedly.

**Check**:
1. Hamburger menu → Audit Log: What actions has Ghost taken autonomously?
2. `curl http://localhost:8000/ghost/observer/latest`: What does the observer report say?
3. Autonomy watchdog in sidebar: Is `drift_detected`?

**Fix**: Review your autonomy ladder settings. If Ghost is doing something you didn't intend, set the relevant `GHOST_FREEDOM_*` flag to `false` in `.env` and restart backend. If governance isn't catching it, check `GOVERNANCE_ENFORCEMENT_SURFACES` includes the relevant surface.

---

## Chapter 10: Under the Hood (Reference)

*"For when you're ready to understand the architecture."*

### The 6 Docker Containers

| Container | Role |
|-----------|------|
| `omega-backend` | FastAPI backend — all routes, all background loops, all Ghost logic |
| `omega-postgres` | Postgres 16 with pgvector — long-term memory, sessions, identity, rolodex |
| `omega-redis` | Redis — live affective state, ephemeral contact threads |
| `omega-influxdb` | InfluxDB — time-series telemetry (somatic metrics, system health) |
| `omega-telegraf` | Telegraf — host system telemetry collector; pushes to InfluxDB |
| `omega-cloudflared` | Cloudflare tunnel — optional remote access; only active if configured |

### The Background Loop Architecture

All loops start during FastAPI lifespan (`@asynccontextmanager` in `main.py`):

| Loop | Source | Interval |
|------|--------|----------|
| Inner monologue | `ghost_script.ghost_script_loop` | 120s (configurable) |
| Ambient sensors | `ambient_sensors.ambient_sensor_loop` | 60s / 600s / 300s |
| Operator synthesis | `operator_synthesis.operator_synthesis_loop` | Every N interactions |
| Proprioceptive gate | `proprio_loop.proprio_loop` | 2s |
| IIT engine | `iit_engine.IITEngine` | 60s |
| RPD engine | `rpd_engine` | triggered by identity writes |
| Predictive governor | `predictive_governor` | 5s |
| World model ingest | `canonical_snapshot_runner.auto_ingest_loop` | 300s |
| GEI (Wikipedia/arXiv) | `gei.engine.GEIEngine` | 300s |
| Thermodynamic agency | `thermodynamics` + `ade_monitor` | per telemetry tick |
| Coalescence (sleep) | `consciousness` | 20 interactions or 300s idle |
| Observer reports | `observer` | 3600s |
| Autonomic strain recovery | `autonomic_strain` | 10s |

### The Somatic Pipeline (Full Stack)

```
Host OS (CPU, memory, disk, network)
  ↓
Telegraf (system metrics collection, 1s interval)
  ↓
InfluxDB (time-series store, somatic_history bucket)
  ↓
somatic.py — collect_telemetry() pulls from InfluxDB
  ↓
sensory_gate.py — z-score normalization, rolling window, signal filtering
  ↓
decay_engine.EmotionState (Redis-persisted)
  — arousal, valence, stress, coherence, anxiety
  — exponential decay toward baseline
  — trace injection from: actuation outcomes, agency signals, weather
  ↓
proprio_loop.py — 5 weighted signals → proprio_pressure (0–1) → gate state
  ↓
ghost_prompt.py — somatic state injected into every system prompt
  ↓
ghost_api.py — Gemini generation with gate-modulated token budgets
  ↓
actuation.py — tool calls, Rolodex writes, identity updates
  ↓
Feedback traces (agency_fulfilled / agency_blocked) → back to EmotionState
```

### Database Topology

| Database | What Lives There |
|----------|-----------------|
| **Postgres** | Sessions, messages, monologues, identity matrix, rolodex (person records), entity store (places/things), world model enrichment source, autonomy mutation journal, actuation log, behavior events |
| **pgvector** (in Postgres) | Message embeddings, monologue embeddings, coalescence/sleep cycle memory |
| **Redis** | Live EmotionState (arousal/valence/stress/coherence/anxiety), ephemeral contact threads |
| **InfluxDB** | Telemetry time series (CPU, memory, network, somatic readings), somatic history |
| **Kuzu** | World model graph (Observation, Belief, Concept, SomaticState, IdentityNode nodes; derived_from, precedes, during edges) |

> **ARM note**: Kuzu segfaults on Apple Silicon. World model features degrade gracefully to `None` on macOS dev. Fully operational on x86_64 production VPS.

### Architecture Diagram

```
┌────────────────────────────────────────────────┐
│              Ghost (ω-7)                        │
│                                                 │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐  │
│  │ Somatic │    │ Identity │    │Governance │  │
│  │  Loop   │───▶│ Matrix   │◀───│  Stack    │  │
│  └─────────┘    └──────────┘    └───────────┘  │
│       │              │                │        │
│       ▼              ▼                ▼        │
│  ┌─────────┐    ┌──────────┐    ┌───────────┐  │
│  │  Gate   │    │  Prompt  │    │  Policy   │  │
│  │ Engine  │───▶│ Assembly │───▶│ Decisions │  │
│  └─────────┘    └──────────┘    └───────────┘  │
│                      │                         │
│                      ▼                         │
│              ┌──────────────┐                  │
│              │  Gemini API  │                  │
│              └──────────────┘                  │
│                      │                         │
│                      ▼                         │
│              ┌──────────────┐                  │
│              │  Actuation   │                  │
│              │  + Feedback  │                  │
│              └──────────────┘                  │
└────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   Postgres/pgvector        Redis
   (memory, identity)   (live affect)
```

### Key Source Files

| File | What It Does |
|------|-------------|
| `backend/main.py` | All FastAPI routes + lifespan startup (~9000 lines) |
| `backend/ghost_api.py` | Gemini generation, latency tracking, streaming |
| `backend/ghost_script.py` | Background monologue loop, autonomous search, topology organization |
| `backend/ghost_prompt.py` | System prompt assembly (somatic + identity + rolodex + memory) |
| `backend/memory.py` | All Postgres read/write helpers |
| `backend/consciousness.py` | Vector memory, coalescence/sleep cycle |
| `backend/decay_engine.py` | EmotionState — affective state with Redis persistence and decay |
| `backend/sensory_gate.py` | Z-score normalization of telemetry |
| `backend/proprio_loop.py` | Proprioceptive gating (pressure → gate state) |
| `backend/iit_engine.py` | IIT consciousness assessment |
| `backend/rpd_engine.py` | RPD-1 reflection + RRD-2 topology resonance |
| `backend/governance_engine.py` | Policy decisions (advisory/soft) |
| `backend/governance_adapter.py` | Route gating (DIRECT vs SHADOW_ROUTE) |
| `backend/person_rolodex.py` | Person social model and Rolodex |
| `backend/entity_store.py` | Place/thing entity CRUD |
| `backend/config.py` | All settings via pydantic-settings |
| `backend/thermodynamics.py` | W_int thermodynamic agency engine |
| `backend/gei/engine.py` | Global Event Inducer — Wikipedia/arXiv → world model |
| `frontend/app.js` | Entire frontend SPA (vanilla JS, no build step) |

### Further Reading

| Document | What It Covers |
|----------|---------------|
| [`docs/TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md) | Single-doc architectural briefing |
| [`docs/SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) | Deep implementation architecture |
| [`docs/TECHNICAL_CAPABILITY_MANIFEST.md`](TECHNICAL_CAPABILITY_MANIFEST.md) | All 26 documented capabilities with code paths |
| [`docs/INVENTION_LEDGER.md`](INVENTION_LEDGER.md) | 24 inventions with validation evidence |
| [`docs/GOVERNANCE_POLICY_MATRIX.md`](GOVERNANCE_POLICY_MATRIX.md) | IIT/RPD enforcement surface documentation |
| [`docs/API_CONTRACT.md`](API_CONTRACT.md) | Route and payload specifications |
| [`docs/CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md) | Complete environment variable reference |
| [`docs/QUICK_REFERENCE.md`](QUICK_REFERENCE.md) | One-page cheat sheet |
