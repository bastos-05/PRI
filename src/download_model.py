from pathlib import Path
from sentence_transformers import SentenceTransformer
import shutil
import os

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
if os.path.exists("/opt/airflow"):
    MODEL_PATH = Path("/opt/airflow/models/all-MiniLM-L6-v2")
else:
    MODEL_PATH = Path("/app/models/all-MiniLM-L6-v2")

TEMP_PATH = MODEL_PATH.with_name(MODEL_PATH.name + ".tmp")

def download_model():
    
    if MODEL_PATH.exists():
        try:
            SentenceTransformer(
                str(MODEL_PATH),
                local_files_only=True,
                device="cpu"
            )
            print("[MODEL] Already available locally")
            return
        except Exception:
            print("[MODEL] Existing model is invalid")

    if TEMP_PATH.exists():
        shutil.rmtree(TEMP_PATH)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("[MODEL] Downloading...", flush=True)

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    model.save(str(TEMP_PATH))

    SentenceTransformer(
        str(TEMP_PATH),
        local_files_only=True,
        device="cpu"
    )

    if MODEL_PATH.exists():
        shutil.rmtree(MODEL_PATH)

    TEMP_PATH.rename(MODEL_PATH)

    print("[MODEL] Ready", flush=True)

if __name__ == "__main__":
    download_model()