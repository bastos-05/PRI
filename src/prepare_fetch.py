import json
import os
import sqlite3
from pathlib import Path

if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"
    RAW_PATH = Path("/opt/airflow/data/raw.jsonl")

else:
    DB_PATH = "/app/data/crawler.db"
    RAW_PATH = Path("/app/data/raw.jsonl")

def get_mode():
    config = json.loads(os.environ.get("PIPELINE_CONFIG") or "{}")
    mode = config.get("mode", "auto")

    if mode not in ("auto", "fresh", "resume"):
        raise ValueError(f"Invalid mode: {mode}")

    if mode == "auto":
        with sqlite3.connect(DB_PATH) as conn:
            has_fetched_already = conn.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM filtered_articles
                    WHERE status = 'FETCHED'
                )
            """).fetchone()[0]

        if has_fetched_already:
            return "resume" 
        else:
            return "fresh"

    return mode

def prepare_fetch():
    mode = get_mode()

    if mode == "resume":
        if not RAW_PATH.exists():
            with sqlite3.connect(DB_PATH) as conn:
                count = conn.execute("""
                    SELECT COUNT(*)
                    FROM filtered_articles
                    WHERE status IN ('FETCHED', 'NORMALIZED')
                """).fetchone()[0]

            if count:
                raise RuntimeError(
                    "Cannot resume: raw.jsonl missing but articles "
                    "are already marked as fetched/normalized"
                )

            RAW_PATH.touch()

        print("[RESUME] Existing preparation")
        return

    print("[FRESH] Resetting article corpus")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM filtered_articles")

    RAW_PATH.write_text("", encoding="utf-8")

    print("[FRESH] Reset completed")

if __name__ == "__main__":
    prepare_fetch()