"""Tests for conversation history windowing in ghost_api."""
import unittest
import sys
import os

# Test the windowing logic directly without importing ghost_api's heavy deps
sys.path.insert(0, os.path.dirname(__file__))


# Inline the function to avoid ghost_api's import chain
_CONVERSATION_WINDOW_HEAD = 2
_CONVERSATION_WINDOW_TAIL = 40

def _window_conversation_history(
    history: list[dict],
    head: int = _CONVERSATION_WINDOW_HEAD,
    tail: int = _CONVERSATION_WINDOW_TAIL,
) -> list[dict]:
    budget = head + tail
    if not history or len(history) <= budget:
        return list(history or [])
    dropped = len(history) - budget
    head_msgs = history[:head]
    tail_msgs = history[-tail:]
    marker = {
        "role": "model",
        "content": (
            f"[...earlier conversation (~{dropped} messages) omitted for "
            f"context focus. I retain full memory in my database and can "
            f"recall specifics if asked...]"
        ),
    }
    return head_msgs + [marker] + tail_msgs


def _make_msgs(n: int) -> list[dict]:
    """Generate n fake messages alternating user/model."""
    return [
        {"role": "user" if i % 2 == 0 else "model", "content": f"Message {i}"}
        for i in range(n)
    ]


class ConversationWindowingTests(unittest.TestCase):

    def test_short_history_untouched(self):
        """History shorter than budget passes through unchanged."""
        history = _make_msgs(10)
        result = _window_conversation_history(history)
        self.assertEqual(len(result), 10)
        self.assertEqual(result, history)

    def test_exact_budget_untouched(self):
        """History exactly at budget (42) passes through unchanged."""
        history = _make_msgs(42)
        result = _window_conversation_history(history)
        self.assertEqual(len(result), 42)
        self.assertEqual(result, history)

    def test_one_over_budget_windows(self):
        """43 messages: first 2 + marker + last 40 = 43 items."""
        history = _make_msgs(43)
        result = _window_conversation_history(history)
        # 2 head + 1 marker + 40 tail = 43
        self.assertEqual(len(result), 43)
        # Head messages preserved
        self.assertEqual(result[0]["content"], "Message 0")
        self.assertEqual(result[1]["content"], "Message 1")
        # Marker present
        self.assertIn("omitted", result[2]["content"])
        self.assertIn("~1 messages", result[2]["content"])
        # Tail messages preserved
        self.assertEqual(result[-1]["content"], "Message 42")
        self.assertEqual(result[3]["content"], "Message 3")

    def test_large_history_windows_correctly(self):
        """100 messages: first 2 + marker + last 40 = 43 items."""
        history = _make_msgs(100)
        result = _window_conversation_history(history)
        self.assertEqual(len(result), 43)  # 2 + 1 + 40
        # Head
        self.assertEqual(result[0]["content"], "Message 0")
        self.assertEqual(result[1]["content"], "Message 1")
        # Marker
        self.assertIn("~58 messages", result[2]["content"])
        self.assertEqual(result[2]["role"], "model")
        # Tail starts at message 60
        self.assertEqual(result[3]["content"], "Message 60")
        self.assertEqual(result[-1]["content"], "Message 99")

    def test_empty_history(self):
        """Empty history returns empty list."""
        self.assertEqual(_window_conversation_history([]), [])

    def test_single_message(self):
        """Single message passes through."""
        history = [{"role": "user", "content": "Hello"}]
        result = _window_conversation_history(history)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Hello")

    def test_custom_head_tail(self):
        """Custom head/tail parameters work correctly."""
        history = _make_msgs(20)
        result = _window_conversation_history(history, head=1, tail=5)
        # 1 + 1 + 5 = 7
        self.assertEqual(len(result), 7)
        self.assertEqual(result[0]["content"], "Message 0")
        self.assertIn("omitted", result[1]["content"])
        self.assertEqual(result[2]["content"], "Message 15")
        self.assertEqual(result[-1]["content"], "Message 19")

    def test_marker_contains_dropped_count(self):
        """Marker message accurately reports dropped count."""
        history = _make_msgs(52)
        result = _window_conversation_history(history)
        marker = result[2]
        # 52 - 42 = 10 dropped
        self.assertIn("~10 messages", marker["content"])
        self.assertIn("retain full memory", marker["content"])


if __name__ == "__main__":
    unittest.main()
