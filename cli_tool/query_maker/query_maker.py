import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DB', 'crypto_primitives.db')
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_categories_and_primitives(conn, library_ids):
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(library_ids))
    sql_query = f"""
        SELECT 
            c.name AS category_name, 
            p.name AS primitive_name
        FROM 
            Categories c
        JOIN 
            Primitive_Categories pc ON c.category_id = pc.category_id
        JOIN 
            Primitives p ON pc.primitive_id = p.primitive_id
        WHERE 
            p.library_id IN ({placeholders})
        ORDER BY 
            c.name, p.name
    """
    cursor.execute(sql_query, library_ids)
    category_primitives = {}
    for row in cursor.fetchall():
        category = row[0]
        primitive = row[1]
        category_primitives.setdefault(category, []).append(primitive)
    return category_primitives

def generate_codeql_query(category, primitives):
    query_id_slug = category.replace('&','').replace(' ', '')
    query_id = f"{query_id_slug}" 
    primitive_checks = "\n    ".join([f'"{p}",' for p in primitives])
    query_content = f"""/**
 * @id cpp/{query_id}
 * @kind problem
 * @problem.severity warning
 * @name Crypto Primitive: {category}
 * @description Finds all cryptographic primitives related to the '{category}' category.
 *
 * This query identifies calls to known cryptographic primitive functions
 * belonging to the '{category}' category, as defined in the database.
 */

import cpp
 
from Function f
where f.getName() in [{primitive_checks}]
select f, "Primitive in category {category}, name: " + f.getName() + ", params: " + f.getParameterString()
"""
    query_kind = "problem"
    return query_content, query_kind, query_id 

def main():
    if len(sys.argv) < 2:
        print("Usage: python query_maker.py <library_id_1> [<library_id_2> ...]")
        print("Example: python query_maker.py 1 3")
        print("  <library_id> refers to the ID of a specific cryptographic library in your database.")
        sys.exit(1)
    try:
        library_ids = [int(arg) for arg in sys.argv[1:]]
    except ValueError:
        print("Error: All provided library IDs must be valid integers.")
        sys.exit(1)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row 
        category_primitives = get_categories_and_primitives(conn, library_ids)
        print("\n--- Generated CodeQL Queries and Metadata ---")
        print("For each generated .ql file, note the 'Kind' and 'ID'.")
        print("You will need these values when interpreting the BQRS results with 'codeql bqrs interpret'.")
        print("-" * 60)
        if not category_primitives:
            print("No categories or primitives found for the given library IDs in the database.")
            print("Please ensure your database is populated and library IDs are correct.")
        else:
            for category, primitives in category_primitives.items():
                if not primitives:
                    continue
                query_content, ql_kind, ql_id = generate_codeql_query(category, primitives)
                filename = os.path.join(OUTPUT_DIR, f"{category.replace(' ', '_')}.ql")
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(query_content)
                print(f"Generated: {filename}")
                print(f"  Kind: {ql_kind}")
                print(f"  ID: {ql_id}")
                print("-" * 60)
    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
