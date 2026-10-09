
import requests
import time
import datetime
import threading

import csv
from queue import Queue
from concurrent.futures import ThreadPoolExecutor


API = "https://en.wikipedia.org/w/api.php"

request_lock = threading.Lock()
state_lock = threading.Lock()
next_request_time = 0.0
workers = 1

def get_members(category):
    global next_request_time

    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "page|subcat",
        "cmlimit": "max",
        "format": "json",
        "maxlag": 5,
    }

    with requests.Session() as session:
        session.headers.update({"User-Agent": "PRIResearchCrawler/1.0 (contact: up202207447@up.pt)"})

        while True:
            for attempt in range(5):

                with request_lock:
                    now = time.monotonic()
                    delay = max(0, next_request_time - now)
                    if delay:
                        time.sleep(delay)
                    next_request_time = time.monotonic() + 0.5

                try:
                    response = session.get(
                        API, params=params, timeout=30
                    )

                    if response.status_code in (429, 503):
                        delay = float(response.headers.get(
                            "Retry-After", max(5, 2 ** attempt)
                        ))
                        time.sleep(delay)
                        continue

                    response.raise_for_status()
                    data = response.json()

                    if data.get("error", {}).get("code") == "maxlag":
                        delay = float(response.headers.get(
                            "Retry-After", 5
                        ))
                        time.sleep(max(5, delay))
                        continue

                    if "error" in data:
                        raise RuntimeError(data["error"])

                    break

                except requests.RequestException:
                    if attempt == 4:
                        raise
                    time.sleep(max(5, 2 ** attempt))
            else:
                raise RuntimeError(f"Retries exhausted: {category}")

            yield from data["query"]["categorymembers"]

            if "continue" not in data:
                break

            params.update(data["continue"])

def crawl_category(root, max_depth=2):
    queue = Queue()
    queue.put((root, 0))

    visited_categories = {root}
    articles = {}
    errors = []

    def worker(worker_id):
        while True:
            item = queue.get()

            if item is None:
                queue.task_done()
                return

            category, depth = item

            try:
                print(f"[CATEGORY] Depth={depth} | {category} | WorkerId: {worker_id}", flush=True)

                members = list(get_members(category))
                new_articles = 0

                with state_lock:
                    for member in members:
                        if member["ns"] == 0: #https://www.mediawiki.org/wiki/Help:Namespaces
                            page_id = member["pageid"]
            
                            if page_id not in articles:
                                new_articles += 1
                                articles.setdefault(page_id, {
                                    "id": page_id,
                                    "title": member["title"],
                                    "categories": set()
                                })
            
                            articles[page_id]["categories"].add(category)
            
                        elif member["ns"] == 14 and depth < max_depth:
                            subcategory = member["title"]

                            if subcategory not in visited_categories:
                                visited_categories.add(subcategory)
                                queue.put((subcategory, depth + 1))
                print(
                    f"[DONE] {category} | "
                    f"New articles: {new_articles} | "
                    f"Total: {len(articles)} | "
                    f"Queue: {queue.qsize()}",
                    flush=True
                )
            except Exception as e:
                with state_lock:
                    errors.append((category, str(e)))
                print(f"[ERROR] {category}: {e}", flush=True)
            finally:
                queue.task_done()

    for article in articles.values():
        article["categories"] = sorted(article["categories"])

    print(
        f"[FINISHED] Categories: {len(visited_categories)} | "
        f"Unique articles: {len(articles)}",
        flush=True
    )

    print(f"[START] Crawling {root} Max Workers: {workers}", flush=True)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, i) for i in range(workers)]

        queue.join()

        for _ in range(workers):
            queue.put(None)

        for future in futures:
            future.result()
    
    return list(articles.values())

def crawler():

    print(f"[START] Crawler using {workers} Threads (Workers)", flush=True)
    start = time.perf_counter()
    
    articles = crawl_category(
        "Category:Man-made disasters",
        max_depth=0
    )

    ct = datetime.datetime.now()

    with open(f'/app/src/{ct}-index.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=articles[0].keys())
        
        writer.writeheader()
        writer.writerows(articles)

    elapsed = time.perf_counter() - start

    print(f"Found {len(articles)} unique articles")
    print(f"Exec time: {elapsed:.2f}s\n")

if __name__ == "__main__":
    crawler()