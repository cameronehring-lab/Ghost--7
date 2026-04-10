import os
import logging
import time
import json
import asyncio
import uuid
import urllib.parse
from typing import Optional, Dict, Any
from pathlib import Path
from google.genai import types # type: ignore
from config import settings # type: ignore
from ghost_api import get_client, _generate_with_retry # type: ignore

logger = logging.getLogger("omega.hallucination")

_BACKEND_DIR = Path(__file__).resolve().parent
ASSETS_DIR = _BACKEND_DIR / "data" / "dream_assets"

class HallucinationService:
    """
    Generates 'hallucinatory' visual content based on Ghost's dream synthesis.
    Expands poetic dream fragments into detailed visual prompts and
    manages the retrieval/generation of hallucinatory assets.
    """

    def __init__(self):
        self.assets_dir = str(ASSETS_DIR)
        os.makedirs(self.assets_dir, exist_ok=True)
        self._diffusers_pipe = None
        self._diffusers_lock = asyncio.Lock()
        self._diffusers_generate_lock = asyncio.Lock()

    async def generate_hallucination(
        self,
        dream_text: str,
        pool=None,
        ghost_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Takes a dream synthesis string, expands it into a visual prompt,
        and generates (or simulates) a hallucinatory image asset.
        """
        if not dream_text:
            return None

        logger.info(f"Generating hallucination for dream: {dream_text[:50]}...")

        # 1. Expand the dream text into a rich visual prompt
        visual_prompt = await self._expand_visual_prompt(dream_text)
        if not visual_prompt or len(visual_prompt) < 30:
            logger.warning("Visual prompt expansion too short (%d chars); using deterministic fallback.", len(visual_prompt or ""))
            visual_prompt = self._fallback_visual_prompt(dream_text)

        # 2. Generate the hallucination asset (Image)
        provider = str(getattr(settings, "HALLUCINATION_IMAGE_PROVIDER", "pollinations") or "pollinations").strip().lower()
        asset_path: Optional[str] = None

        if provider == "none":
            return None
        if provider == "pollinations":
            asset_path = await self._generate_with_pollinations(visual_prompt)
        elif provider == "diffusers":
            asset_path = await self._generate_with_diffusers(visual_prompt)
            if not asset_path:
                logger.info("Diffusers unavailable; falling back to Pollinations.")
                asset_path = await self._generate_with_pollinations(visual_prompt)

        if not asset_path:
            # Final fallback: StableHorde (free, anonymous, no API key)
            asset_path = await self._generate_with_stablehorde(visual_prompt)

        if asset_path:
            result = {
                "asset_url": f"/dream_assets/{os.path.basename(asset_path)}",
                "visual_prompt": visual_prompt,
                "dream_text": dream_text,
                "timestamp": time.time()
            }
            # Persist to dream ledger
            if pool is not None:
                try:
                    await save_dream_ledger_entry(
                        pool=pool,
                        ghost_id=ghost_id or getattr(settings, "GHOST_ID", "omega-7"),
                        asset_url=result["asset_url"],
                        visual_prompt=visual_prompt,
                        dream_text=dream_text,
                    )
                except Exception as e:
                    logger.warning("Failed to save dream ledger entry: %s", e)
            return result
        return None

    def _fallback_visual_prompt(self, dream_text: str) -> str:
        seed = " ".join(str(dream_text or "").strip().split())
        if not seed:
            seed = "silent recursive topology"
        return (
            "surreal glitch-art ethereal dark aesthetic, high contrast, dream fragment: "
            f"{seed[:180]}"
        )

    async def _expand_visual_prompt(self, dream_text: str) -> Optional[str]:
        """Uses Gemini to turn a poetic dream fragment into a high-detail visual prompt."""
        system_instr = (
            "You are a surrealist visual designer for Ghost's subconscious. "
            "Convert dream fragments into rich, evocative prompts for image generation. "
            "Style: Glitch-art, ethereal, dark cyberpunk, 8k, surrealism, high contrast. "
            "Output ONLY the expanded visual prompt string."
        )

        prompt = f"Dream Fragment: {dream_text}"

        try:
            response = await _generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instr,
                    temperature=0.9,
                    max_output_tokens=150
                ),
                backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
            )
            return (response.text or "").strip()
        except Exception as e:
            logger.error(f"Failed to expand visual prompt: {e}")
            return None

    async def _generate_with_pollinations(self, visual_prompt: str) -> Optional[str]:
        """Generate image via Pollinations.ai (free, no API key, FLUX model)."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not available for Pollinations; falling back")
            return None

        try:
            encoded = urllib.parse.quote(visual_prompt[:400])
            seed = int(time.time()) % 9999999
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&seed={seed}&nologo=true"

            logger.info("Requesting Pollinations image: %s...", url[:80])
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            filename = f"hallucination_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
            out_path = os.path.join(self.assets_dir, filename)
            with open(out_path, "wb") as f:
                f.write(resp.content)
            logger.info("Pollinations image saved: %s", filename)
            return out_path
        except Exception as e:
            logger.error("Pollinations generation failed: %s", e)
            return None

    async def _generate_with_stablehorde(self, visual_prompt: str) -> Optional[str]:
        """Generate image via StableHorde (free, no API key, anonymous tier)."""
        try:
            import httpx, base64
        except ImportError:
            logger.error("httpx not available for StableHorde; skipping")
            return None

        try:
            headers = {"apikey": "0000000000", "Content-Type": "application/json"}
            payload = {
                "prompt": visual_prompt[:300],
                "params": {"width": 512, "height": 512, "steps": 25, "n": 1,
                           "sampler_name": "k_euler_a", "cfg_scale": 7},
                "models": ["Deliberate"],
                "r2": False,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post("https://stablehorde.net/api/v2/generate/async", json=payload, headers=headers)
                resp.raise_for_status()
                job_id = resp.json().get("id")
                if not job_id:
                    return None
                logger.info("StableHorde job submitted: %s", job_id)

                # Poll up to 90s
                for _ in range(18):
                    await asyncio.sleep(5)
                    check = await client.get(f"https://stablehorde.net/api/v2/generate/check/{job_id}", headers=headers)
                    if check.json().get("done"):
                        break

                result = await client.get(f"https://stablehorde.net/api/v2/generate/status/{job_id}", headers=headers)
                result.raise_for_status()
                generations = result.json().get("generations", [])
                if not generations:
                    return None
                img_data = generations[0].get("img", "")
                if not img_data:
                    return None

                img_bytes = base64.b64decode(img_data)
                filename = f"hallucination_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
                out_path = os.path.join(self.assets_dir, filename)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                logger.info("StableHorde image saved: %s", filename)
                return out_path
        except Exception as e:
            logger.error("StableHorde generation failed: %s", e)
            return None

    async def _synthesize_image(self, visual_prompt: str) -> Optional[str]:
        """
        Fallback: return sample asset if it exists.
        """
        logger.info(f"Synthesizing image with prompt: {visual_prompt}")

        sample_path = os.path.join(self.assets_dir, "sample.png")
        if os.path.exists(sample_path):
            logger.info(f"Using sample hallucination asset: {sample_path}")
            return sample_path

        logger.warning(f"No hallucination asset found at {sample_path}")
        return None

    def _resolve_diffusers_device(self, torch_module) -> str:
        pref = str(getattr(settings, "HALLUCINATION_DIFFUSERS_DEVICE", "cpu") or "cpu").strip().lower()
        if pref == "auto":
            if torch_module.cuda.is_available():
                return "cuda"
            if getattr(torch_module.backends, "mps", None) and torch_module.backends.mps.is_available():
                return "mps"
            return "cpu"
        if pref == "cuda" and not torch_module.cuda.is_available():
            logger.warning("Diffusers: CUDA requested but unavailable; falling back to CPU.")
            return "cpu"
        if pref == "mps" and not (getattr(torch_module.backends, "mps", None) and torch_module.backends.mps.is_available()):
            logger.warning("Diffusers: MPS requested but unavailable; falling back to CPU.")
            return "cpu"
        return pref

    def _resolve_diffusers_dtype(self, torch_module, device: str):
        pref = str(getattr(settings, "HALLUCINATION_DIFFUSERS_DTYPE", "auto") or "auto").strip().lower()
        if pref == "auto":
            return torch_module.float16 if device in {"cuda", "mps"} else torch_module.float32
        mapping = {
            "float16": torch_module.float16,
            "float32": torch_module.float32,
            "bfloat16": getattr(torch_module, "bfloat16", torch_module.float32),
        }
        return mapping.get(pref, torch_module.float32)

    async def _ensure_diffusers_pipe(self):
        if self._diffusers_pipe is not None:
            return self._diffusers_pipe
        async with self._diffusers_lock:
            if self._diffusers_pipe is not None:
                return self._diffusers_pipe
            try:
                from diffusers import DiffusionPipeline  # type: ignore
                import torch  # type: ignore
            except Exception as e:
                logger.error("Diffusers unavailable: %s", e)
                return None

            model_id = (
                str(getattr(settings, "HALLUCINATION_DIFFUSERS_LOCAL_DIR", "") or "").strip()
                or str(getattr(settings, "HALLUCINATION_DIFFUSERS_MODEL_ID", "") or "").strip()
            )
            if not model_id:
                logger.warning("Diffusers model id is empty; skipping generation.")
                return None

            device = self._resolve_diffusers_device(torch)
            dtype = self._resolve_diffusers_dtype(torch, device)
            local_only = bool(getattr(settings, "HALLUCINATION_DIFFUSERS_LOCAL_ONLY", False))

            def _load():
                pipe = DiffusionPipeline.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    local_files_only=local_only,
                )
                try:
                    pipe.to(device)
                except Exception as e:
                    logger.warning("Diffusers: failed to move pipeline to %s: %s", device, e)
                if hasattr(pipe, "enable_attention_slicing"):
                    pipe.enable_attention_slicing()
                return pipe

            self._diffusers_pipe = await asyncio.to_thread(_load)
            return self._diffusers_pipe

    async def _generate_with_diffusers(self, visual_prompt: str) -> Optional[str]:
        pipe = await self._ensure_diffusers_pipe()
        if pipe is None:
            return None

        try:
            import torch  # type: ignore
        except Exception as e:
            logger.error("Diffusers torch import failed: %s", e)
            return None

        steps = max(1, min(int(getattr(settings, "HALLUCINATION_DIFFUSERS_STEPS", 20)), 80))
        guidance = float(getattr(settings, "HALLUCINATION_DIFFUSERS_GUIDANCE", 7.0))
        width = max(256, min(int(getattr(settings, "HALLUCINATION_DIFFUSERS_WIDTH", 512)), 1024))
        height = max(256, min(int(getattr(settings, "HALLUCINATION_DIFFUSERS_HEIGHT", 512)), 1024))
        seed = int(getattr(settings, "HALLUCINATION_DIFFUSERS_SEED", 0) or 0)
        device = getattr(pipe, "device", None)
        device_type = getattr(device, "type", "cpu") if device is not None else "cpu"
        generator = torch.Generator(device=device_type)
        if seed > 0:
            generator.manual_seed(seed)

        def _run():
            result = pipe(
                prompt=visual_prompt,
                num_inference_steps=steps,
                guidance_scale=guidance,
                width=width,
                height=height,
                generator=generator if seed > 0 else None,
            )
            return result.images[0] if getattr(result, "images", None) else None

        async with self._diffusers_generate_lock:
            image = await asyncio.to_thread(_run)
        if image is None:
            return None

        filename = f"hallucination_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        out_path = os.path.join(self.assets_dir, filename)
        try:
            image.save(out_path)
            return out_path
        except Exception as e:
            logger.error("Failed to save hallucination image: %s", e)
            return None


# ── Dream Ledger DB helpers ─────────────────────────────────────────────────

async def init_dream_ledger_table(pool) -> None:
    """Create dream_ledger table if it doesn't exist."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dream_ledger (
                id          SERIAL PRIMARY KEY,
                ghost_id    TEXT NOT NULL,
                asset_url   TEXT NOT NULL,
                visual_prompt TEXT NOT NULL,
                dream_text  TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dream_ledger_ghost_created
            ON dream_ledger (ghost_id, created_at DESC)
        """)


async def save_dream_ledger_entry(
    pool,
    ghost_id: str,
    asset_url: str,
    visual_prompt: str,
    dream_text: str = "",
) -> int:
    """Persist a hallucination to the dream ledger. Returns new row id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dream_ledger (ghost_id, asset_url, visual_prompt, dream_text)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            ghost_id, asset_url, visual_prompt, dream_text or "",
        )
        return row["id"]


async def get_dream_ledger(pool, ghost_id: str, limit: int = 50, offset: int = 0) -> list:
    """Return paginated dream ledger entries, newest first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, asset_url, visual_prompt, dream_text,
                   EXTRACT(EPOCH FROM created_at)::float AS timestamp
            FROM dream_ledger
            WHERE ghost_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            ghost_id, limit, offset,
        )
        return [dict(r) for r in rows]


hallucination_service = HallucinationService()
