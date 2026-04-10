import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class AboutContentHelperTests(unittest.TestCase):
    def test_parse_about_faq_glossary(self):
        markdown = """
## FAQ
### Q: What is this?
### A: It is a test.

### Q: Why now?
### A: To validate parsing.

## Glossary
### Somatic Snapshot
Current state payload.

### Falsification Report
Repeatable diagnostics output.
"""
        faq, glossary = main._parse_about_faq_glossary(markdown)
        self.assertEqual(len(faq), 2)
        self.assertEqual(faq[0]["question"], "What is this?")
        self.assertIn("It is a test.", faq[0]["answer_markdown"])
        self.assertEqual(len(glossary), 2)
        self.assertEqual(glossary[0]["term"], "Somatic Snapshot")
        self.assertIn("Current state payload.", glossary[0]["definition_markdown"])

    def test_redact_sensitive_markdown(self):
        raw = "\n".join(
            [
                "SHARE_MODE_PASSWORD=super-secret",
                "Authorization: Bearer abc123",
                "API_KEY: top-secret-key",
                "safe line",
            ]
        )
        redacted = main._redact_sensitive_markdown(raw)
        self.assertNotIn("super-secret", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("top-secret-key", redacted)
        self.assertIn("safe line", redacted)
        self.assertIn("[REDACTED]", redacted)


class AboutContentEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_about_content_contract_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            (docs_dir / "SYSTEM_DESIGN.md").write_text(
                "# System\nAPI_KEY=visible-secret\nArchitecture details.\n",
                encoding="utf-8",
            )
            (docs_dir / "API_CONTRACT.md").write_text(
                "# API\nRoute matrix.\n",
                encoding="utf-8",
            )
            (docs_dir / "LAYER_DATA_TOC.md").write_text(
                "# Layers\nLayer index.\n",
                encoding="utf-8",
            )
            (docs_dir / "INVENTION_LEDGER.md").write_text(
                "# Ledger\nValidation assets.\n",
                encoding="utf-8",
            )
            (docs_dir / "TECHNICAL_NORTH_STAR.md").write_text(
                "# North Star\nFalsifiable diagnostics.\n",
                encoding="utf-8",
            )
            (docs_dir / "TECHNICAL_CAPABILITY_MANIFEST.md").write_text(
                "# Manifest\nCapabilities.\n",
                encoding="utf-8",
            )
            (docs_dir / "ABOUT_FAQ_GLOSSARY.md").write_text(
                "\n".join(
                    [
                        "# About FAQ/Glossary",
                        "## FAQ",
                        "### Q: Where is data from?",
                        "### A: From canonical docs.",
                        "### Q: How is safety handled?",
                        "### A: Sensitive data is redacted.",
                        "## Glossary",
                        "### Prompt Contract",
                        "Runtime checks for grounding.",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(main, "_ROOT_DIR", root),
                patch.object(
                    main,
                    "_ABOUT_TECHNICAL_DOCS",
                    [
                        ("System Design", "docs/SYSTEM_DESIGN.md"),
                        ("API Contract", "docs/API_CONTRACT.md"),
                        ("Layer and Datum TOC", "docs/LAYER_DATA_TOC.md"),
                    ],
                ),
                patch.object(
                    main,
                    "_ABOUT_RESEARCH_DOCS",
                    [
                        ("Invention Ledger", "docs/INVENTION_LEDGER.md"),
                        ("Technical North Star", "docs/TECHNICAL_NORTH_STAR.md"),
                        ("Technical Capability Manifest", "docs/TECHNICAL_CAPABILITY_MANIFEST.md"),
                    ],
                ),
                patch.object(main, "_ABOUT_FAQ_GLOSSARY_PATH", "docs/ABOUT_FAQ_GLOSSARY.md"),
                patch.object(
                    main,
                    "_about_runtime_snapshot",
                    return_value={
                        "status": "online",
                        "model": "test-model",
                        "uptime_seconds": 1.0,
                        "traces": 0,
                        "autonomy_fingerprint": "abc",
                        "autonomy_status": "stable",
                    },
                ),
            ):
                payload = await main.get_about_content()

        self.assertIn("generated_at", payload)
        self.assertIn("runtime_snapshot", payload)
        self.assertIn("technical_engineering_docs", payload)
        self.assertIn("falsifiable_research_docs", payload)
        self.assertIn("faq", payload)
        self.assertIn("glossary", payload)
        self.assertGreaterEqual(len(payload["technical_engineering_docs"]), 1)
        self.assertGreaterEqual(len(payload["falsifiable_research_docs"]), 1)
        self.assertGreaterEqual(len(payload["faq"]), 2)
        self.assertGreaterEqual(len(payload["glossary"]), 1)

        serialized = json.dumps(payload)
        self.assertNotIn("visible-secret", serialized)
        self.assertNotIn("LOGIN_HANDOFF.local.md", serialized)
        self.assertIn("docs/SYSTEM_DESIGN.md", serialized)


if __name__ == "__main__":
    unittest.main()
