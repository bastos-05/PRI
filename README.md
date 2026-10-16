# PRI

### REPORT
DOCX: https://docs.google.com/document/d/1EBQbp5Je-pxeZXom9qd25TjW5JFVIDhudJZfHjO6MJQ/edit?usp=sharing
<br>
LATEX: https://www.overleaf.com/1278562841tmsyzbzykhwz#cb4f79

### Templates
https://www.acm.org/publications/authors/submissions

## How to Run

The data preparation pipeline is orchestrated using **Apache Airflow** and runs inside Docker containers.

### 1. Start the pipeline

Start the services using Docker Compose:

```bash
docker compose up -d --build
```

Access the Airflow web interface at the address configured in `docker-compose.yml`.

### 2. Trigger the DAG

In the Airflow interface, locate the data preparation DAG and select **Trigger DAG**.

Use the following configuration, which corresponds to the final dataset used for **Milestone 1**:

```json
{
  "mode": "fresh",
  "crawler": {
    "workers": 3,
    "max_depth": 8
  },
  "filter": {
    "topics": [
      "Industrial accidents and disasters involving factories, chemical plants and industrial facilities",
      "Structural collapses and engineering failures involving bridges, buildings and dams",
      "Nuclear accidents, radioactive contamination and radiation disasters",
      "Aviation accidents, aircraft crashes and fatal air disasters",
      "Railway accidents, train collisions and derailments",
      "Maritime disasters, shipwrecks, sinkings and maritime accidents",
      "Mining disasters, mine collapses and underground explosions",
      "Oil spills, pipeline failures and major environmental contamination caused by human activity",
      "Fires, explosions and catastrophic accidents caused by human activity",
      "Infrastructure failures and disasters caused or worsened by engineering defects or human negligence"
    ],
    "graph": {
      "min_parent_child_similarity": 0.6,
      "min_high_parent_ratio": 1.0
    }
  },
  "fetch": {
    "workers": 3,
    "batch_size": 20
  }
}
```

### 3. Execution modes

The `mode` parameter controls how existing data is handled:

- **`fresh`** — Rebuilds the