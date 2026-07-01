import asyncio
from database import AsyncSessionLocal, ProcessedSite
from sqlalchemy import select, update
from datetime import datetime, timedelta

async def backdate_stripe():
    print("Backdating Stripe scan to 5 months old...")
    async with AsyncSessionLocal() as db:
        original_url = "https://docs.stripe.com/payments"
        
        # Calculate 5 months ago (approx 150 days)
        five_months_ago = datetime.utcnow() - timedelta(days=150)
        
        result = await db.execute(select(ProcessedSite).where(ProcessedSite.url == original_url))
        scan = result.scalars().first()
        
        if not scan:
            print("Scan not found!")
            return
            
        print(f"Current created_at: {scan.created_at}")
        
        # Update the timestamp
        await db.execute(
            update(ProcessedSite)
            .where(ProcessedSite.id == scan.id)
            .values(created_at=five_months_ago)
        )
        await db.commit()
        
        # Verify
        result = await db.execute(select(ProcessedSite).where(ProcessedSite.url == original_url))
        scan = result.scalars().first()
        print(f"New created_at: {scan.created_at}")
        print("Successfully backdated!")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backdate_stripe())
