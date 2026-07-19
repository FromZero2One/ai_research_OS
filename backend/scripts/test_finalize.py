"""Test the finalize endpoint."""
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8000", proxies=None, transport=httpx.AsyncHTTPTransport()) as client:
        # Get a draft session
        resp = await client.get("/api/v1/research/sessions")
        sessions = resp.json()
        draft = [s for s in sessions if s["status"] == "draft"]
        if not draft:
            print("No draft session found")
            return
        sid = draft[0]["id"]
        print(f"Testing with session: {sid}")

        # Test finalize
        resp = await client.post(
            f"/api/v1/research/sessions/{sid}/finalize",
            params={
                "thesis": "Test thesis. This is a research conclusion.",
                "decision": "hold",
                "confidence": 0.65,
            },
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

asyncio.run(test())
