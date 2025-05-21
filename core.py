import sys
import os
import sqlite3
from query_maker.query_maker import get_categories_and_primitives, generate_codeql_query
from environ_detector.environ_detector import scan_project
from db_creator_updater.db_creator_updater import update
from report_maker.report_maker import make_pdf_report
from utils.utils import log_message

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DB', 'crypto_primitives.db')
DB_PATH = os.path.normpath(DB_PATH)
print(f"DB_PATH: {DB_PATH}")
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: python core.py <command> [options]")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'scan-environment':
        path = sys.argv[2] if len(sys.argv) > 2 else '.'
        log_message(f"Scanning project at {path}...")
        environment_info = scan_project(path)
        log_message(f"Scan results: {environment_info}")

    elif command == 'scan-project':
        if len(sys.argv) != 3:
            print("Usage: python core.py scan-project <library_id>")
            sys.exit(1)
        library_id = sys.argv[2]
        conn = sqlite3.connect(DB_PATH)
        category_primitives = get_categories_and_primitives(conn, library_id)
        generated_files = []
        for category, primitives in category_primitives.items():
            if not primitives:
                continue
            query = generate_codeql_query(category, primitives)
            filename = os.path.join(OUTPUT_DIR, f"{category.replace(' ', '_')}.ql")
            with open(filename, 'w') as f:
                f.write(query)
            log_message(f"Generated {filename}")
            generated_files.append(filename)
        conn.close()

        # Launch CodeQL queries and save output to ../outputs/output.serif
        output_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs'))
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'output.sarif')
        for ql_file in generated_files:
            log_message(f"Running CodeQL query: {ql_file}")
            cmd = f"codeql query run --database=./codeql-db {ql_file} --output={output_file}"
            exit_code = os.system(cmd)
            if exit_code != 0:
                log_message(f"Failed to run query: {ql_file}")
            else:
                log_message(f"Successfully ran query: {ql_file} (output: {output_file})")

    elif command == 'update-db':
        log_message("Creating or updating the database...")
        update()
        log_message("Database updated successfully.")

    elif command == 'report':
        log_message("Generating report...")            
        make_pdf_report(sarif_path='sarif_file.json', output_pdf='report.pdf')                
        log_message("Report generated successfully.")


    else:
        print("Unknown command. Available commands: scan, generate, update-db, report")
        sys.exit(1)

if __name__ == "__main__":
    main()