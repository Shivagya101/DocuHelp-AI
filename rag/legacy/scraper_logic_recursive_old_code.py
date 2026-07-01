import sys
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright
from utils.rabbitmq_provider import publish_to_queue
from utils.redis_provider import get_redis_connection, enqueue_scrape_task

# FIX FOR WINDOWS: Playwright uses asyncio subprocesses which crash if SelectorEventLoop is used.
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

def fetch_and_publish(url: str, base_url: str = None, current_depth: int = 0, max_depth: int = 2, is_cron_update: bool = False):
    """
    RQ task to scrape a URL using Playwright, extract internal links for DLS, and publish HTML to RabbitMQ.
    """
    if base_url is None:
        base_url = url

    redis_conn = get_redis_connection()
    visited_key = f"visited:{base_url}"
    active_key = f"active:{url}"

    print(f"[Scraper] Starting scrape for URL: {url} (Depth {current_depth}/{max_depth})")
    
    html_content = ""
    try:
        with sync_playwright() as p:
            # Use chromium in headless mode
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 1. BOT EVASION: Hide navigator.webdriver
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # 2. NETWORK INTERCEPTION: Block images, css, and media to make scraping lightning fast
            def intercept_route(route):
                if route.request.resource_type in ["image", "stylesheet", "media", "font"]:
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", intercept_route)

            # Wait until network is mostly idle to ensure JS is rendered
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 3. AUTO-SCROLLING: Force lazy-loaded content to render
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000) # Give lazy-load a brief moment to fetch text
            
            html_content = page.content()
            browser.close()
            
        print(f"[Scraper] Successfully scraped {len(html_content)} characters.")
    except Exception as e:
        print(f"[Scraper] CRASH DETECTED for {url}: {e}")
        # Release locks so it can be retried
        redis_conn.srem(visited_key, url)
        redis_conn.delete(active_key)
        # Re-raise the exception so RQ marks the job as Failed and triggers a Retry
        raise e
        
    if not html_content:
        return

    # Extract internal links for Depth-Limited Search
    if not is_cron_update and current_depth < max_depth:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc
            base_path = parsed_base.path if parsed_base.path else "/"
            
            valid_links_to_process = []
            
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                absolute_link = urljoin(url, href)
                absolute_link = absolute_link.split("#")[0]
                # NORMALIZE: Ensure child links match main.py exactly
                absolute_link = absolute_link.rstrip("/")
                
                parsed_link = urlparse(absolute_link)
                link_domain = parsed_link.netloc
                link_path = parsed_link.path
                
                if link_domain == base_domain and absolute_link.startswith("http"):
                    if link_path.startswith(base_path):
                        if absolute_link not in valid_links_to_process:
                            valid_links_to_process.append(absolute_link)
                            
            if valid_links_to_process:
                # 1. Batch filter with PostgreSQL (Long-Term Memory)
                from database import AsyncSessionLocal
                from sqlalchemy import select
                from database import ProcessedSite

                async def filter_db_links(links):
                    async with AsyncSessionLocal() as async_db:
                        result = await async_db.execute(select(ProcessedSite.url).filter(ProcessedSite.url.in_(links)))
                        existing_urls = set(result.scalars().all())
                    return [link for link in links if link not in existing_urls]

                try:
                    new_links = asyncio.run(filter_db_links(valid_links_to_process))
                except Exception as e:
                    print(f"[Scraper] DB filter error: {e}")
                    new_links = valid_links_to_process

                # 2. Process remaining new links
                for link in new_links:
                    # Short-Term Active Lock
                    active_lock_key = f"active:{link}"
                    is_fresh = redis_conn.set(active_lock_key, "1", nx=True, ex=1800)
                    if not is_fresh:
                        continue # Someone else is processing this right now
                        
                    # 5-page limit check
                    redis_conn.sadd(visited_key, link)
                    if redis_conn.scard(visited_key) > 5:
                        redis_conn.srem(visited_key, link) # ROLLBACK: Remove from bloated bucket
                        redis_conn.delete(active_lock_key) # release lock
                        print(f"[Scraper] MAX PAGE LIMIT REACHED (5) for {base_url}. Enqueueing stopped.")
                        break # Stop enqueuing for this scrape tree!
                        
                    enqueue_scrape_task(link, base_url, current_depth + 1, max_depth)
        except Exception as e:
            print(f"[Scraper] Error enqueuing internal links: {e}")
    # Publish to RabbitMQ
    try:
        payload = {
            "url": url,
            "base_url": base_url,
            "html": html_content,
            "is_cron_update": is_cron_update
        }
        asyncio.run(publish_to_queue("parse_tasks", payload))
        print(f"[Scraper] Successfully published payload to RabbitMQ queue 'parse_tasks'.")
        
    except Exception as e:
        print(f"[Scraper] Error publishing to RabbitMQ: {e}")
        raise
