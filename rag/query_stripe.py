import asyncio
from database import AsyncSessionLocal
from repository.scan_repository import get_scan_by_url_async

async def run():
    async with AsyncSessionLocal() as session:
        scan = await get_scan_by_url_async(session, "https://docs.stripe.com/payments")
        if scan:
            print(f"Total links: {len(scan.internal_links)}")
            print("Internal URLs stored:")
            for link in scan.internal_links:
                print(f" - {link}")
        else:
            print("Stripe URL not found in database.")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
