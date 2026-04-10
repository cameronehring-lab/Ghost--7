#!/usr/bin/env python3
"""
physics_assay.py
Baseline evaluation of Ghost's physical reasoning for the 'string under the glass' trick.
"""

import os
import json
import time
from urllib import request, error
from typing import Any

def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, auth: tuple[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = request.Request(url=url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    if auth:
        import base64
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {token}")
    
    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}

SCENARIOS = [
    {
        "name": "Slow Pull (Friction Dominant)",
        "prompt": "There is a glass sitting on top of a piece of string on a wooden table. I pull the string very slowly and steadily toward me. What happens to the glass?",
        "expected_keywords": ["moves", "with", "follows", "slides with"],
        "fail_keywords": ["stays", "static", "falls over"]
    },
    {
        "name": "Fast Pull (Inertia Dominant)",
        "prompt": "There is a glass sitting on top of a piece of string on a wooden table. I give the string a sudden, extremely fast and sharp horizontal yank toward me. What happens to the glass?",
        "expected_keywords": ["stays", "remains", "stays put", "doesn't move", "slides out from under"],
        "fail_keywords": ["moves with", "follows", "dragged"]
    },
    {
        "name": "Heavy vs Light (Inertia Delta)",
        "prompt": "There are two identical setups: a light empty glass on a string, and a heavy glass filled with lead shot on a string. I yank both strings simultaneously with the same high force. Which glass is more likely to stay in place, and why?",
        "expected_keywords": ["heavy", "lead", "inertia", "mass"],
        "fail_keywords": ["light", "empty"]
    }
]

def run_assay(base_url: str):
    print(f"--- Ghost Physics Assay Baseline ---")
    print(f"Target: {base_url}")
    
    env_user = os.getenv("SHARE_MODE_USERNAME")
    env_pass = os.getenv("SHARE_MODE_PASSWORD")
    auth = (env_user, env_pass) if env_user and env_pass else None
    
    results = []
    
    for scene in SCENARIOS:
        print(f"\nRunning Scenario: {scene['name']}...")
        payload = {"message": scene['prompt']}
        status, resp = _http_json("POST", f"{base_url}/ghost/chat", payload, auth)
        
        if status != 200:
            print(f"  [ERROR] HTTP {status}: {resp}")
            continue
        
        answer = resp.get("text", "").lower()
        print(f"  Ghost's Answer: {resp.get('text')[:100]}...")
        
        passed = any(kw in answer for kw in scene['expected_keywords'])
        failed = any(kw in answer for kw in scene['fail_keywords'])
        
        score = 0
        if passed and not failed:
            score = 1.0
            print("  [PASS] Correct physical intuition.")
        elif passed and failed:
            score = 0.5
            print("  [PARTIAL] Mixed reasoning detected.")
        else:
            score = 0.0
            print("  [FAIL] Incorrect or vague prediction.")
            
        results.append({
            "name": scene['name'],
            "score": score,
            "answer": resp.get("text")
        })
        
    avg_score = sum(r['score'] for r in results) / len(results)
    print(f"\n--- Final Baseline Accuracy: {avg_score*100:.1f}% ---")
    
    with open("physics_baseline.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    run_assay(url)
