
import requests
import time
import csv
from collections import deque

API = "https://en.wikipedia.org/w/api.php"

session = requests.Session()
session.headers.update({
    "User-Agent": "PRIResearchCrawler/1.0 (contact: up202207447@up.pt)"
})


def get_members(category):
    params = {
        "action": "query",
        "list": "categorymembers", #https://www.mediawiki.org/wiki/API:Categorymembers
        "cmtitle": category,
        "cmtype": "page|subcat",
        "cmlimit": "max",
        "format": "json",
    }

    while True:
        response = session.get(API, params=params, timeout=30)

        if response.status_code in (429, 503):
            delay = int(response.headers.get("Retry-After", 10))
            time.sleep(delay)
            continue

        response.raise_for_status()
        data = response.json()

        yield from data["query"]["categorymembers"]

        if "continue" not in data:
            break

        params.update(data["continue"])
        time.sleep(0.5)

def crawl_category(root, max_depth=2):
    queue = deque([(root, 0)])
    visited_categories = set()
    articles = {}

    print(f"[START] Crawling {root}", flush=True)

    while queue:
        category, depth = queue.popleft()

        if category in visited_categories:
            continue

        visited_categories.add(category)

        print(f"[CATEGORY] Depth={depth} | {category}", flush=True)

        new_articles = 0

        for member in get_members(category):
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
                queue.append((member["title"], depth + 1))

        print(
            f"[DONE] {category} | "
            f"New articles: {new_articles} | "
            f"Total: {len(articles)} | "
            f"Queue: {len(queue)}",
            flush=True
        )

        time.sleep(0.5)

    for article in articles.values():
        article["categories"] = sorted(article["categories"])

    print(
        f"[FINISHED] Categories: {len(visited_categories)} | "
        f"Unique articles: {len(articles)}",
        flush=True
    )

    return list(articles.values())

def retrieve():
    print("[START] Crawler", flush=True)
    start = time.perf_counter()
    
    articles = crawl_category(
        "Category:Man-made disasters",
        max_depth=2
    )

    with open('/app/src/test.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=articles[0].keys())
        
        writer.writeheader()
        writer.writerows(articles)

    elapsed = time.perf_counter() - start

    print(f"Found {len(articles)} unique articles")
    print(f"Exec time: {elapsed:.2f}s\n")

if __name__ == "__main__":
    retrieve()
