"""Print the top results of every query in solr/eval/config/queries_* (one folder per setup).

The queries live in JSON files (Solr JSON Request API), the same ones used by the
evaluation pipeline in solr/eval, so there is a single source of truth.

Setup A (queries_a): simple, title + text, equal weights.
Setup B (queries_b): English analysis (stemming, stop words), title boost, phrase boost.

Usage: python solr/run_queries.py [rows]
"""
import json
import sys
import urllib.request
from pathlib import Path

CORE = "http://127.0.0.1:8983/solr/pri/select"
ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
CONFIG = Path(__file__).parent / "eval" / "config"

for setup_dir in sorted(CONFIG.glob("queries_*")):
    setup = setup_dir.name.split("_", 1)[1].upper()
    for query_file in sorted(setup_dir.glob("*.json")):
        body = json.loads(query_file.read_text(encoding="utf-8"))
        body["limit"] = ROWS
        request = urllib.request.Request(
            CORE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)["response"]
        print(f"\n{query_file.stem} | setup {setup} | {data['numFound']} hits | {body['query']}")
        for rank, doc in enumerate(data["docs"], 1):
            print(f"  {rank:2}. {doc['title']}  [id {doc['id']}]  ({doc['score']:.2f})")
