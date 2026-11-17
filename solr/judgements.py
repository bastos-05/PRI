"""Pool the top results of every setup for every query into one CSV for manual judging.
overrides `fields` (adds text) and `limit`, and writes solr/eval/judgments.csv.
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

CORE = "http://127.0.0.1:8983/solr/pri/select"
ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 20 # how many results to take per query and setup
SNIPPET = 400
CONFIG = Path(__file__).parent / "eval" / "config"
OUT = Path(__file__).parent / "eval" / "judgments.csv" 

setups = sorted(d for d in CONFIG.glob("queries_*") if d.is_dir())
names = [d.name.split("_", 1)[1].upper() for d in setups]
query_ids = sorted({f.stem for d in setups for f in d.glob("*.json")})

rows = []
for qid in query_ids:
    pool = {}
    query_text = ""
    for setup_dir, name in zip(setups, names):
        path = setup_dir / f"{qid}.json"
        if not path.exists():
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        query_text = body["query"]
        body["fields"] = "id, title, score, text"
        body["limit"] = ROWS
        req = urllib.request.Request(
            CORE, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            docs = json.load(r)["response"]["docs"]
        for rank, d in enumerate(docs, 1):
            entry = pool.setdefault(d["id"], {
                "query_id": qid,
                "query": query_text,
                "doc_id": d["id"],
                "title": d["title"],
                "url": f"https://en.wikipedia.org/?curid={d['id']}",
                "snippet": " ".join(d.get("text", "").split())[:SNIPPET],
                **{f"rank_{n}": "" for n in names},
                "relevance": "",
            })
            entry[f"rank_{name}"] = rank
    rows.extend(sorted(pool.values(), key=lambda e: min(
        (e[f"rank_{n}"] for n in names if e[f"rank_{n}"] != ""), default=999)))
    print(f"{qid}: {len(pool)} unique documents | {query_text}")

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
print(f"\nWrote {len(rows)} rows to {OUT}")