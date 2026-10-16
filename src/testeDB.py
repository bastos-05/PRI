import sqlite3

def testeDB():
    with sqlite3.connect("data/crawler.db") as conn:
        for row in conn.execute("""
            SELECT processed, COUNT(*)
            FROM categories
            GROUP BY processed
        """):
            print(row)

        conn.execute("DELETE FROM filtered_articles")

if __name__ == "__main__":
    main()