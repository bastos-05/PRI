#FROM python:3.11-slim
FROM apache/airflow:3.3.2

#WORKDIR /app

COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r requirements.txt

#COPY src/ ./src/
#COPY data/ ./data/
#COPY models/ ./models/

#CMD ["python", "src/main.py"]