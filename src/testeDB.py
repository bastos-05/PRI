import sqlite3

for path in ["data/crawler.db", "data/crawler.backup.db"]:
    with sqlite3.connect(path) as conn:
        print(path)

        for row in conn.execute("""
            SELECT processed, COUNT(*)
            FROM categories
            GROUP BY processed
        """):
            print(row)