import os
import json
import asyncio
from database import AsyncSessionLocal
import aio_pika
from utils.rabbitmq_provider import consume_from_queue

async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(ignore_processed=True):
        try:
            body = message.body.decode()
            data = json.loads(body)
            url = data.get("url")
            html_content = data.get("html")
            
            if not url or not html_content:
                print("[Parser] Received invalid message payload.")
                await message.ack()
                return

            print(f"[Parser] Processing policy for URL: {url} ({len(html_content)} bytes)")
            
            # 1. Clean HTML to plain text
            from ai_engine import clean_html, generate_chunks
            clean_text = clean_html(html_content)
            
            if len(clean_text) < 100:
                print(f"[Parser] Content too short for {url}")
                await message.ack()
                return

            print(f"[Parser] Extracting text chunks for {url}...")
            
            # 2. Generate RAG chunks synchronously (CPU bound)
            chunks = generate_chunks(clean_text)
            
            is_cron_update = data.get("is_cron_update", False)
            
            # 3. Save or Update in PostgreSQL (Asynchronously!)
            async with AsyncSessionLocal() as db:
                try:
                    from repository.scan_repository import (
                        get_scan_by_url_async, 
                        get_chunks_for_scan_async, 
                        apply_delta_update_async, 
                        update_scan_content_async, 
                        update_scan_timestamp_async
                    )
                    from merkle_sync import MerkleTree, diff_trees
                    
                    if is_cron_update:
                        existing_scan = await get_scan_by_url_async(db, url)
                        if not existing_scan:
                            print(f"[Parser] Error: Cron update failed, scan not found for {url}")
                            await message.ack()
                            return
                            
                        print(f"[Parser] Running Merkle Tree diff for Cron Update: {url}")
                        old_chunks = await get_chunks_for_scan_async(db, existing_scan.id)
                        old_tree = MerkleTree(old_chunks)
                        new_tree = MerkleTree(chunks)
                        scan_id = existing_scan.id
                        
                        if old_tree.root_hash == new_tree.root_hash:
                            print(f"[Parser] No changes detected for {url}.")
                        else:
                            to_delete, to_add, to_update_parents = diff_trees(old_tree, new_tree)
                            await apply_delta_update_async(db, scan_id, to_delete, to_add, to_update_parents)
                            print(f"[Parser] Successfully updated {url} via Merkle Diff.")
                        
                        # Prevent infinite cron loops by resetting the timestamp!
                        await update_scan_timestamp_async(db, scan_id)
                    else:
                        result = await update_scan_content_async(
                            db, 
                            url=url, 
                            policy_text=clean_text,
                            chunks=chunks,
                            internal_links=data.get("internal_links", [])
                        )
                        if result and result.get("success"):
                            print(f"[Parser] Successfully indexed {len(chunks)} chunks for {url} to Database.")
                        else:
                            print(f"[Parser] Site Rejected for {url}: {result.get('reason') if result else 'Unknown error'}")
                except Exception as e:
                    print(f"[Parser] Error saving to database: {e}")
                    await db.rollback()
                
            # Acknowledge the message so RabbitMQ deletes it
            await message.ack()
            
        except Exception as e:
            print(f"[Parser] Critical Error during processing: {e}")
            # Nack the message so it goes back to the queue or dead-letter
            await message.nack(requeue=False)

async def main():
    print("[Parser] Starting Async RabbitMQ consumer...")
    # Keep a reference to the connection so it doesn't get garbage collected
    connection = await consume_from_queue("parse_tasks", process_message)
    
    try:
        # Wait indefinitely until interrupted
        await asyncio.Future()
    finally:
        await connection.close()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
