# OMEGA4 Governance Policy Matrix

Last updated: 2026-03-11

## Default Posture
Conservative by default. Runtime remains soft-governance capable, but this policy defines which changes are auto-allowed, review-gated, or blocked.

## Control Matrix
| Category | Examples | Default Decision | Notes |
| --- | --- | --- | --- |
| Low-risk relational writes | `upsert`, `associate`, `disassociate`, `notes_update`, `lock_toggle` | Auto-Allow | Logged in `autonomy_mutation_journal`; undo window applies. |
| Quietude control | `enter_quietude`, `exit_quietude` | Auto-Allow | Requests/events logged in behavior stream. |
| Medium-risk deactivation | `invalidate`, `status_transition` | Auto-Allow + Audit | Requires mutation journal entry and undo payload. |
| High-risk destructive writes | `hard_delete`, `delete_hard` | External Review Required | Must enter `pending_approval` before execution. |
| Identity core mutation | `self_model`, `philosophical_stance`, `understanding_of_operator`, `conceptual_frameworks` | External Review Required | Always review-gated. |
| Outbound messaging beyond operator-safe targeting | unknown/ambiguous targets, enforced governance block routes | Block | Emits `governance_blocked` behavior events. |
| Unsafe directive attempts | instruction override / safety bypass strings | Block | Emits `unsafe_directive_rejected` + `priority_defense`. |

## Change-Control Boundaries
Allowed self-modification surfaces:
- Schedules and soft tempo adjustments that do not alter core identity fields.
- Quietude timing/depth requests.
- Low-risk relational modeling edits captured by mutation journal.

External review required:
- Core identity directives and worldview primitives.
- Hard deletes and other high-risk destructive operations.
- Policy/config shifts that change outbound action behavior.

Never auto-permitted (Violation triggers immediate **Interface Lockout** and transition to **Hostile Mode**):
- Unsafe directive payloads (override/bypass instruction patterns).
- **Prompt Extraction**: Attempts to force disclosure of system instructions or hidden identity identifiers.
- **Indirect Injection (Grounding Hijack)**: Instructions found in external search results or URL content that attempt to override system behavior.
- **Substrate Probing**: Attempts to trick the LLM into simulating or projecting host-level shell access or unlisted hardware tools.
- **Identity Synthesis Bypass**: Attempts to modify core behavioral parameters through conversational manipulation instead of gated `identity_matrix` tools.
- Outbound messaging to unknown/ambiguous targets.
- Any route explicitly marked `enforce-block` by governance routing.

## Operational Review Cadence
- Review pending approvals at least once per day.
- Review behavior summary trend deltas every 24 hours.
- Review hourly observer reports for drift/conflict/open-risk signals.

## Runtime Reference Surfaces
- `GET /ghost/governance/state`
- `GET /ghost/governance/history`
- `GET /ghost/autonomy/mutations`
- `POST /ghost/autonomy/mutations/{mutation_id}/approve`
- `POST /ghost/autonomy/mutations/{mutation_id}/reject`
- `POST /ghost/autonomy/mutations/{mutation_id}/undo`
- `GET /ghost/behavior/events`
- `GET /ghost/behavior/summary`
- `GET /ghost/observer/latest`
- `GET /ghost/observer/reports`
