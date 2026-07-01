import asyncio
from database import AsyncSessionLocal
from repository.scan_repository import get_stale_scans_async
from utils.redis_provider import enqueue_scrape_task

async def run_cronjob_async():
    print("[Cron Worker] Starting periodic synchronization of all URLs older than 30 days (Async)...")
    async with AsyncSessionLocal() as db:
        try:
            # Fetch scans older than 30 days
            stale_scans = await get_stale_scans_async(db, days_old=30)
            
            if not stale_scans:
                print("[Cron Worker] No URLs older than 30 days found. Everything is up to date.")
                return

            print(f"[Cron Worker] Found {len(stale_scans)} URLs needing updates. Dispatching to RabbitMQ...")
            
            for scan in stale_scans:
                if scan.policy_text and scan.policy_text.startswith('{"status": "rejected"'):
                    print(f"[Cron Worker] Deleting expired rejected site (TTL > 30 days): {scan.url}")
                    await db.delete(scan)
                else:
                    print(f"Dispatching Update Task for URL: {scan.url}")
                    # Enqueue task with is_cron_update=True
                    enqueue_scrape_task(scan.url, base_url=scan.url, current_depth=0, max_depth=2, is_cron_update=True)
            
            await db.commit()
                
        except Exception as e:
            print(f"[Cron Worker] Error during sync: {e}")
            
    print("\n[Cron Worker] Dispatch cycle finished. Going back to sleep.")

def run_cronjob():
    if __import__('sys').platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_cronjob_async())

if __name__ == "__main__":
    run_cronjob()
