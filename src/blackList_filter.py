import sqlite3
import os

if os.path.exists("/opt/airflow"):
    DB_PATH = "/opt/airflow/data/crawler.db"  
elif os.path.exists("/app"):
    DB_PATH = "/app/data/crawler.db"          
else:
    DB_PATH = "data/crawler.db"

BLACKLIST_KEYWORDS = [
    "natural disaster", "earthquake", "volcano", "hurricane", "tsunami", 
    "flood", "geological", "war", "military", "conflict", "crime", 
    "murder", "sport", "music", "fiction", "biography", "politics", 
    "religion", "art", "film", "movie", "television", "weather", "protest", "combat", "non-combat", 
    "terrorism", "arson", "genocide"
]

def mark_blacklist_in_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    #  Marcar categorias que dão match direto com as palavras-chave da blacklist
    conditions = " OR ".join(["LOWER(name) LIKE ?" for _ in BLACKLIST_KEYWORDS])
    params = [f"%{kw}%" for kw in BLACKLIST_KEYWORDS]

    cursor.execute(f"""
        UPDATE categories 
        SET processed = -1 
        WHERE ({conditions}) AND processed != -1
    """, params)
    
    direct_updated = cursor.rowcount
    print(f"--- Marcadas {direct_updated} categorias por correspondência direta com a blacklist ---")

    #  exclusão em cascata pelas subcategorias usando a tabela category_edges
    total_propagated = 0
    while True:
        # Encontrar todas as subcategorias cujos pais já estão marcados como -1 mas que ainda estão ativas
        cursor.execute("""
            SELECT DISTINCT ce.child_name 
            FROM category_edges ce
            JOIN categories p ON ce.parent_name = p.name
            JOIN categories c ON ce.child_name = c.name
            WHERE p.processed = -1 AND c.processed != -1
        """)
        children = cursor.fetchall()
        
        if not children:
            break
        
        child_names = [row[0] for row in children]
        cursor.executemany("UPDATE categories SET processed = -1 WHERE name = ?", [(name,) for name in child_names])
        total_propagated += len(child_names)

    conn.commit()
    conn.close()

    print(f"\n[SUCESSO] Propagação em cascata concluída.")
    print(f"- Categorias diretas marcadas: {direct_updated}")
    print(f"- Subcategorias descendentes propagadas: {total_propagated}")
    print("O ramo completo de categorias indesejadas foi excluído com sucesso.")

if __name__ == "__main__":
    mark_blacklist_in_db()