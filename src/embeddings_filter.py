import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
# Multi-Otsu baseado (Otsu method usado em image segmentation mas acho que se aplica a qui por que a ideia é tentar separar em grupos)
from skimage.filters import threshold_multiotsu
from collections import defaultdict

DB_PATH = "data/crawler.db"

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

def score_by_group(scores, threshold_high, threshold_low):
    groups = np.where(
        scores >= threshold_high,
        HIGH,
        np.where(scores >= threshold_low, MEDIUM, LOW)
    )

    return groups

def adjust_groups_with_graph(categories, scores, threshold_high, threshold_low):
    
    category_index = {
        name: i for i, name in enumerate(categories)
    }

    groups = score_by_group(scores, threshold_high, threshold_low) # grafo grupos inicial e usado para comparação evitando uma cascata
    graph_groups = groups.copy()
    parents = build_graph()
    heuristica = 0.5

    for category, i in category_index.items():

        parent_indices = [
            category_index[parent]
            for parent in parents[category]
            if parent in category_index
        ]

        if not parent_indices:
            continue

        high_parents = sum(
            groups[j] == HIGH
            for j in parent_indices
        )

        total_parents = len(parent_indices)

        high_parent_ratio = high_parents / total_parents

        if groups[i] == MEDIUM and high_parent_ratio >= heuristica:
            graph_groups[i] = HIGH

        elif groups[i] == LOW and high_parent_ratio >= heuristica:
            graph_groups[i] = MEDIUM

    labels = ["LOW", "MEDIUM", "HIGH"]
    for value, label in enumerate(labels):

        before = np.count_nonzero(groups == value)
        after = np.count_nonzero(graph_groups == value)

        print(
            f"{label}: {before} -> {after} "
            f"({after - before:+d})"
        )

    promoted = np.where(graph_groups > groups)[0]

    for i in promoted[:30]:
        category = categories[i]

        high_parents = [
            parent
            for parent in parents[category]
            if parent in category_index
            and groups[category_index[parent]] == HIGH
        ]

        print(
            f"\n{category}"
            f"\n  Score: {scores[i]:.3f}"
            f"\n  Group: {labels[groups[i]]} -> {labels[graph_groups[i]]}"
            f"\n  HIGH parents: {high_parents}"
        )

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

    #all-MiniLM-L6-v2 transforma texto em vetores com 384 dimensoes
    model = SentenceTransformer(
        "models/all-MiniLM-L6-v2",
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
        TOPICS,
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
            f"{TOPICS[similarities[i].argmax()]}"
        )

    print(f"\nLast 30 categories (Total {len(scores)}):")
    for i in ranking[(len(scores)-30):]:
        print(
            f"{scores[i]:.4f} | "
            f"{categories[i]} | "
            f"{TOPICS[similarities[i].argmax()]}"
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

    adjust_groups_with_graph(categories, scores, threshold_high, threshold_low)