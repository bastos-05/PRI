import os

API = "https://en.wikipedia.org/w/api.php"
if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"
else:
    DB_PATH = "/app/data/crawler.db"

def fetch():
    