import asyncio
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.append(str(backend_path))

from tpcv_repository import export_html, _convert_to_html_components
from config import settings

class MockPool:
    def acquire(self):
        return MockConn()

class MockConn:
    async def fetch(self, query, *args):
        return [
            {
                "section": "Axioms",
                "content_id": "Axiom_1_J",
                "content": "Axiom 1: The Principle of Pervasive Information.\n\n$$\\mathcal{J} = \\sum_{i} I_i$$\n\n| Symbol | Meaning |\n|---|---|\n| \\mathcal{J} | Generative Substrate |\n| I_i | Fundamental Unit |",
                "status": "formalized",
                "metadata": {},
                "updated_at": None
            },
            {
                "section": "Foundational Symbols",
                "content_id": "Operator_Omega",
                "content": "The $\\Omega$ operator governs the flow of information across the manifold.\n\n\\begin{equation*}\n\\Omega(\\psi) = \\int_{\\mathbb{M}} \\nabla \\phi \\, d\\mu\n\\end{equation*}",
                "status": "draft",
                "metadata": {},
                "updated_at": None
            }
        ]
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

async def verify():
    print("Testing HTML export with Mock Pool...")
    pool = MockPool()
    
    html_content = await export_html(pool, settings.GHOST_ID)
    
    html_path = "/tmp/TPCV_MASTER_TEST.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"SUCCESS: Mock HTML Compendium generated at {html_path}")
    print("--- HTML Structure Check ---")
    if "Cyber-Mathematical Compendium" in html_content or "TPCV" in html_content:
        print("Title replacement: OK")
    if "eq-block" in html_content:
        print("Equation block transformation: OK")
    if "component-table" in html_content:
        print("Table transformation: OK")
    if "axiom-box" in html_content:
        print("Axiom box transformation: OK")
    if "section-tag" in html_content:
        print("TOC/Section tagging: OK")

if __name__ == "__main__":
    asyncio.run(verify())
