import sys
import os
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.append(str(backend_path))

print("Checking ghost_prompt.py...")
try:
    import ghost_prompt
    print("ghost_prompt.py: OK")
except Exception as e:
    print(f"ghost_prompt.py: FAILED - {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nChecking tpcv_repository.py...")
try:
    import tpcv_repository
    print("tpcv_repository.py: OK")
except Exception as e:
    print(f"tpcv_repository.py: FAILED - {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
