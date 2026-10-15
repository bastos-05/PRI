
import requests
import time
import datetime
import threading
import sqlite3
import os

import csv
from queue import Queue
from concurrent.futures import ThreadPoolExecutor


API = "https://en.wikipedia.org/w/api.php"
if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"
else:
    DB_PATH = "/app/data/crawler.db"

request_lock = threading.Lock()
state_lock = threading.Lock()
next_request_time = 0.0
workers = 3

def get_members(session, category):
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
                    API, params=params, timeout=30
                )

                if response.status_code in (429, 503):
                    print(
                        f"[THROTTLED] "
                        f"Status={response.status_code} | "
                        f"Retry-After={response.headers.get('Retry-After')} | "
                        f"X-Cache={response.headers.get('X-Cache')} | "
                        f"Server={response.headers.get('Server')}",
                        flush=True
                    )

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


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        print(conn)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                page_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                name TEXT PRIMARY KEY,
                processed BOOLEAN NOT NULL DEFAULT 0,
                depth INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS belongs_to (
                page_id INTEGER NOT NULL,
                category_name TEXT NOT NULL,

                PRIMARY KEY (page_id, category_name),

                FOREIGN KEY (page_id)
                    REFERENCES articles(page_id),

                FOREIGN KEY (category_name)
                    REFERENCES categories(name)
            );

            CREATE TABLE IF NOT EXISTS category_edges (
                parent_name TEXT NOT NULL,
                child_name TEXT NOT NULL,

                PRIMARY KEY (parent_name, child_name),

                FOREIGN KEY (parent_name)
                    REFERENCES categories(name),

                FOREIGN KEY (child_name)
                    REFERENCES categories(name)
            );

            DROP TABLE articles_filtred;

            CREATE TABLE IF NOT EXISTS filtered_articles (
                page_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(status IN ('PENDING', 'FETCHED', 'NORMALIZED')),
                FOREIGN KEY (page_id) REFERENCES articles(page_id)
            );
        """)

def crawl_category(root, max_depth=2):
    crawler_queue = Queue()

    with sqlite3.connect(DB_PATH) as conn:
        pending_categories = conn.execute(
            """
            SELECT name, depth
            FROM categories
            WHERE processed = 0 AND depth <= ?
            ORDER BY depth
            """,
            (max_depth,)
        ).fetchall()

        processed_categories = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM categories WHERE processed = 1"
            )
        }

        root_processed = conn.execute(
            "SELECT processed FROM categories WHERE name = ?",
            (root,)
        ).fetchone()

    visited_categories = set()
    
    for category, depth in pending_categories:
        visited_categories.add(category)
        crawler_queue.put((category, depth))

    if root_processed is None and root not in visited_categories:
        visited_categories.add(root)
        crawler_queue.put((root, 0)) 

    db_queue = Queue()

    articles = {}
    errors = []

    def worker(worker_id):
        with requests.Session() as session:
            session.headers.update({
                "User-Agent": "PRIResearchCrawler/1.0 (contact:up202207447@up.pt)"
            })

            while True:
                item = crawler_queue.get()

                if item is None:
                    crawler_queue.task_done()
                    return

                category, depth = item

                try:
                    print(f"[CATEGORY] Depth={depth} | {category} | WorkerId: {worker_id}", flush=True)

                    members = list(get_members(session, category))

                    new_articles = 0

                    with state_lock:
                        for member in members:
                            if member["ns"] == 0:
                                page_id = member["pageid"]

                                if page_id not in articles:
                                    articles[page_id] = {
                                        "id": page_id,
                                        "title": member["title"],
                                        "categories": set()
                                    }
                                    new_articles += 1

                                articles[page_id]["categories"].add(category)

                            elif member["ns"] == 14:
                                subcategory = member["title"]

                                if (
                                    depth < max_depth 
                                    and subcategory not in visited_categories
                                    and subcategory not in processed_categories
                                ):
                                    visited_categories.add(subcategory)
                                    crawler_queue.put((subcategory, depth + 1))

                    db_queue.put((category, members, depth))

                    print(
                        f"[DONE] {category} | "
                        f"New articles: {new_articles} | "
                        f"Total: {len(articles)} | "
                        f"Queue: {crawler_queue.qsize()}",
                        flush=True
                    )

                
                except Exception as e:
                    with state_lock:
                        errors.append((category, str(e)))
                    print(f"[ERROR] {category}: {e}", flush=True)
                finally:
                    crawler_queue.task_done()

    def save_category(conn, category, members, depth):
        with conn:
            conn.execute(
                """
                INSERT INTO categories (name, depth)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    depth = MIN(categories.depth, excluded.depth)
                """,
                (category, depth)
            )

            for member in members:
                if member["ns"] == 0:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO articles (page_id, title)
                        VALUES (?, ?)
                        """,
                        (member["pageid"], member["title"])
                    )

                    conn.execute(
                        """
                        INSERT OR IGNORE INTO belongs_to
                        (page_id, category_name)
                        VALUES (?, ?)
                        """,
                        (member["pageid"], category)
                    )

                elif member["ns"] == 14:
                    subcategory = member["title"]

                    conn.execute(
                        """
                        INSERT INTO categories (name, depth)
                        VALUES (?, ?)
                        ON CONFLICT(name) DO UPDATE SET
                            depth = MIN(categories.depth, excluded.depth)
                        """,
                        (subcategory, depth+1)
                    )

                    conn.execute(
                        """
                        INSERT OR IGNORE INTO category_edges
                        (parent_name, child_name)
                        VALUES (?, ?)
                        """,
                        (category, subcategory)
                    )

            conn.execute(
                """
                UPDATE categories
                SET processed = 1
                WHERE name = ?
                """,
                (category,)
            )

    db_errors = []

    def db_worker():
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            while True:
                task = db_queue.get()

                try:
                    if task is None:
                        return

                    category, members, depth = task

                    for attempt in range(5):
                        try:
                            save_category(conn, category, members, depth)

                            print(f"[DB SAVED] {category}",flush=True)
                            break

                        except sqlite3.OperationalError as e:

                            if e.sqlite_errorcode not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                                raise

                            if attempt == 4:
                                raise

                            delay = min(30, 2 ** attempt)

                            print(
                                f"[DB RETRY] {category} | "
                                f"Attempt={attempt + 1} | "
                                f"Error={e} | Delay={delay}s",
                                flush=True
                            )

                            time.sleep(delay)

                    print(f"[PERSISTED] {category}", flush=True)
                except Exception as e:
                    db_errors.append((category, str(e)))
                    print(f"[DB ERROR] {category}: {e}", flush=True)

                finally:
                    db_queue.task_done()
        finally:
            conn.close()
    
    print(f"[START] Crawling {root} Max Workers: {workers}", flush=True)

    db_thread = threading.Thread(target=db_worker)
    db_thread.start()
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, i) for i in range(workers)]

        try:
            print("[WAIT] crawler_queue.join()", flush=True)
            crawler_queue.join()
            print("[OK] crawler_queue.join()", flush=True)

        finally:
            print("[STOP] Sending shutdown signals", flush=True)

            for _ in range(workers):
                crawler_queue.put(None)

        print("[WAIT] Worker futures", flush=True)
        for future in futures:
            future.result()

        print("[OK] All crawler workers stopped", flush=True)

        for article in articles.values():
            article["categories"] = sorted(article["categories"])

        print(
            f"[FINISHED] Categories: {len(visited_categories)} | "
            f"Unique articles: {len(articles)}",
            flush=True
        )

    print("[WAIT] db_queue.join()", flush=True)
    db_queue.join()
    print("[OK] db_queue.join()", flush=True)

    db_queue.put(None)
    db_thread.join()

    print("[OK] DB worker stopped", flush=True)

    if errors or db_errors:
        raise RuntimeError(
            f"Crawler failed: {len(errors)} crawling errors, "
            f"{len(db_errors)} database errors.\n"
            f"Crawling: {errors[:5]}\n"
            f"Database: {db_errors[:5]}"
        )

    with sqlite3.connect(DB_PATH) as conn:
        total_articles = conn.execute(
            "SELECT COUNT(*) FROM articles"
        ).fetchone()[0]

        total_categories = conn.execute(
            "SELECT COUNT(*) FROM categories WHERE processed = 1"
        ).fetchone()[0]

    print(
        f"[DATABASE] Articles: {total_articles} | "
        f"Processed categories: {total_categories}"
    )
    
    return list(articles.values())

def crawler():

    print(f"[START] Crawler using {workers} Threads (Workers)", flush=True)
    start = time.perf_counter()

    ct = datetime.datetime.now()
    foldername = f"crawl-{ct}"

    if not os.path.exists(foldername):
        os.makedirs(foldername)

    init_db()
    
    articles = crawl_category(
        "Category:Man-made disasters",
        max_depth=8
    )

    elapsed = time.perf_counter() - start

    print(f"Found {len(articles)} unique articles")
    print(f"Exec time: {elapsed:.2f}s\n")

if __name__ == "__main__":
    crawler()