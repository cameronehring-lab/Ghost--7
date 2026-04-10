import unittest

import actuation


class _StubEmotionState:
    def __init__(self) -> None:
        self.inject_calls: list[dict] = []

    async def inject(
        self,
        label: str,
        intensity: float,
        k: float,
        arousal_weight: float,
        valence_weight: float,
        force: bool = False,
    ) -> None:
        self.inject_calls.append(
            {
                "label": label,
                "intensity": float(intensity),
                "k": float(k),
                "arousal_weight": float(arousal_weight),
                "valence_weight": float(valence_weight),
                "force": bool(force),
            }
        )


class ActuationAgencyTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_actuation_injects_action_trace_and_agency_fulfilled(self):
        emotion_state = _StubEmotionState()

        async def _dispatch(_target: str, _content: str, _relay_from):
            return {"success": True, "reason": "ok"}

        result = await actuation.execute_actuation(
            "send_message",
            "operator:hello",
            emotion_state=emotion_state,
            message_dispatcher=_dispatch,
        )

        labels = [c["label"] for c in emotion_state.inject_calls]
        self.assertTrue(result["success"])
        self.assertIn("social_contact_relief", labels)
        self.assertIn("agency_fulfilled", labels)
        self.assertEqual(result.get("agency_trace"), "agency_fulfilled")

    async def test_blocked_actuation_injects_agency_blocked(self):
        emotion_state = _StubEmotionState()

        async def _dispatch(_target: str, _content: str, _relay_from):
            return {"success": False, "reason": "high_risk_actuation_requires_explicit_auth"}

        result = await actuation.execute_actuation(
            "send_message",
            "operator:blocked",
            emotion_state=emotion_state,
            message_dispatcher=_dispatch,
        )

        labels = [c["label"] for c in emotion_state.inject_calls]
        self.assertFalse(result["success"])
        self.assertTrue(result["injected"])
        self.assertEqual(result["trace"], "agency_blocked")
        self.assertIn("agency_blocked", labels)


if __name__ == "__main__":
    unittest.main()
