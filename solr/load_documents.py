"""Index data/final.jsonl into the 'pri' core. Safe to re-run (id = page_id overwrites).

Usage: python solr/load_documents.py [path/to/final.jsonl] [--clear]
Metadata (if present) is flattened to: location (text), year (int), deaths (int).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

CORE = "http://127.0.0.1:8983/solr/pri"
BATCH = 500
YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")
NUMBER = re.compile(r"\d[\d,\.]*")


def post(path, body):
    request = urllib.request.Request(
        CORE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def entries(metadata, field):
    return (metadata or {}).get(field) or []


def to_int(text):
    match = NUMBER.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return int(float(match.group().rstrip(".")))
    except ValueError:
        return None


def flatten(article):
    metadata = article.get("metadata") or {}
    doc = {
        "id": str(article["page_id"]),
        "page_id": article["page_id"],
        "revision_id": article["revision_id"],
        "title": article["title"],
        "text": article["text"],
    }
    if article.get("wikidata_id"):
        doc["wikidata_id"] = article["wikidata_id"]

    locations = []
    for entry in entries(metadata, "location"):
        label = entry.get("label") or entry.get("text")
        if label:
            locations.append(label)
    if locations:
        doc["location"] = locations

    years = set()
    for field in ("date", "start_date", "end_date"):
        for entry in entries(metadata, field):
            value = entry.get("value")
            if isinstance(value, dict) and value.get("time"):
                match = re.match(r"[+-]?(\d{1,4})-", value["time"])
                if match and match.group(1) != "0":
                    years.add(int(match.group(1)))
            elif entry.get("text"):
                years.update(int(y) for y in YEAR.findall(entry["text"]))
    if years:
        doc["year"] = sorted(years)

    for entry in entries(metadata, "deaths"):
        value = entry.get("value")
        number = None
        if isinstance(value, dict) and value.get("amount"):
            number = to_int(value["amount"])
        elif entry.get("text"):
            number = to_int(entry["text"])
        if number is not None:
            doc["deaths"] = number
            break
    return doc


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "data" / "final.jsonl"
    if "--clear" in sys.argv:
        post("/update?commit=true", {"delete": {"query": "*:*"}})
        print("Index cleared")
    batch, total = [], 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                batch.append(flatten(json.loads(line)))
            if len(batch) >= BATCH:
                post("/update", batch)
                total += len(batch)
                batch = []
                print(f"{total} indexed", end="\r")
    if batch:
        post("/update", batch)
        total += len(batch)
    post("/update?commit=true", {})
    print(f"Done: {total} documents indexed from {path}")


if __name__ == "__main__":
    main()
