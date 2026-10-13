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
    tags=['pri', 'crawler', 'wikipedia', 'blacklist'],
) as dag:

    # Tarefa para aplicar a Blacklist (marca as categorias com processed = -1)
    apply_blacklist_task = BashOperator(
        task_id='apply_blacklist_filter',
        bash_command='python /opt/airflow/src/blackList_filter.py',
    )

    # correr o Crawler (apenas processa o que restou pendente)
    run_crawler_task = BashOperator(
        task_id='run_wikipedia_crawler',
        bash_command='python /opt/airflow/src/crawler.py',
    )

    # Ordem de execução
    apply_blacklist_task >> run_crawler_task