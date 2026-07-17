import asyncio
import httpx
import time
import os
import sys
from database import async_engine
from sqlalchemy.sql import text

API_URL = "http://localhost:8000"
MERKLE_URL = "http://localhost:8001/merkle.html"
FILE_PATH = r"C:\Users\Shivagya\.gemini\antigravity-ide\brain\aae534de-4083-40c4-8c09-0300dbf9bf25\scratch\merkle.html"

async def test_merkle_tree():
    print("=== TEST 4: MERKLE TREE CRON SYNC ===")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("1. Enqueuing mock policy...")
        await client.post(f"{API_URL}/sync_bulk", json={"urls": [MERKLE_URL]})
        
        print("2. Waiting for it to be indexed...")
        while True:
            resp = await client.post(f"{API_URL}/analyze", json={"url": MERKLE_URL})
            if resp.json().get("status") == "indexed":
                print("   -> Successfully indexed v1.")
                break
            time.sleep(3)
            
        print("3. Modifying merkle.html (changing Section 2)...")
        new_html = """<html>
<head><title>Mock Policy v2</title></head>
<body>
<h1>Terms of Service</h1>
<p>Welcome to our mock service. This is version 1.</p>
<p>Section 1: You must be 18 years or older.</p>
<p>Section 2: We MAY share your data with trusted partners.</p>
<p>Section 3: You can cancel anytime.</p>
</body>
</html>"""
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(new_html)
            
        print("4. Backdating PostgreSQL created_at by 31 days to trigger cron...")
        async with async_engine.begin() as conn:
            await conn.execute(text(f"UPDATE processed_sites SET created_at = created_at - interval '31 days' WHERE url LIKE '%merkle.html%'"))
            
        print("5. Running Cron Worker manually...")
        from workers.cron_worker import run_cronjob_async
        await run_cronjob_async()
        
        print("\n SUCCESS: Merkle test complete. Check the logs above for 'Merkle Tree mismatch' and 'Differential Sync Complete'!")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_merkle_tree())
