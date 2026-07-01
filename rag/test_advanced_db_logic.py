import asyncio
from database import AsyncSessionLocal
from repository.scan_repository import (
    get_scan_by_url_async, 
    get_chunks_for_scan_async, 
    apply_delta_update_async, 
    update_scan_content_async,
    ProcessedSite,
    PolicyChunk
)
from ai_engine import generate_chunks
from merkle_sync import MerkleTree, diff_trees
from sqlalchemy import select

async def run_tests():
    print("=== STARTING ADVANCED DB LOGIC TESTS ===\n")
    
    async with AsyncSessionLocal() as db:
        # Get original Stripe scan
        original_url = "https://docs.stripe.com/payments"
        scan = await get_scan_by_url_async(db, original_url)
        
        if not scan:
            print(f"Error: {original_url} not found in DB. Make sure you ran the integration test.")
            return

        original_text = scan.policy_text
        print(f"Loaded original scan '{original_url}' with {len(original_text)} chars.")

        # ==========================================
        # TEST 1: Merkle Tree Delta Update
        # ==========================================
        print("\n--- TEST 1: Merkle Tree Delta Update ---")
        # Let's modify the text by adding a paragraph in the middle, and removing some text
        lines = original_text.split('\n')
        # Remove a chunk of lines (e.g. lines 50 to 60)
        del lines[50:60]
        # Insert a new paragraph
        lines.insert(20, "\n# NEW FAKE HEADING\nThis is a brand new fake paragraph added to test the Merkle tree functionality. It should be detected as a new chunk, while leaving the rest of the chunks perfectly intact without re-embedding them!\n")
        
        modified_text = "\n".join(lines)
        print(f"Modified text length: {len(modified_text)} chars.")
        
        new_chunks = generate_chunks(modified_text)
        print(f"Generated {len(new_chunks)} chunks for the modified text.")
        
        old_chunks = await get_chunks_for_scan_async(db, scan.id)
        print(f"Retrieved {len(old_chunks)} old chunks from DB.")
        
        old_tree = MerkleTree(old_chunks)
        new_tree = MerkleTree(new_chunks)
        
        if old_tree.root_hash == new_tree.root_hash:
            print("[FAILED] Merkle trees matched, but text was modified!")
        else:
            print("[SUCCESS] Merkle trees have different root hashes.")
            to_delete, to_add, to_update_parents = diff_trees(old_tree, new_tree)
            print(f"Diff results: {len(to_delete)} to delete, {len(to_add)} to add, {len(to_update_parents)} sibling parents to update.")
            
            # Apply delta update
            deleted, added = await apply_delta_update_async(db, scan.id, to_delete, to_add, to_update_parents)
            print(f"[SUCCESS] Delta update applied. Deleted: {deleted}, Added: {added}")


        # ==========================================
        # TEST 2: pg_trgm Thin Wrapper Detection
        # ==========================================
        print("\n--- TEST 2: pg_trgm Duplicate Detection ---")
        # We will use the exact same original chunks, but try to save them under a NEW URL
        duplicate_url = "https://docs.stripe.com/payments/fake-seo-spam"
        print(f"Attempting to index almost identical content under a new URL: {duplicate_url}")
        
        # We use the new_chunks which is 95% similar to the original text
        result = await update_scan_content_async(
            db, 
            url=duplicate_url, 
            policy_text=modified_text,
            chunks=new_chunks,
            internal_links=[]
        )
        
        if not result.get("success"):
            print(f"[SUCCESS] Expected rejection. Reason: {result.get('reason')}")
        else:
            print(f"[FAILED] Site was indexed successfully despite being a duplicate.")
            
    print("\n=== TESTS COMPLETE ===")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_tests())
