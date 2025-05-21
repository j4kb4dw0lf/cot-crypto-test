import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DB', 'crypto_primitives.db')
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_categories_and_primitives(conn, library_id):
    """
    Returns a dict: {category_name: [primitive_name, ...], ...}
    Only includes primitives from the given library_id.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.name, p.name
        FROM Categories c
        JOIN Primitive_Categories pc ON c.category_id = pc.category_id
        JOIN Primitives p ON pc.primitive_id = p.primitive_id
        WHERE p.library_id = ?
        ORDER BY c.name, p.name
    """, (library_id,))
    category_primitives = {}
    for category, primitive in cursor.fetchall():
        category_primitives.setdefault(category, []).append(primitive)
    return category_primitives

def generate_codeql_query(category, primitives):
    primitive_checks = "\n    ".join([f'"{p}"' for p in primitives])
    query = f"""/**
 * CodeQL query for category: {category}
 * Finds all primitives in this category.
 */

from Function f
where f.getName() in [{primitive_checks}]
select f, "Primitive in category '{category}'"
"""
    return query

def main():
    if len(sys.argv) != 2:
        print("Usage: python query_maker.py <library_id>")
        sys.exit(1)
    library_id = sys.argv[1]
    conn = sqlite3.connect(DB_PATH)
    category_primitives = get_categories_and_primitives(conn, library_id)
    for category, primitives in category_primitives.items():
        if not primitives:
            continue
        query = generate_codeql_query(category, primitives)
        filename = os.path.join(OUTPUT_DIR, f"{category.replace(' ', '_')}.ql")
        with open(filename, 'w') as f:
            f.write(query)
        print(f"Generated {filename}")
    conn.close()

if __name__ == "__main__":
    main()