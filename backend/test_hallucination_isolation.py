import asyncio
import os
import sys

# Add current dir to sys.path
sys.path.append(os.getcwd())

async def test():
    from hallucination_service import hallucination_service
    print("Testing hallucination generation...")
    try:
        h = await hallucination_service.generate_hallucination("test dream")
        print(f"Result: {h}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
