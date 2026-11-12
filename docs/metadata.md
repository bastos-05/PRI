# Metadados dos desastres

O DAG executa `fetcher → enrich_metadata → normalizer`. A nova etapa usa
`requests` e `mwparserfromhell`, que já constam de `requirements.txt`.

O fetcher guarda o `wikidata_id` obtido por `pageprops.wikibase_item`.
Para artigos antigos sem esse campo, o enriquecimento consulta os respetivos
`page_id` na Wikipedia. Não procura entidades pelo título.

## Ficheiros

- `raw.jsonl`: mantém o wikitext original.
- `enriched.jsonl`: artigos originais com `wikidata_id` e `metadata`.
- `final.jsonl`: texto normalizado, identificadores e os mesmos metadados.
- `metadata_cache.db`: cache das respostas bem-sucedidas das APIs, separada da base do crawler.

O enriquecimento processa lotes de 50 artigos. Escreve primeiro um ficheiro
temporário e só substitui `enriched.jsonl` quando termina com sucesso. Uma falha
da API faz falhar a tarefa, permitindo o retry do Airflow. A cache permite
reaproveitar pedidos já concluídos. O normalizador deve correr depois desta etapa.

## Campos

`metadata` contém `location`, `coordinates`, `date`, `start_date`, `end_date`,
`deaths`, `injured`, `missing`, `casualties` e `damages`.

Cada campo é `null` quando não há valor, ou uma lista de valores com a sua origem.
Não se substituem valores desconhecidos por zero nem se somam vítimas de categorias
diferentes. A cobertura por campo aparece nos logs da tarefa.

Os valores do Wikidata preservam o objeto original: precisão e calendário das datas,
quantidade, limites das estimativas e unidade/moeda. Incluem propriedade, identificador
da declaração, rank, qualificadores, referências e instante de consulta. Declarações
deprecated são ignoradas; as preferred têm prioridade sobre as normal.

Propriedades: local P276 (alternativas P131 e P17), coordenadas P625, data P585,
início/fim P580/P582, mortos P1120, feridos P1339 e custo dos danos P2630.
Os locais incluem o nome em inglês, com alternativa em português e, por fim, o QID.
Por precaução, P580/P582 só são usados se houver P585 ou um campo de data na
infobox: num artigo sobre uma infraestrutura, podem referir-se à sua existência.
Esta regra é conservadora e pode deixar intervalos por preencher.

Quando falta um campo, tenta-se a infobox. Estes valores mantêm texto, wikitext,
nome do template, parâmetro e revisão do artigo. Não são convertidos automaticamente
em números ou datas: podem conter intervalos, estimativas e templates. Danos da
infobox podem ser descritivos; P2630 representa especificamente danos monetários.

## Utilização

O enriquecimento está ativo por defeito no DAG. Para um corpus já recolhido,
executar as tarefas `enrich_metadata` e depois `normalizer`, sem repetir o crawler
nem usar o modo `fresh`.

Também podem ser executados dentro do ambiente Docker do projeto:

```bash
python /opt/airflow/src/enrich_metadata.py
python /opt/airflow/src/normalizer.py
```

Para voltar a consultar as APIs em vez de usar a cache, acrescentar à configuração
do DAG (a cache não expira automaticamente):

```json
{"metadata": {"refresh": true}}
```

Os testes offline usam respostas simuladas e não alteram o corpus:

```bash
python -m unittest discover -s tests -v
```
