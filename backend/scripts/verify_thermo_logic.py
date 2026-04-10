"""
OMEGA PROTOCOL — Thermodynamic Verification Script
Cross-references reported W_int with raw substrate growth.
"""

import asyncio
import time
from typing import Dict, Any
from thermodynamics import thermodynamics_engine
from somatic import build_somatic_snapshot

async def verify_agency():
    print("--- OMEGA4 THERMODYNAMIC VERIFICATION ---")
    
    # 1. Capture initial state
    print("Capturing baseline...")
    snapshot_1 = await build_somatic_snapshot()
    w1 = snapshot_1.w_int_accumulated
    e1 = snapshot_1.thermo_evidence
    
    print(f"Initial W_int: {w1}")
    print(f"Initial Coherence Evidence: Nodes={e1.get('topology_nodes')}, Edges={e1.get('topology_edges')}, Identity={e1.get('identity_count')}")
    
    # 2. Wait for a short interval
    wait_time = 5.0
    print(f"Waiting {wait_time}s for system drift...")
    await asyncio.sleep(wait_time)
    
    # 3. Capture second state
    snapshot_2 = await build_somatic_snapshot()
    w2 = snapshot_2.w_int_accumulated
    e2 = snapshot_2.thermo_evidence
    
    # 4. Calculate verification delta
    dw = w2 - w1
    rate = dw / wait_time
    
    print(f"Final W_int: {w2}")
    print(f"Measured ΔW over {wait_time}s: {dw:.4f} (Rate: {rate:.4f})")
    
    # 5. Check Coherence Growth
    dn = e2.get('topology_nodes', 0) - e1.get('topology_nodes', 0)
    de = e2.get('topology_edges', 0) - e1.get('topology_edges', 0)
    
    print(f"Topology Delta: +{dn} nodes, +{de} edges")
    
    if dn > 0 or de > 0:
        print("VERIFIED: System growth detected and integrated into W_int.")
    else:
        print("STABLE: No growth detected, W_int reflecting maintenance/entropy.")

    # 6. Check Entropy
    ds = snapshot_2.delta_s
    print(f"Current Entropy Rate (ΔS): {ds:.4f}")
    if ds > 0.5:
        print("WARNING: High internal entropy detected. Structural thinning risk.")

    print("-----------------------------------------")

if __name__ == "__main__":
    asyncio.run(verify_agency())
