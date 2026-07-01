import time
import requests
import json
import sys

API_URL = "http://127.0.0.1:8000"
TARGET_URL = "https://docs.stripe.com/payments"

def print_step(msg):
    print(f"\n{'='*60}\n[TEST] {msg}\n{'='*60}")

def test_1_new_url():
    print_step(f"Test 1: Requesting a NEW URL ({TARGET_URL})")
    res = requests.post(f"{API_URL}/analyze", json={"url": TARGET_URL})
    print("Response Status Code:", res.status_code)
    data = res.json()
    print("Response Body:", json.dumps(data, indent=2))
    assert data["status"] == "processing", "Expected status to be processing"
    print("[PASS] Test 1 Passed: New URL correctly placed in queue.")

def test_2_pending_state():
    print_step(f"Test 2: Requesting the SAME URL while it is processing (Pending State)")
    res = requests.post(f"{API_URL}/analyze", json={"url": TARGET_URL})
    print("Response Status Code:", res.status_code)
    data = res.json()
    print("Response Body:", json.dumps(data, indent=2))
    assert data["status"] == "processing", "Expected status to be processing"
    assert "Already in queue" in data["message"], "Expected 'Already in queue' message"
    print("[PASS] Test 2 Passed: Race condition prevented, duplicate request caught.")

def test_3_cached_state():
    print_step("Test 3: Waiting for worker to finish, then checking Cached State")
    wait_time = 25
    print(f"Waiting {wait_time} seconds for Playwright to scrape and parser to index...")
    for i in range(wait_time):
        time.sleep(1)
        print(f"Waiting... {wait_time-i}s remaining")
    
    res = requests.post(f"{API_URL}/analyze", json={"url": TARGET_URL})
    print("Response Status Code:", res.status_code)
    data = res.json()
    print("Response Body (first 5 links):", json.dumps(data["internal_links"][:5] if data.get("internal_links") else [], indent=2))
    assert data["status"] == "cached", f"Expected status to be cached, got {data['status']}"
    assert len(data.get("internal_links", [])) > 0, "Expected internal links to be populated"
    print(f"[PASS] Test 3 Passed: URL cached successfully. Found {len(data['internal_links'])} internal links.")
    return data["internal_links"]

def test_4_sync_bulk(internal_links):
    print_step("Test 4: Bulk Syncing 2 internal pages")
    if len(internal_links) < 2:
        print("Not enough internal links found to test bulk sync.")
        return []
        
    target_urls = internal_links[:2]
    print(f"Queueing: {target_urls}")
    res = requests.post(f"{API_URL}/sync_bulk", json={"urls": target_urls})
    print("Response Status Code:", res.status_code)
    data = res.json()
    print("Response Body:", json.dumps(data, indent=2))
    assert data["status"] == "success", "Expected sync_bulk to succeed"
    print("[PASS] Test 4 Passed: Bulk sync queued successfully.")
    return target_urls

def test_5_chat():
    print_step("Test 5: Asking a question across the knowledge base")
    wait_time = 25
    print(f"Waiting {wait_time} seconds for the internal pages to be scraped and indexed...")
    for i in range(wait_time):
        time.sleep(1)
        print(f"Waiting... {wait_time-i}s remaining")
        
    question = "How do I accept payments using Stripe?"
    print(f"Question: {question}")
    
    with requests.post(f"{API_URL}/chat", json={"url": TARGET_URL, "question": question, "history": []}, stream=True) as r:
        print("Streaming response:")
        full_text = ""
        for line in r.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    try:
                        data = json.loads(line_str[6:])
                        if data['type'] == 'chunk':
                            text = data['text']
                            full_text += text
                            print(text, end='', flush=True)
                        elif data['type'] == 'citations':
                            print(f"\n[Citations: {data['citations']}]")
                    except Exception as e:
                        pass
        print("\n")
        assert len(full_text) > 20, "Expected a substantive answer"
    print("[PASS] Test 5 Passed: AI answered successfully using RAG context.")

def run_all():
    try:
        test_1_new_url()
        time.sleep(1)
        test_2_pending_state()
        links = test_3_cached_state()
        test_4_sync_bulk(links)
        test_5_chat()
        print_step("ALL INTEGRATION TESTS PASSED !")
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
    except Exception as e:
        print(f"\n[FAIL] UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    run_all()
