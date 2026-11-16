import json
import re
import sys
import time
import requests
from pathlib import Path

CORE = "http://localhost:8983/solr/pri"
YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")

def post(path, payload):
    response = requests.post(CORE + path, json=payload, timeout=600)

    response.raise_for_status()
    return response.json()


# Logs meaning here https://solr.apache.org/guide/solr/latest/query-guide/logs.html
def update_documents(documents):
    started = time.perf_counter()
    payload = json.dumps(documents).encode()
    size_mib = len(payload) / (1024 * 1024)

    print(f"Sending {len(documents)} documents | Payload: {size_mib:.2f} MiB")
    try:
        response = post("/update", documents)
    except Exception as error:
        elapsed = time.perf_counter() - started
        print(f"FAILED after {elapsed:.2f}s | {error}")
        raise

    elapsed = time.perf_counter() - started
    rate = len(documents) / elapsed if elapsed else 0.0
    qtime = response.get("responseHeader", {}).get("QTime")
    solr_time = f"{qtime} ms" if qtime is not None else "n/a"

    print(f"Done | Documents: {len(documents)}")
    print(f"Time: {elapsed:.2f}s | Rate: {rate:.1f} docs/s")
    print(f"Solr QTime (Query Time): {solr_time}")


def entries(metadata, field):
    return (metadata or {}).get(field) or []

def to_int(text):
    if not isinstance(text, str):
        return None

    text = text.strip()

    if not re.fullmatch(r"\+?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", text):
        return None

    return int(text.replace(",", ""))


def metadata_text(entry):
    if entry.get("text"):
        return entry["text"]

    value = entry.get("value") or {}
    if value.get("time"):
        date = value["time"].lstrip("+").split("T")[0]
        year, month, day = date.rsplit("-", 2)
        precision = value.get("precision")
        if precision == 9:
            return year
        if precision == 10:
            return f"{year}-{month}"
        if precision == 11:
            return date

        return f"{value['time']} (Wikidata precision: {precision})"

    if value.get("amount") is not None:
        text = value["amount"]
        if value.get("lowerBound") is not None or value.get("upperBound") is not None:
            text += f" [bounds: {value.get('lowerBound')} to {value.get('upperBound')}]"
        unit = value.get("unit")
        if unit and unit != "1":
            text += f" {unit.rsplit('/', 1)[-1]}"
        return text

    return None


def flatten(article):
    metadata = article.get("metadata") or {}
    doc = {
        "id": str(article["page_id"]),
        "page_id": article["page_id"],
        "revision_id": article["revision_id"],
        "title": article["title"],
        "text": article["text"],
        "wikidata_id": article.get("wikidata_id")
    }

    locations = []
    location_ids = []
    for entry in entries(metadata, "location"):
        label = entry.get("label") or entry.get("text")
        if label:
            locations.append(label)
        value = entry.get("value") or {}
        if value.get("id"):
            location_ids.append(value["id"])
    doc["location"] = locations
    doc["location_id"] = location_ids

    coordinates = []
    for entry in entries(metadata, "coordinates"):
        value = entry.get("value") or {}
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if value.get("globe") != "http://www.wikidata.org/entity/Q2":
            continue
        if latitude is not None and longitude is not None:
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                coordinates.append(f"{latitude},{longitude}")
    doc["coordinates"] = coordinates

    years = set()
    for field in ("date", "start_date", "end_date"):
        dates = []
        field_years = set()
        for entry in entries(metadata, field):
            text = metadata_text(entry)
            if text:
                dates.append(text)
            value = entry.get("value")
            if isinstance(value, dict) and value.get("time"):
                match = re.match(r"([+-]?\d+)-", value["time"])
                if match and value.get("precision", 0) >= 9:
                    field_years.add(int(match.group(1)))
            elif entry.get("text"):
                field_years.update(int(y) for y in YEAR.findall(entry["text"]))
        doc[field] = dates
        doc[f"{field}_year"] = sorted(field_years)
        years.update(field_years)
    if years:
        doc["year"] = sorted(years)

    for field in ("deaths", "injured", "missing", "casualties", "damages"):
        texts = []
        for entry in entries(metadata, field):
            text = metadata_text(entry)
            if text:
                texts.append(text)
        text_field = f"{field}_text" if field in ("deaths", "injured", "missing") else field
        doc[text_field] = texts

    for field in ("deaths", "injured", "missing"):
        number = None
        for entry in entries(metadata, field):
            value = entry.get("value") or {}

            if entry.get("qualifiers") or value.get("lowerBound") is not None or value.get("upperBound") is not None:
                continue
            number = to_int(value.get("amount") or entry.get("text"))
            if number is not None:
                break
        doc[field] = number
    return doc


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        path = Path(__file__).resolve().parent.parent / "data" / "final.jsonl"
    else:
        path = Path(args[0])

    print(f"Source: {path}")

    started = time.perf_counter()

    if "--clear" in sys.argv:
        post("/update?commit=true", {"delete": {"query": "*:*"}})
        print("Index cleared")
        return

    documents = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                documents.append(flatten(json.loads(line)))

    update_documents(documents)

    print("Committing documents...")
    commit_started = time.perf_counter()
    post("/update?commit=true", {})
    print(f"OK | Time: {time.perf_counter() - commit_started:.2f}s", flush=True)

    elapsed = time.perf_counter() - started
    rate = len(documents) / elapsed if elapsed else 0.0

    print(f"Documents: {len(documents)}")
    print(f"Total time: {elapsed:.2f}s | Average: {rate:.1f} docs/s | Source: {path}")


if __name__ == "__main__":
    main()
