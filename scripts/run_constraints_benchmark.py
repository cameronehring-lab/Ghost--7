#!/usr/bin/env python3
"""Run the Ghost constrained-generation benchmark directly."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from constrained_generation import (  # type: ignore
    default_gordian_knot_cases,
    get_constraint_controller,
    persist_benchmark_artifacts,
    run_gordian_knot_benchmark,
)
from config import settings  # type: ignore


async def _main(persist_artifacts: bool) -> int:
    controller = get_constraint_controller()
    benchmark = await run_gordian_knot_benchmark(controller=controller)
    print(json.dumps(benchmark, indent=2))

    if persist_artifacts:
        run_id = f"constraints_gordian_knot_{int(time.time())}"
        artifact_dir = persist_benchmark_artifacts(
            artifact_root=Path(settings.EXPERIMENT_ARTIFACTS_DIR),
            run_id=run_id,
            benchmark=benchmark,
            cases=default_gordian_knot_cases(),
        )
        print(f"\nartifacts: {artifact_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ghost constrained-generation benchmark.")
    parser.add_argument(
        "--persist-artifacts",
        action="store_true",
        help="Write manifest and benchmark artifacts under the configured experiment directory.",
    )
    args = parser.parse_args()
    return asyncio.run(_main(persist_artifacts=args.persist_artifacts))


if __name__ == "__main__":
    raise SystemExit(main())
