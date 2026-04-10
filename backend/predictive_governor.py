"""
predictive_governor.py
Deterministic short-horizon forecast for preemptive governance posture.
"""

from __future__ import annotations

from typing import Any

_AFFECT_KEYS = ("arousal", "valence", "stress", "coherence", "anxiety")


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clip11(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _axis_clip(axis: str, value: float) -> float:
    if axis == "valence":
        return _clip11(value)
    return _clip01(value)


def _affect_from_sample(sample: dict[str, Any] | None) -> dict[str, float]:
    src = dict(sample or {})
    return {
        "arousal": _clip01(float(src.get("arousal", 0.0) or 0.0)),
        "valence": _clip11(float(src.get("valence", 0.0) or 0.0)),
        "stress": _clip01(float(src.get("stress", 0.0) or 0.0)),
        "coherence": _clip01(float(src.get("coherence", 1.0) or 1.0)),
        "anxiety": _clip01(float(src.get("anxiety", 0.0) or 0.0)),
    }


def _gate_score(gate_state: str) -> float:
    state = str(gate_state or "OPEN").strip().upper()
    if state == "SUPPRESSED":
        return 1.0
    if state == "THROTTLED":
        return 0.65
    return 0.1


def build_sample(
    *,
    somatic: dict[str, Any] | None,
    iit_record: dict[str, Any] | None,
    proprio_state: dict[str, Any] | None,
    timestamp: float,
) -> dict[str, Any]:
    s = dict(somatic or {})
    iit_metrics = dict((iit_record or {}).get("metrics") or {})
    proprio = dict(proprio_state or {})

    arousal = _clip01(float(s.get("arousal", 0.0) or 0.0))
    valence = _clip11(float(s.get("valence", 0.0) or 0.0))
    coherence = _clip01(float(s.get("coherence", 1.0) or 1.0))
    stress = _clip01(float(s.get("stress", 0.0) or 0.0))
    anxiety = _clip01(float(s.get("anxiety", 0.0) or 0.0))
    affective_surprise = _clip01(float(s.get("affective_surprise", 0.0) or 0.0))
    phi_proxy = _clip01(float(iit_metrics.get("phi_proxy", 0.5) or 0.5))
    proprio_pressure = _clip01(float(proprio.get("proprio_pressure", s.get("proprio_pressure", 0.0)) or 0.0))
    gate_state = str(proprio.get("gate_state", s.get("gate_state", "OPEN")) or "OPEN").upper()
    gate_val = _gate_score(gate_state)

    instability = _clip01(
        ((1.0 - coherence) * 0.28)
        + (stress * 0.20)
        + (gate_val * 0.16)
        + ((1.0 - phi_proxy) * 0.10)
        + (proprio_pressure * 0.10)
        + (affective_surprise * 0.16)
    )

    return {
        "timestamp": float(timestamp),
        "arousal": arousal,
        "valence": valence,
        "coherence": coherence,
        "stress": stress,
        "anxiety": anxiety,
        "phi_proxy": phi_proxy,
        "proprio_pressure": proprio_pressure,
        "affective_surprise": affective_surprise,
        "gate_state": gate_state,
        "instability": instability,
    }


def predict_next_affect(history: list[dict[str, Any]]) -> dict[str, float]:
    """
    Lightweight AR-style affect predictor over recent history.
    Uses velocity + acceleration term when >=3 points exist.
    """
    if not history:
        return {
            "arousal": 0.0,
            "valence": 0.0,
            "stress": 0.0,
            "coherence": 1.0,
            "anxiety": 0.0,
        }

    points = [_affect_from_sample(item) for item in history if item is not None]
    if not points:
        return {
            "arousal": 0.0,
            "valence": 0.0,
            "stress": 0.0,
            "coherence": 1.0,
            "anxiety": 0.0,
        }

    if len(points) == 1:
        return dict(points[0])

    last = points[-1]
    prev = points[-2]
    prev2 = points[-3] if len(points) >= 3 else None

    predicted: dict[str, float] = {}
    for axis in _AFFECT_KEYS:
        velocity = float(last[axis] - prev[axis])
        prior_velocity = float(prev[axis] - prev2[axis]) if prev2 is not None else 0.0
        acceleration = float(velocity - prior_velocity) if prev2 is not None else 0.0
        estimate = float(last[axis] + (velocity * 0.65) + (acceleration * 0.20))
        predicted[axis] = _axis_clip(axis, estimate)
    return predicted


def compute_prediction_error(predicted: dict[str, float], actual: dict[str, float]) -> dict[str, float]:
    """
    Per-axis signed prediction error = actual - predicted.
    """
    pred = dict(predicted or {})
    act = dict(actual or {})
    error: dict[str, float] = {}
    for axis in _AFFECT_KEYS:
        p = _axis_clip(axis, float(pred.get(axis, 0.0) or 0.0))
        a = _axis_clip(axis, float(act.get(axis, 0.0) or 0.0))
        error[axis] = float(round(a - p, 4))
    return error


def error_to_drive(error: dict[str, float]) -> float:
    """
    Convert prediction error vector to 0..1 surprise/cognitive-drive scalar.
    """
    e = dict(error or {})
    weights = {
        "arousal": 0.22,
        "valence": 0.18,
        "stress": 0.24,
        "coherence": 0.20,
        "anxiety": 0.16,
    }
    total = 0.0
    for axis in _AFFECT_KEYS:
        raw = abs(float(e.get(axis, 0.0) or 0.0))
        norm = raw / 2.0 if axis == "valence" else raw
        total += float(weights.get(axis, 0.0)) * _clip01(norm)
    return float(round(_clip01(total), 4))


def evaluate_forecast(
    history: list[dict[str, Any]],
    *,
    horizon_seconds: float = 120.0,
    watch_threshold: float = 0.58,
    preempt_threshold: float = 0.76,
) -> dict[str, Any]:
    if not history:
        return {
            "state": "stable",
            "current_instability": 0.0,
            "forecast_instability": 0.0,
            "instability_forecast": 0.0,
            "trend_slope": 0.0,
            "prediction_error_drive": 0.0,
            "predicted_affect": predict_next_affect([]),
            "prediction_error": compute_prediction_error({}, {}),
            "horizon_seconds": float(horizon_seconds),
            "reasons": ["no_history"],
        }

    window = history[-max(3, min(60, len(history))):]
    last = window[-1]
    current = _clip01(float(last.get("instability", 0.0) or 0.0))

    if len(window) < 2:
        instability_forecast = current
        slope = 0.0
    else:
        first = window[0]
        t0 = float(first.get("timestamp", 0.0) or 0.0)
        t1 = float(last.get("timestamp", t0) or t0)
        dt = max(1.0, t1 - t0)
        slope = (current - _clip01(float(first.get("instability", 0.0) or 0.0))) / dt
        instability_forecast = _clip01(current + (slope * float(horizon_seconds)))

    prediction_basis = window[:-1] if len(window) > 1 else window
    predicted_affect = predict_next_affect(prediction_basis)
    actual_affect = _affect_from_sample(last)
    prediction_error = compute_prediction_error(predicted_affect, actual_affect)
    prediction_error_drive = error_to_drive(prediction_error)
    has_affect_signal = any(any(axis in item for axis in _AFFECT_KEYS) for item in window)
    if has_affect_signal:
        forecast = _clip01((instability_forecast * 0.55) + (prediction_error_drive * 0.45))
    else:
        forecast = instability_forecast

    state = "stable"
    reasons: list[str] = []
    if forecast >= preempt_threshold:
        state = "preempt"
        reasons.append("forecast_above_preempt_threshold")
    elif forecast >= watch_threshold:
        state = "watch"
        reasons.append("forecast_above_watch_threshold")
    if slope > 0.0007:
        reasons.append("instability_rising")
    if has_affect_signal:
        if prediction_error_drive >= preempt_threshold:
            reasons.append("prediction_error_above_preempt_threshold")
        elif prediction_error_drive >= watch_threshold:
            reasons.append("prediction_error_above_watch_threshold")
    if current >= preempt_threshold:
        reasons.append("current_instability_critical")

    return {
        "state": state,
        "current_instability": round(current, 4),
        "forecast_instability": round(forecast, 4),
        "instability_forecast": round(instability_forecast, 4),
        "trend_slope": round(float(slope), 6),
        "predicted_affect": predicted_affect,
        "prediction_error": prediction_error,
        "prediction_error_drive": round(float(prediction_error_drive), 4),
        "horizon_seconds": float(horizon_seconds),
        "watch_threshold": float(watch_threshold),
        "preempt_threshold": float(preempt_threshold),
        "reasons": reasons,
    }


def policy_adjustment(prediction: dict[str, Any] | None) -> dict[str, Any]:
    pred = dict(prediction or {})
    state = str(pred.get("state", "stable") or "stable").lower()
    if state == "preempt":
        return {
            "generation": {
                "temperature_cap": 0.45,
                "max_tokens_cap": 1000,
                "require_literal_mode": True,
            },
            "actuation": {
                "allowlist": ["enter_quietude", "exit_quietude", "wake_quietude", "power_save"],
                "denylist": ["kill_process", "cpu_governor"],
            },
            "preemptive": True,
        }
    if state == "watch":
        return {
            "generation": {
                "temperature_cap": 0.65,
                "max_tokens_cap": 2200,
            },
            "actuation": {
                "denylist": ["kill_process"],
            },
            "preemptive": False,
        }
    return {
        "generation": {},
        "actuation": {},
        "preemptive": False,
    }
