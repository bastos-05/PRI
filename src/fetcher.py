import os
import json
import sqlite3
import threading
import time
import requests
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_URL = "https://en.wikipedia.org/w/api.php"
if os.path.exists("/opt/airflow"):
    RAW_PATH = Path("/opt/airflow/data/raw.jsonl")
    DB_PATH = "/opt/airflow/data/crawler.db"
else:
    RAW_PATH = Path("/app/data/raw.jsonl")
    DB_PATH = "/app/data/crawler.db"

WORKERS = 3
BATCH_SIZE = 20

def get_fetch_config():
    config = json.loads(os.environ.get("PIPELINE_CONFIG") or "{}")
    fetch_cfg = config.get("fetch") or {}

    return {
        "workers": int(fetch_cfg.get("workers", WORKERS)),
        "batch_size": int(fetch_cfg.get("batch_size", BATCH_SIZE))
    }

request_lock = threading.Lock()
storage_lock = threading.Lock()
next_request_time = 0.0

def save_articles(articles):
    if not articles:
        return 0

    saved = 0

    with storage_lock:
        with RAW_PATH.open("a", encoding="utf-8") as f:
            for article in articles:
                invalid = False
                if article.get("missing"):
                    print(f"[MISSING] {article}", flush=True)
                    invalid = True
                if not article.get("revisions"):
                    print(f"[NO REVISIONS] {article}", flush=True)
                    invalid = True

                if invalid:
                    with sqlite3.connect(DB_PATH, timeout=30) as conn:
                        conn.execute(
                            """
                            UPDATE filtered_articles
                            SET status = 'SKIPPED'
                            WHERE page_id = ?
                            """, (article["pageid"],)
                        )
                        continue

                revision = article["revisions"][0]

                document = {
                    "page_id": article["pageid"],
                    "title": article["title"],
                    "revision_id": revision["revid"],
                    "wikitext": revision["slots"]["main"]["content"]
                }

                f.write(json.dumps(document, ensure_ascii=False) + "\n")
                saved += 1

            f.flush()
            os.fsync(f.fileno())

        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.executemany(
                """
                UPDATE filtered_articles
                SET status = 'FETCHED'
                WHERE page_id = ?
                  AND status = 'PENDING'
                """,
                [
                    (article["pageid"],)
                    for article in articles
                    if not article.get("missing")
                    and article.get("revisions")
                ]
            )
    return saved

def fetch_articles(page_ids, session):
    global next_request_time

    params = {
        "action": "query",
        "prop": "revisions",
        "pageids": "|".join(map(str, page_ids)),
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
        "maxlag": 5
    }

    while True:
        for attempt in range(5):

            with request_lock:
                now = time.monotonic()
                delay = max(0, next_request_time - now)

                if delay:
                    time.sleep(delay)

                next_request_time = time.monotonic() + 0.35

            try:
                response = session.get(
                    API_URL, params=params, timeout=60
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
            raise RuntimeError("Retries exhausted")

        yield from data.get("query", {}).get("pages", [])

        if "continue" in data:
            print(
                f"[CONTINUE] {data['continue']} "
                f"| Requested: {len(page_ids)}",
                flush=True
            )
        else:
            break

        params.update(data["continue"])

def fetch():
    config = get_fetch_config()

    workers = config["workers"]
    batch_size = config["batch_size"]

    processed = 0
    counter_lock = threading.Lock()
    start = time.perf_counter()

    fetcher_queue = Queue()

    with sqlite3.connect(DB_PATH) as conn:
        pending_articles = conn.execute(
            """
            SELECT page_id
            FROM filtered_articles
            WHERE status = 'PENDING'
            """
        ).fetchall()

    def worker(worker_id):
        nonlocal processed

        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "PRIResearchCrawler/1.0 (contact:up202207447@up.pt)"
            })

            while True:
                articles_to_process = []
                finished = False

                for _ in range(batch_size):
                    article_to_process = fetcher_queue.get()

                    if article_to_process is None:
                        fetcher_queue.task_done()
                        finished = True
                        break
        
                    articles_to_process.append(article_to_process)
                
                if articles_to_process:
                    try:
                        articles = list(fetch_articles(articles_to_process, session))
                        saved = save_articles(articles)

                        with counter_lock:
                            processed += saved

                    finally:
                        for _ in articles_to_process:
                            fetcher_queue.task_done()

                if finished:
                    return

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(len(pending_articles), flush=True)
    pending_articles = pending_articles[:5000]
    for (page_id,) in pending_articles:
        fetcher_queue.put(page_id)

    print(len(pending_articles), flush=True)
    print(fetcher_queue.qsize(), flush=True)

    for _ in range(workers):
        fetcher_queue.put(None)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(worker, i)
            for i in range(workers)
        ]

        for future in futures:
            future.result()

    elapsed = time.perf_counter() - start
    throughput = processed / elapsed

    print(f"Artigos guardados: {processed}", flush=True)
    print(f"Tempo: {elapsed:.2f}s", flush=True)
    print(f"Throughput: {throughput:.2f} artigos/s", flush=True)

    with sqlite3.connect(DB_PATH) as conn:
        pending_articles_count = conn.execute(
            """
            SELECT page_id
            FROM filtered_articles
            WHERE status = 'PENDING'
            """
        ).fetchall()

        print(f"[PENDING STILL] {len(pending_articles_count)} articles", flush=True)

def recursive_fetch():
    while True:
        with sqlite3.connect(DB_PATH) as conn:
            pending_articles_count = conn.execute(
                """
                SELECT page_id
                FROM filtered_articles
                WHERE status = 'PENDING'
                """
            ).fetchall()

            print(f"[PENDING STILL] {len(pending_articles_count)} articles")
            if len(pending_articles_count) > 0:
                fetch()
            else:
                # Necessário para o normalizer
#                with storage_lock:
#                    with RAW_PATH.open("a", encoding="utf-8") as f:
#                        f.write(json.dumps({"type": "control", "status": "FINISHED"}) + "\n")
#                        f.flush()
#                        os.fsync(f.fileno())
                break

if __name__ == "__main__":
    recursive_fetch()