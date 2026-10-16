import os
import re
import json
import sqlite3
import mwparserfromhell
import time
from pathlib import Path

if os.path.exists("/opt/airflow"):
    DATA_PATH = Path("/opt/airflow/data")
else:
    DATA_PATH = Path("/app/data")

RAW_PATH = DATA_PATH / "raw.jsonl"
FINAL_PATH = DATA_PATH / "final.jsonl"
DB_PATH = DATA_PATH / "crawler.db"

def preserve_templates(parsed):
    for template in parsed.filter_templates(recursive=True):
        name = str(template.name).strip().lower().replace("_", " ")

        params = [
            str(param.value).strip()
            for param in template.params
            if not param.showkey
        ]

        replacement = None

        if name in ("nowrap", "nobr", "small"):
            replacement = " ".join(params)

        elif name == "lang" and len(params) >= 2:
            replacement = params[1]

        elif name in ("convert", "cvt") and len(params) >= 2:
            replacement = f"{params[0]} {params[1]}"

        if replacement is not None:
            try:
                parsed.replace(template, replacement)
            except ValueError:
                pass

    return parsed


def normalize_wikitext(wikitext):
    parsed = mwparserfromhell.parse(wikitext)

    parsed = preserve_templates(parsed)

    for tag in parsed.filter_tags(recursive=True):
        if str(tag.tag).lower().strip() == "ref":
            try:
                parsed.remove(tag)
            except ValueError:
                pass

    text = parsed.strip_code(
        normalize=True,
        collapse=False,
        keep_template_params=False
    )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def normalize():
    processed = 0
    duplicates = 0
    seen = set()

    start = time.perf_counter()

    FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)

    with RAW_PATH.open("r", encoding="utf-8") as source, \
        FINAL_PATH.open("w", encoding="utf-8") as destination:
        
        for line in source:
            if not line.strip():
                continue

            article = json.loads(line)

            page_id = article.get("page_id")

            if page_id is None:
                continue

            # Evitar duplicados
            if page_id in seen:
                duplicates += 1
                continue

            wikitext = article.get("wikitext")

            if not isinstance(wikitext, str):
                continue

            text = normalize_wikitext(wikitext)

            if not text:
                continue

            document = {
                "page_id": page_id,
                "title": article["title"],
                "revision_id": article["revision_id"],
                "text": text
            }

            destination.write(
                json.dumps(document, ensure_ascii=False) + "\n"
            )

            seen.add(page_id)
            processed += 1

    print(f"[NORMALIZED] {processed} articles")
    print(f"[DUPLICATES] {duplicates} articles")

if __name__ == "__main__":
    normalize()