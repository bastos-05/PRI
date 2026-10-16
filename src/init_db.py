import os
import sqlite3

if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"
else:
    DB_PATH = "/app/data/crawler.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:

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

            CREATE TABLE IF NOT EXISTS filtered_articles (
                page_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK(status IN ('PENDING', 'FETCHED', 'NORMALIZED', 'SKIPPED')),
                FOREIGN KEY (page_id) REFERENCES articles(page_id)
            );
        """)

if __name__ == "__main__":
    init_db()