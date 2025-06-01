import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DB', 'crypto_primitives.db')
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Return CodeQl query to detect primitives that don't require further analysis on arguments.
# If necessary specify a list of primitive ids or categories ids to exclude from the query
def generate_query_no_args(conn, library_ids, excl_categories=None, excl_primitives=None):

    cursor = conn.cursor()

    # SQL query
    placeholders_libraries = ','.join('?' * len(library_ids))
    placeholders_excl_categories = ','.join('?' * (len(excl_categories) if excl_categories is not None else 0))
    placeholders_excl_primitives = ','.join('?' * (len(excl_primitives) if excl_primitives is not None else 0))
    query = f"""
    SELECT 
        p.name as PrimitiveName, 
        c.name as CategoryName,
        COALESCE(p.comment_alternative, c.comment_alternative_general) AS Alternative
    FROM Primitives p
    JOIN Primitive_categories pc ON p.primitive_id = pc.primitive_id
    JOIN Categories c ON pc.category_id = c.category_id
    WHERE p.library_id IN ({placeholders_libraries}) AND p.need_arg IS NULL AND 
    p.primitive_id NOT IN ({placeholders_excl_primitives}) AND c.category_id NOT IN ({placeholders_excl_categories});
    """

    cursor.execute(query,library_ids)

    # Fetch all results
    rows = cursor.fetchall()

    # Start building the CodeQL content

    codeql_lines = [
        "/**",
        "* @id cpp/primitives-noargs-analysis",
        "* @kind problem",
        "* @problem.severity warning",
        "* @name Crypto primitive",
        "* @description Find cryptographic primitives",
        "*",
        "*/",
        "\nimport cpp\n",
        "predicate getCategory(string name, string category, string alternative) {"
    ]

    # Generate the OR-ed predicate clauses
    for i, (primitive, category, alternative) in enumerate(rows):
        line = f'  (name = "{primitive}" and category = "{category}" and alternative = "{alternative}")'
        if i < len(rows) - 1:
            line += " or"
        codeql_lines.append(line)

    codeql_lines.append("}\n")


    # Add the main query block
    codeql_lines.extend([
        "from Function f, string name, string category, string alternative",
        "where name = f.getName() and getCategory(name, category, alternative)",
        'select f,  "\\nFunction name: "+ name + "\\n" + "Category: " +  category + "\\n" + "Alternative: " + alternative'
    ])

    codeql_query = "\n".join(codeql_lines)
    
    cursor.close()
    conn.close()

    return codeql_query


def generate_query_with_args(conn, library_ids):
    pass

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
        query_noargs = generate_query_no_args(conn, library_ids)
        print("-" * 60)
        if not query_noargs:
            print("Failed to generate query")
            print("Please ensure your database is populated and library IDs are correct.")
        else:
            filename = os.path.join(OUTPUT_DIR, "query_noargs.ql")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(query_noargs)
            print(f"Generated: {filename}")
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
