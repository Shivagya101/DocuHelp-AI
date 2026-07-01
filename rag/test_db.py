import asyncio
from database import AsyncSessionLocal
from repository.scan_repository import get_scan_by_url_async
import sys
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def check():
    async with AsyncSessionLocal() as db:
        scan = await get_scan_by_url_async(db, "https://react.dev")
        if scan:
            print("Found Scan!")
            print(f"internal_links count: {len(scan.internal_links) if scan.internal_links else 0}")
            if scan.internal_links:
                print("Sample:", scan.internal_links[:5])
        else:
            print("No scan found.")

asyncio.run(check())
