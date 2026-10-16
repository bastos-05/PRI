from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'wikipedia_disasters_crawler_pipeline',
    default_args=default_args,
    description='Pipeline para recolha e filtragem de desastres e falhas de engenharia na Wikipedia',
    schedule=None,  
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['pri', 'crawler', 'wikipedia', 'embeddings'],
) as dag:

    pipeline_env = {
        "PIPELINE_CONFIG": "{{ dag_run.conf | default({}, true) | tojson }}"
    }

    # Tarefa para aplicar o filtro
    apply_filter_task = BashOperator(
        task_id='apply_filter_task',
        bash_command='python /opt/airflow/src/embeddings_filter.py',
        env=pipeline_env,
        append_env=True,
    )

    # Tarefa para dar download do modelo de embeddings
    download_model_task = BashOperator(
        task_id='download_model_task',
        bash_command='python /opt/airflow/src/download_model.py',
    )

    # correr o Crawler (apenas processa o que restou pendente)
    run_crawler_task = BashOperator(
        task_id='run_crawler',
        bash_command='python /opt/airflow/src/crawler.py',
        env=pipeline_env,
        append_env=True,
    )

    run_fetcher_task = BashOperator(
        task_id='run_fetcher',
        bash_command='python /opt/airflow/src/fetcher.py',
        env=pipeline_env,
        append_env=True,
    )

    prepare_fetch_task = BashOperator(
        task_id='run_prepare_fetcher',
        bash_command='python /opt/airflow/src/prepare_fetch.py',
        env=pipeline_env,
        append_env=True,
    )

    init_db_task = BashOperator(
        task_id='init_db',
        bash_command='python /opt/airflow/src/init_db.py',
    )

    # Ordem de execução
    init_db_task >> [download_model_task, run_crawler_task] >> prepare_fetch_task >> apply_filter_task >> run_fetcher_task