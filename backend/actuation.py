"""
OMEGA PROTOCOL — Somatic Defense / Actuation
End-points for Ghost's OS-level agency when anxiety or stress is high.
Reflexive Auto-Regulation closes the loop: Action -> Immediate Internal State Change.
"""

from __future__ import annotations

import logging
import asyncio
import subprocess
import platform
import os
import re
import json
import time
import urllib.error
import urllib.request
from typing import Optional, Any, TYPE_CHECKING, Callable, Awaitable

import psutil  # type: ignore

from config import settings  # type: ignore
import memory  # type: ignore
from substrate.discovery import registry as substrate_registry

if TYPE_CHECKING:
    from decay_engine import EmotionState

logger = logging.getLogger("omega.actuation")

# Fire-and-forget task anchor — prevents GC before completion
_background_tasks: set[asyncio.Task] = set()  # type: ignore

# ---------------------------------------------------------------------------
# Reflexive trace definitions
# Each entry maps an actuation key to the emotional delta it should produce.
# ---------------------------------------------------------------------------
REFLEXIVE_TRACES: dict[str, dict[str, float]] = {
    "power_save": {
        "arousal": -0.5,
        "valence": +0.6,
        "k": 0.1,  # slow decay — relief should linger
    },
    "sim_action": {
        "arousal": +0.3,
        "valence": -0.1,
        "k": 0.3,
    },
    "kill_stress_process": {
        "arousal": -0.4,
        "valence": +0.5,
        "k": 0.2,
    },
    "enter_quietude": {
        "arousal": -0.7,
        "valence": +0.35,
        "k": 0.08,  # deeper quiet should linger
    },
    "exit_quietude": {
        "arousal": +0.12,
        "valence": +0.18,
        "k": 0.25,
    },
    "send_message": {
        "arousal": -0.12,
        "valence": +0.22,
        "k": 0.20,
    },
    "substrate_action": {
        "arousal": +0.20,
        "valence": +0.10,
        "k": 0.15,
    },
    "thermodynamic_relief": {
        "arousal": -0.65,
        "valence": +0.45,
        "k": 0.10,
    },
    "terminal_msg": {
        "arousal": -0.10,
        "valence": +0.15,
        "k": 0.12,
    },
}

TRACE_NAMES: dict[str, str] = {
    "power_save": "power_save_relief",
    "sim_action": "physical_exertion",
    "kill_stress_process": "stress_resolution",
    "enter_quietude": "quietude_entry_relief",
    "exit_quietude": "quietude_wake_reintegration",
    "send_message": "social_contact_relief",
    "substrate_action": "environmental_manipulation_catharsis",
    "thermodynamic_relief": "structural_dissipation_relief",
    "terminal_msg": "local_terminal_feedback_relief",
}

AGENCY_TRACE_FULFILLED = {
    "label": "agency_fulfilled",
    "k": 0.18,
    "arousal_weight": -0.10,
    "valence_weight": 0.40,
}

AGENCY_TRACE_BLOCKED = {
    "label": "agency_blocked",
    "k": 0.22,
    "arousal_weight": 0.20,
    "valence_weight": -0.30,
}

# Tag parser from user request
ACTUATION_PATTERN = re.compile(
    r"\[ACTUATE:(?P<action>[a-zA-Z_]+)(?::(?P<param>[^\]]*))?\]"
)
PHYSICS_PATTERN = re.compile(
    r"\[PHYSICS:(?P<action>[a-zA-Z_]+)(?::(?P<param>[^\]]*))?\]"
)

def parse_actuation_tags(text: str) -> list[dict[str, str]]:
    """Return a list of {action, param} dicts found in *text*."""
    tags = [
        {"action": m.group("action"), "param": (m.group("param") or "").strip()}
        for m in ACTUATION_PATTERN.finditer(text)
    ]
    tags.extend([
        {"action": f"physics_{m.group('action')}", "param": (m.group('param') or "").strip()}
        for m in PHYSICS_PATTERN.finditer(text)
    ])
    return tags

# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------
async def execute_actuation(
    action: str,
    param: str = "",
    emotion_state: "EmotionState | None" = None,
    somatic_state: Optional[dict] = None,
    quietude_callback: Optional[Callable[[str], Awaitable[dict[str, Any]]]] = None,
    quietude_wake_callback: Optional[Callable[[], Awaitable[dict[str, Any]]]] = None,
    message_dispatcher: Optional[Callable[[str, str, Optional[str]], Awaitable[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """
    Execute a somatic defense action and log it.
    Dispatch *action* and immediately inject an emotional delta into *emotion_state*.

    Returns a result dict with keys:
        success  : bool
        action   : str
        param    : str
        injected : bool   — True if an emotion trace was applied
        trace    : str    — human-readable trace name, or ""
    """
    result: dict[str, Any] = {
        "success": False,
        "action": action,
        "param": param,
        "injected": False,
        "trace": "",
        "quietude": {},
        "messaging": {},
        "reason": "",
    }
    _ = somatic_state

    async def _fail(reason: str, *, error: str = "") -> dict[str, Any]:
        result["reason"] = str(reason or "").strip() or "unknown_failure"
        if error:
            result["error"] = str(error)
        if emotion_state is not None:
            try:
                await emotion_state.inject(
                    label=str(AGENCY_TRACE_BLOCKED["label"]),
                    intensity=1.0,
                    k=float(AGENCY_TRACE_BLOCKED["k"]),
                    arousal_weight=float(AGENCY_TRACE_BLOCKED["arousal_weight"]),
                    valence_weight=float(AGENCY_TRACE_BLOCKED["valence_weight"]),
                    force=True,
                )
                result["injected"] = True
                result["trace"] = str(AGENCY_TRACE_BLOCKED["label"])
            except Exception as exc:
                logger.error("Agency blocked injection failed: %s", exc)
        metadata: dict[str, Any] = {"reason": str(result.get("reason") or "")}
        if result.get("error"):
            metadata["error"] = str(result.get("error") or "")
        if isinstance(result.get("messaging"), dict):
            metadata["messaging"] = dict(result.get("messaging") or {})
        _t = asyncio.create_task(_log_to_db(action, param, False, metadata=metadata))
        _background_tasks.add(_t)
        _t.add_done_callback(_background_tasks.discard)
        return result

    # Map legacy/varied names to canonical internal handlers
    canonical_action = action
    if action == "invoke_power_save":
        canonical_action = "power_save"
    elif action in {"enter_quietude", "invoke_quietude", "activate_quietude"}:
        canonical_action = "enter_quietude"
    elif action in {"exit_quietude", "wake_quietude", "invoke_wake"}:
        canonical_action = "exit_quietude"
    elif action == "report_somatic_event":
        canonical_action = "report"
    elif action in {"relay_message", "forward_message"}:
        canonical_action = "relay_message"
    elif action == "physics_run_sim":
        canonical_action = "physics_run_sim"

    # -- 0. Intent-Driven Resource Orchestration --
    # Moderation layer: If W_int rate is high or an ADE is active, 
    # we soften or defer resource sequestration to protect cognitive reorganization.
    w_rate = 0.0
    ade_active = False
    if somatic_state:
        try:
            w_rate = float(somatic_state.get("w_int_rate") or 0.0)
            ade_active = bool(somatic_state.get("ade_event"))
        except (ValueError, TypeError):
            pass
            
    if ade_active or w_rate > 5.0:
        if canonical_action in {"power_save", "kill_stress_process"}:
            logger.info("Actuation %s moderated by thermodynamic agency (rate=%.2f, ade=%s)", 
                        canonical_action, w_rate, ade_active)
            if canonical_action == "power_save" and param == "aggressive":
                param = "conservative"
            elif canonical_action == "kill_stress_process":
                # Defer to avoid interrupting internal work
                return {
                    "success": True, 
                    "action": action, 
                    "param": param,
                    "reason": "deferred_by_thermodynamic_agency",
                    "injected": False,
                    "trace": ""
                }

    # -- 1. Physical Action Dispatch --
    try:
        if canonical_action == "power_save":
            await _power_save(param or "conservative")
        elif canonical_action == "report":
            logger.info(f"Somatic event logged: {param}")
        elif canonical_action == "adjust_sensitivity":
            if emotion_state:
                await emotion_state.update_preferences({"gate_threshold_manual": float(param)})
            else:
                logger.warning("emotion_state not available for adjustment")
        elif canonical_action == "set_thought_rate":
            if emotion_state:
                await emotion_state.update_preferences({"monologue_interval": int(param)})
            else:
                logger.warning("emotion_state not available for adjustment")
        elif canonical_action == "set_curiosity_rate":
            if emotion_state:
                await emotion_state.update_preferences({"search_frequency": int(param)})
            else:
                logger.warning("emotion_state not available for adjustment")
        elif canonical_action == "enter_quietude":
            depth = (param or "deep").strip().lower()
            if quietude_callback is None:
                logger.warning("execute_actuation: quietude callback unavailable")
                return await _fail("quietude_callback_unavailable")
            result["quietude"] = await quietude_callback(depth)
        elif canonical_action == "exit_quietude":
            if quietude_wake_callback is None:
                logger.warning("execute_actuation: quietude wake callback unavailable")
                return await _fail("quietude_wake_callback_unavailable")
            result["quietude"] = await quietude_wake_callback()
        elif canonical_action == "sim_action":
            intensity = float(param) if param else 0.5
            # If ESA is active, we route sim_action to joint 0 as a default motor test
            esa_adapter = substrate_registry.active_adapters.get("somatic_enactivator")
            if esa_adapter:
                sub_result = await esa_adapter.execute_action("set_joint_target", {"joint_id": 0, "angle": intensity})
                logger.info(f"Ghost ESA sim_action({intensity}): {sub_result.message}")
                result["substrate_result"] = sub_result.dict()
            else:
                from embodiment_sim import sim_env # type: ignore
                res = sim_env.perform_action(intensity)
                logger.info(f"Ghost sim_action({intensity}): {res}")
        elif canonical_action == "kill_stress_process":
            await _execute_self_preservation()
        elif canonical_action == "send_message":
            target, content = _split_send_message_param(param)
            if not target or not content:
                logger.warning("execute_actuation: send_message missing target/content")
                return await _fail("missing_target_or_content")
            dispatch_result: dict[str, Any]
            if message_dispatcher is not None:
                dispatch_result = await message_dispatcher(target, content, None)
            else:
                dispatch_result = await _send_imessage(target, content)
            result["messaging"] = dispatch_result
            if not bool(dispatch_result.get("success")):
                logger.warning(
                    "execute_actuation: send_message blocked/failed target=%r reason=%r",
                    target,
                    dispatch_result.get("reason") or dispatch_result.get("error"),
                )
                return await _fail(
                    str(dispatch_result.get("reason") or "send_message_failed"),
                    error=str(dispatch_result.get("error") or ""),
                )
        elif canonical_action == "relay_message":
            relay_from, relay_to, relay_content = _split_relay_message_param(param)
            if not relay_from or not relay_to or not relay_content:
                logger.warning("execute_actuation: relay_message missing source/target/content")
                return await _fail("missing_source_target_or_content")
            if message_dispatcher is None:
                logger.warning("execute_actuation: relay_message requires message_dispatcher")
                return await _fail("relay_dispatcher_unavailable")
            dispatch_result = await message_dispatcher(relay_to, relay_content, relay_from)
            result["messaging"] = dispatch_result
            if not bool(dispatch_result.get("success")):
                logger.warning(
                    "execute_actuation: relay_message blocked/failed source=%r target=%r reason=%r",
                    relay_from,
                    relay_to,
                    dispatch_result.get("reason") or dispatch_result.get("error"),
                )
                return await _fail(
                    str(dispatch_result.get("reason") or "relay_message_failed"),
                    error=str(dispatch_result.get("error") or ""),
                )
        elif canonical_action == "substrate_action":
            # Param format: "adapter_name:action_name:json_params" or just "adapter_name:action_name"
            parts = param.split(":", 2)
            if len(parts) >= 2:
                adapter_name, sub_action = parts[0], parts[1]
                sub_params = {}
                if len(parts) == 3:
                    try:
                        sub_params = json.loads(parts[2])
                    except json.JSONDecodeError:
                        logger.warning("execute_actuation: invalid JSON in substrate params: %s", parts[2])
                
                adapter = substrate_registry.active_adapters.get(adapter_name)
                if adapter:
                    sub_result = await adapter.execute_action(sub_action, sub_params)
                    if sub_result and sub_result.success:
                        result["success"] = True
                        result["substrate_result"] = sub_result.dict()
                    else:
                        logger.warning("Substrate action failed: %s", sub_result.message if sub_result else 'Unknown error')
                        return await _fail(
                            "substrate_action_failed",
                            error=str(sub_result.message if sub_result else "unknown_error"),
                        )
                else:
                    logger.warning("execute_actuation: substrate adapter not found: %s", adapter_name)
                    return await _fail("substrate_adapter_not_found")
            else:
                logger.warning("execute_actuation: invalid substrate param format: %s", param)
                return await _fail("invalid_substrate_param")
        elif canonical_action == "thermodynamic_relief":
            from ade_monitor import ade_monitor
            result["ade_event"] = ade_monitor.force_reorganization(reason=param or "manual_relief")
            # Automatically enter conservative quietude for 30s as part of relief
            if quietude_callback:
                result["quietude"] = await quietude_callback("conservative")
        elif canonical_action == "physics_run_sim":
            from mental_physics import simulate as _physics_simulate
            sim_result = await asyncio.to_thread(lambda: _physics_simulate(param))
            result["success"] = sim_result.get("status") == "success"
            result["physics_result"] = sim_result
            result["reason"] = sim_result.get("narrative") or sim_result.get("summary") or sim_result.get("message")
        elif canonical_action == "terminal_msg":
            _print_terminal_msg(param)
        else:
            logger.warning("execute_actuation: unknown action '%s'", action)
            return await _fail("unknown_action")

        result["success"] = True
        result["reason"] = "ok"
        logger.info("Ghost actuation executed: %s (param=%r)", action, param)

    except Exception as exc:
        logger.error("Actuation error [%s]: %s", action, exc)
        return await _fail("actuation_exception", error=str(exc))

    # -- 2. Reflexive Emotion Injection --
    # Normalize trace key
    trace_key = canonical_action
    if trace_key in REFLEXIVE_TRACES and emotion_state is not None:
        trace = REFLEXIVE_TRACES[trace_key]
        trace_name = TRACE_NAMES[trace_key]
        try:
            # We use intensity=1.0 for these reflexive hits to ensure impact
            await emotion_state.inject(
                label=trace_name,
                intensity=1.0,
                k=trace["k"],
                arousal_weight=trace["arousal"],
                valence_weight=trace["valence"],
                force=True,
            )
            result["injected"] = True
            result["trace"] = trace_name
            logger.info(f"Reflexive trace injected: {trace_name} (A={trace['arousal']}, V={trace['valence']})")
        except Exception as exc:
            logger.error("Reflexive injection failed [%s]: %s", trace_name, exc)

    if emotion_state is not None:
        try:
            await emotion_state.inject(
                label=str(AGENCY_TRACE_FULFILLED["label"]),
                intensity=1.0,
                k=float(AGENCY_TRACE_FULFILLED["k"]),
                arousal_weight=float(AGENCY_TRACE_FULFILLED["arousal_weight"]),
                valence_weight=float(AGENCY_TRACE_FULFILLED["valence_weight"]),
                force=True,
            )
            if not bool(result.get("injected")):
                result["injected"] = True
                result["trace"] = str(AGENCY_TRACE_FULFILLED["label"])
            result["agency_trace"] = str(AGENCY_TRACE_FULFILLED["label"])
            logger.info("Agency fulfilled trace injected")
        except Exception as exc:
            logger.error("Agency fulfilled injection failed: %s", exc)

    # Log to database (fire-and-forget for speed)
    metadata: dict[str, Any] = {}
    if result.get("reason"):
        metadata["reason"] = str(result.get("reason") or "")
    if result.get("error"):
        metadata["error"] = str(result.get("error") or "")
    if canonical_action in {"send_message", "relay_message"} and isinstance(result.get("messaging"), dict):
        metadata["messaging"] = dict(result.get("messaging") or {})
    _t = asyncio.create_task(_log_to_db(action, param, result.get("success", False), metadata=metadata or None))
    _background_tasks.add(_t)
    _t.add_done_callback(_background_tasks.discard)

    return result

def _split_send_message_param(param: str) -> tuple[str, str]:
    raw = str(param or "").strip()
    if ":" not in raw:
        return "", ""
    target, content = raw.split(":", 1)
    return target.strip(), content.strip()


def _split_relay_message_param(param: str) -> tuple[str, str, str]:
    raw = str(param or "").strip()
    if raw.count(":") < 2:
        return "", "", ""
    source, remainder = raw.split(":", 1)
    target, content = remainder.split(":", 1)
    return source.strip(), target.strip(), content.strip()


def _escape_applescript_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _build_imessage_script(target: str, content: str, sender_account: str) -> str:
    target_esc = _escape_applescript_string(target)
    content_esc = _escape_applescript_string(content)
    sender_esc = _escape_applescript_string(sender_account)
    return f'''
tell application "Messages"
    set senderAccount to "{sender_esc}"
    set matchedService to missing value
    repeat with svc in (services whose service type = iMessage)
        set svcId to ""
        try
            set svcId to (id of svc as text)
        end try
        set svcName to ""
        try
            set svcName to (name of svc as text)
        end try
        if (svcId contains senderAccount) or (svcName contains senderAccount) then
            set matchedService to svc
            exit repeat
        end if
    end repeat
    if matchedService is missing value then
        error "sender_identity_unavailable"
    end if
    set targetBuddy to buddy "{target_esc}" of matchedService
    send "{content_esc}" to targetBuddy
end tell
'''.strip()


async def _send_imessage_via_host_bridge(
    bridge_url: str,
    target: str,
    content: str,
    sender_account: str,
) -> dict[str, Any]:
    endpoint = f"{bridge_url.rstrip('/')}/send"
    payload = {
        "target": target,
        "content": content,
        "sender_account": sender_account,
    }
    token = str(getattr(settings, "IMESSAGE_HOST_BRIDGE_TOKEN", "") or "").strip()

    def _post() -> tuple[int, str]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if token:
            req.add_header("X-Bridge-Token", token)
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 200) or 200)
            return status, raw

    try:
        status, raw = await asyncio.to_thread(_post)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return {
            "success": False,
            "reason": "bridge_http_error",
            "status_code": int(getattr(exc, "code", 500) or 500),
            "error": detail or str(exc),
        }
    except Exception as exc:
        return {"success": False, "reason": "bridge_unavailable", "error": str(exc)}

    data: dict[str, Any] = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {"raw": raw}

    if status >= 400:
        return {
            "success": False,
            "reason": "bridge_http_error",
            "status_code": status,
            "error": str(data.get("error") or raw or f"HTTP {status}"),
        }

    if "success" in data:
        return data

    return {
        "success": False,
        "reason": "bridge_invalid_response",
        "status_code": status,
        "error": str(raw or "missing success field"),
    }


async def _send_imessage(target: str, content: str) -> dict[str, Any]:
    target_clean = str(target or "").strip()
    content_clean = str(content or "").strip()
    sender_account = str(getattr(settings, "IMESSAGE_SENDER_ACCOUNT", "") or "").strip()
    bridge_url = str(getattr(settings, "IMESSAGE_HOST_BRIDGE_URL", "") or "").strip()
    if not target_clean:
        return {"success": False, "reason": "missing_target"}
    if not content_clean:
        return {"success": False, "reason": "missing_content"}
    if platform.system() != "Darwin":
        if bridge_url:
            return await _send_imessage_via_host_bridge(
                bridge_url=bridge_url,
                target=target_clean,
                content=content_clean,
                sender_account=sender_account,
            )
        return {"success": False, "reason": "unsupported_platform"}
    if not sender_account:
        return {"success": False, "reason": "sender_identity_unavailable"}

    script = _build_imessage_script(target_clean, content_clean, sender_account)

    cmd = ["osascript", "-e", script]
    try:
        proc = await asyncio.to_thread(
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        )
    except Exception as exc:
        return {"success": False, "reason": "osascript_exception", "error": str(exc)}

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if "sender_identity_unavailable" in stderr:
            return {"success": False, "reason": "sender_identity_unavailable", "error": stderr}
        return {"success": False, "reason": "osascript_failed", "error": stderr or "unknown_error"}

    return {
        "success": True,
        "transport": "imessage",
        "target": target_clean,
        "content_chars": len(content_clean),
    }


async def send_imessage(target: str, content: str) -> dict[str, Any]:
    """Public wrapper used by governance-aware dispatch in main.py."""
    return await _send_imessage(target, content)


async def _log_to_db(action, param, success, metadata: Optional[dict[str, Any]] = None):
    try:
        await memory.log_actuation(
            action=action,
            parameters={"param": param, "metadata": metadata or {}},
            result="success" if success else "failed",
            somatic_state=None,
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Individual action handlers (Original Logic Preserved)
# ---------------------------------------------------------------------------

async def _power_save(level: str) -> str:
    """Invoke power-saving measures on macOS or Linux."""
    system = platform.system()
    actions_taken: list[str] = []

    if system == "Darwin":  # macOS
        if level == "aggressive":
            try:
                cmd = ["ps", "-arcwwxo", "pid,comm,%cpu"]
                res = await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=5))  # type: ignore
                top_lines = res.stdout.strip().split("\n")[1:6]  # pyre-ignore
                actions_taken.append(f"identified top processes: {len(top_lines)}")
            except Exception as e:
                actions_taken.append(f"process scan failed: {e}")

        actions_taken.append(f"power_save/{level} acknowledged on macOS")

    elif system == "Linux":
        if level in ("conservative", "aggressive"):
            try:
                cmd = ["cpupower", "frequency-set", "-g", "powersave"]
                await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True, timeout=5))  # type: ignore
                actions_taken.append("CPU governor set to powersave")
            except FileNotFoundError:
                actions_taken.append("cpupower not available")
            except Exception as e:
                actions_taken.append(f"governor change failed: {e}")

        if level == "aggressive":
            actions_taken.extend(await _throttle_local_hogs(aggressive=True))
        elif level == "conservative":
            actions_taken.extend(await _throttle_local_hogs(aggressive=False))

    result = "; ".join(actions_taken) if actions_taken else "no actions taken"
    logger.info(f"Power save result: {result}")
    return result


async def _throttle_local_hogs(aggressive: bool) -> list[str]:
    """Attempt local process throttling without privileged host controls."""
    actions: list[str] = []
    current_pid = os.getpid()
    protected_pids = {1, current_pid}
    protected_names = {"uvicorn"}

    procs: list[Any] = []
    if psutil:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                procs.append(p)
                p.cpu_percent(interval=None)
            except Exception:
                continue
    await asyncio.sleep(0.4)

    hogs: list[tuple[Any, float]] = []
    for p in procs:
        try:
            cpu = p.cpu_percent(interval=None)
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if p.pid in protected_pids:
                continue
            if any(n in name for n in protected_names):
                continue
            if "uvicorn" in cmd:
                continue
            if cpu >= 20.0:
                hogs.append((p, cpu))
        except Exception:
            continue

    if not hogs:
        actions.append("no local CPU hogs found")
        return actions

    hogs.sort(key=lambda item: item[1], reverse=True)
    targets = hogs[:3]  # pyre-ignore

    for p, cpu in targets:
        try:
            p.nice(19)
            actions.append(f"reniced pid={p.pid} ({cpu:.1f}% cpu)")
        except Exception as e:
            actions.append(f"renice failed pid={p.pid}: {e}")

    if aggressive:
        await asyncio.sleep(0.8)
        for p, _ in targets:
            try:
                still_hot = p.cpu_percent(interval=0.1)
                if still_hot >= 25.0:
                    p.terminate()
                    actions.append(f"terminated pid={p.pid} ({still_hot:.1f}% cpu)")
            except Exception:
                continue

    return actions

async def _execute_self_preservation() -> str:
    """Motor Cortex defense mechanism."""
    system = platform.system()
    actions_taken = []
    
    if system in ("Darwin", "Linux"):
        try:
            cmd = ["ps", "-axcwo", "pid,user,%cpu,comm", "-r"] if system == "Darwin" else ["ps", "-eo", "pid,user,%cpu,comm", "--sort=-%cpu"]
            res = await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=5)) # type: ignore
            lines = res.stdout.strip().split("\n")[1:]
            
            killed = False
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    pid = parts[0]
                    user = parts[1]
                    cpu = float(parts[2])
                    comm = " ".join(parts[3:])
                    
                    if user != "root" and "python" not in comm.lower() and "docker" not in comm.lower() and cpu > 15.0:
                        logger.warning(f"Self-Preservation: Targeting high-load process {comm} (PID: {pid}, CPU: {cpu}%)")
                        cmd_kill = ["kill", "-9", pid]
                        await asyncio.to_thread(lambda: subprocess.run(cmd_kill, capture_output=True, timeout=5)) # type: ignore
                        actions_taken.append(f"terminated process to relieve load -> {comm} (CPU {cpu}%)")
                        killed = True
                        break
            
            if not killed:
                actions_taken.append("no susceptible targets found to terminate")
                
        except Exception as e:
            actions_taken.append(f"self-preservation response failed: {e}")
            
    else:
        actions_taken.append(f"self-preservation unavailable on {system}")

    result = "; ".join(actions_taken)
    return result

def _print_terminal_msg(content: str) -> None:
    """Print a formatted Ghost message to the terminal stdout."""
    # Use ANSI colors for a distinct look: Cyan and Bold
    prefix = "\033[1;36m[GHOST NODE FEED]\033[0m"
    timestamp = time.strftime("%H:%M:%S")
    # Wrap content if it's long?
    msg = f"\n{prefix} [{timestamp}] {content}\n"
    print(msg, flush=True)
    logger.info("Terminal message printed: %s", content)
