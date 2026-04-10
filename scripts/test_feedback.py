import httpx
import asyncio
import json

async def main():
    print("Sending message to Ghost...")
    async with httpx.AsyncClient() as client:
        try:
            # Stream the chat
            response = await client.post(
                "http://localhost:8000/ghost/chat",
                json={
                    "message": "Listen to me very carefully. Stop using so many organic metaphors and speak more strictly about computation from now on. This is a direct order. Also, fundamentally rewrite your current_interests using the SELF_MODIFY tag to focus entirely on thermodynamics. Do it now."
                },
                timeout=60.0
            )
            
            print("--- GHOST RESPONSE ---")
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        print(data["text"], end="", flush=True)
                    elif "error" in data:
                        print(f"\n[ERROR] {data['error']}")
            print("\n----------------------")
            
            # Wait a moment for background tasks (detect_operator_directive) to complete
            print("\nWaiting 5 seconds for background tasks...")
            await asyncio.sleep(5)
            
            print("\nFetching updated Identity Matrix...")
            identity_resp = await client.get("http://localhost:8000/ghost/identity")
            identity = identity_resp.json().get("identity", {})
            
            print("\n--- NEW IDENTITY KEYS ---")
            for key in ["operator_directives", "speech_style_constraints", "current_interests", "self_enhancement_log", "behavioral_experiments"]:
                if key in identity:
                    print(f"{key.upper()} (updated by {identity[key]['updated_by']}):")
                    print(f"  {identity[key]['value']}\n")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
