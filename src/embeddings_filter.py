import sqlite3
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
# Multi-Otsu baseado (Otsu method usado em image segmentation mas acho que se aplica a qui por que a ideia é tentar separar em grupos)
from skimage.filters import threshold_multiotsu
from collections import defaultdict
import csv
import json
import os

if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"
    PROMOTED_PATH = "/opt/airflow/data/promoted_categories.csv"
    MODEL_PATH = Path("/opt/airflow/models/all-MiniLM-L6-v2")
else:
    DB_PATH = "/app/data/crawler.db"
    PROMOTED_PATH = "/app/data/promoted_categories.csv"
    MODEL_PATH = Path("/app/data/models/all-MiniLM-L6-v2")

TOPICS = [
    "Aviation accidents and disasters",
    "Industrial accidents and explosions",
    "Engineering failures and structural collapses",
    "Railway and maritime disasters",
    "Human-caused environmental disasters",
    "Technological and nuclear accidents"
]

# Tags para cada grupo
LOW = 0
MEDIUM = 1
HIGH = 2
MIN_PARENT_CHILD_SIM = 0.6
MIN_HIGH_PARENT_RATIO = 1.0

def get_filter_config():
    config = json.loads(os.environ.get("FILTER_CONFIG") or "{}")

    graph = config.get("graph") or {}

    return {
        "topics": config.get("topics") or TOPICS,
        "min_sim": graph.get(
            "min_parent_child_similarity",
            MIN_PARENT_CHILD_SIM
        ),
        "min_ratio": graph.get(
            "min_high_parent_ratio",
            MIN_HIGH_PARENT_RATIO
        )
    }

def build_graph():
    with sqlite3.connect(DB_PATH) as conn:
        edges = conn.execute("""
            SELECT parent_name, child_name
            FROM category_edges
        """).fetchall()

    parents = defaultdict(list)

    for parent, child in edges:
        parents[child].append(parent)

    return parents

def get_categories_group(scores, threshold_high, threshold_low):
    groups = np.where(
        scores >= threshold_high,
        HIGH,
        np.where(scores >= threshold_low, MEDIUM, LOW)
    )

    return groups

def promoted_csv(groups, new_groups, categories_graph, category_index, categories, scores):
    promoted = np.where(new_groups > groups)[0]

    with open(PROMOTED_PATH, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "category",
            "semantic_score",
            "original_group",
            "graph_group",
            "high_parents",
            "relevant"
        ])

        for i in promoted:
            high_parents = [
                parent
                for parent in categories_graph[categories[i]]
                if parent in category_index
                and groups[category_index[parent]] == HIGH
            ]

            writer.writerow([
                categories[i],
                float(scores[i]),
                int(groups[i]),
                int(new_groups[i]),
                "; ".join(high_parents),
                ""
            ])

def adjust_groups_with_graph(
    categories,
    scores,
    category_embeddings,
    threshold_high,
    threshold_low
):
    config = get_filter_config()

    min_parent_child_similarity = config["min_sim"]
    min_high_parent_ratio = config["min_ratio"]

    category_index = {
        name: i for i, name in enumerate(categories)
    }

    groups = get_categories_group(
        scores,
        threshold_high,
        threshold_low
    )

    new_groups = groups.copy()
    graph_categories = build_graph()

    labels = ["LOW", "MEDIUM", "HIGH"]
    promotions = []

    for category, i in category_index.items():

        if groups[i] == HIGH:
            continue

        parent_indices = [
            category_index[parent]
            for parent in graph_categories[category]
            if parent in category_index
        ]

        if not parent_indices:
            continue

        high_parent_indices = [
            j for j in parent_indices
            if groups[j] == HIGH
        ]

        if not high_parent_indices:
            continue

        high_parent_ratio = (len(high_parent_indices) / len(parent_indices))

        if high_parent_ratio < min_high_parent_ratio:
            continue

        parent_child_similarities = (category_embeddings[high_parent_indices] @ category_embeddings[i])

        valid_positions = np.where(parent_child_similarities >= min_parent_child_similarity)[0]

        if len(valid_positions) == 0:
            continue

        if groups[i] == MEDIUM:
            new_groups[i] = HIGH

        elif groups[i] == LOW:
            new_groups[i] = MEDIUM

        matching_parents = [
            (categories[high_parent_indices[pos]], float(parent_child_similarities[pos]))
            for pos in valid_positions
        ]

        promotions.append((i, matching_parents, high_parent_ratio))

    print("\nGraph filtering results")

    for value, label in enumerate(labels):
        before = np.count_nonzero(groups == value)
        after = np.count_nonzero(new_groups == value)

        print(
            f"{label}: {before} -> {after} "
            f"({after - before:+d})"
        )

    print(f"Promoted categories: {len(promotions)}")

    for i, matching_parents, ratio in promotions[:30]:
        print(f"\n{categories[i]}")
        print(f"\nSemantic score: {scores[i]:.3f}")
        print(f"\nGroup: {labels[groups[i]]} -> {labels[new_groups[i]]}")
        print(f"\nHIGH parent ratio: {ratio:.2f}")

        for parent, similarity in matching_parents:
            print(f"Parent: {parent}")
            print(f"(similarity: {similarity:.3f})")

    promoted_csv(groups, new_groups, graph_categories, category_index, categories, scores)

    return groups, new_groups

def automatic_percentiles(scores):
    # Encontrar dois tresholds automaticamente
    low, high = threshold_multiotsu(
        scores,
        classes=3
    )

    # Converter tresholds em percentis
    p_low = 100 * np.mean(scores < low)
    p_high = 100 * np.mean(scores < high)

    return (low, high), (p_low, p_high)

def start_filtering():

    config = get_filter_config()
    topics = config["topics"]
    
    if not MODEL_PATH.is_dir():
        raise FileNotFoundError(
            f"Modelo não encontrado em {MODEL_PATH}"
        )

    #all-MiniLM-L6-v2 transforma texto em vetores com 384 dimensoes
    model = SentenceTransformer(
        str(MODEL_PATH),
        local_files_only=True
    )

    with sqlite3.connect(DB_PATH) as conn:
        categories = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM categories WHERE processed = 1"
            )
        ]

    # Normaliza o nome das categorias
    texts = [
        name.removeprefix("Category:").replace("_", " ")
        for name in categories
    ]

    # MAtriz vetores das categorias
    category_embeddings = model.encode(
        texts,
        batch_size=128,
        normalize_embeddings=True, # normaliza os vetores
        show_progress_bar=True
    )

    # MAtriz vetores dos topicos
    topic_embeddings = model.encode(
        topics,
        normalize_embeddings=True # normaliza os vetores
    )

    # .T temos de transpor a matriz porque topic_embeddings é 6x384 e category_embeddings é 85667x384 e as colunas do primeiro devem ser iguais às linhas do segundo
    similarities = category_embeddings @ topic_embeddings.T # multiplicação matricial
    scores = similarities.max(axis=1)

    ranking = np.argsort(scores)[::-1]

    print(f"\nTop 30 categories (Total {len(scores)}):")
    for i in ranking[:30]:
        print(
            f"{scores[i]:.4f} | "
            f"{categories[i]} | "
            f"{topics[similarities[i].argmax()]}"
        )

    print(f"\nLast 30 categories (Total {len(scores)}):")
    for i in ranking[(len(scores)-30):]:
        print(
            f"{scores[i]:.4f} | "
            f"{categories[i]} | "
            f"{topics[similarities[i].argmax()]}"
        )

    print("Score statistics")

    for p in [0, 10, 25, 50, 75, 90, 95, 99, 100]:
        print(
            f"P{p}: {np.percentile(scores, p):.4f}"
        )
    
    (threshold_low, threshold_high), (p_low, p_high) = (
        automatic_percentiles(scores)
    )

    print(f"Lower threshold: {threshold_low:.4f} (P{p_low:.1f})")
    print(f"Upper threshold: {threshold_high:.4f} (P{p_high:.1f})")

    low = scores < threshold_low

    medium = (
        (scores >= threshold_low)
        & (scores < threshold_high)
    )

    high = scores >= threshold_high

    print("Low:", np.count_nonzero(low))
    print("Medium:", np.count_nonzero(medium))
    print("High:", np.count_nonzero(high))

    # testar tresholds
    for threshold in [0.4, 0.5, 0.6, 0.7, 0.8]:
        count = np.count_nonzero(scores >= threshold)
        print(f"Threshold {threshold:.1f}: {count} categories")

    groups, new_groups = adjust_groups_with_graph(categories, scores, category_embeddings, threshold_high, threshold_low)

if __name__ == "__main__":
    start_filtering()