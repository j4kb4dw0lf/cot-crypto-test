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

def get_all_libraries(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT library_id, name FROM Libraries ORDER BY name")
    return cursor.fetchall()

def main():
    if len(sys.argv) < 2:
        print("Usage: python core.py <command> [options]")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'scan-project':
        project_context_path = os.getcwd() 
        codeql_db_path = os.path.join(project_context_path, "codeql-db")

        if len(sys.argv) < 3:
            print("Usage: python core.py scan-project <library_id_1|any> [<library_id_2> ...]")
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                all_libraries = get_all_libraries(conn)
                if all_libraries:
                    print("\n**Available Library IDs:**")
                    for lib_id, lib_name in all_libraries:
                        print(f"  ID: {lib_id}, Name: {lib_name}")
                else:
                    print("\nNo libraries found in the database.")
            except sqlite3.Error as e:
                print(f"Error accessing database: {e}")
            finally:
                if conn:
                    conn.close()
            sys.exit(1)
        
        input_library_ids_str = sys.argv[2:]

        library_ids = []
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            
            if len(input_library_ids_str) == 1 and input_library_ids_str[0].lower() == 'any':
                log_message("Input 'any' detected. Fetching all library IDs from the database.")
                all_libraries = get_all_libraries(conn)
                if not all_libraries:
                    log_message("No libraries found in the database to scan.")
                    sys.exit(1)
                library_ids = [lib_id for lib_id, _ in all_libraries]
            else:
                for arg in input_library_ids_str:
                    try:
                        library_ids.append(int(arg))
                    except ValueError:
                        log_message(f"Error: Invalid Library ID '{arg}'. Please enter integers or 'any'.")
                        all_libraries = get_all_libraries(conn)
                        if all_libraries:
                            print("\n**Available Library IDs:**")
                            for lib_id, lib_name in all_libraries:
                                print(f"  ID: {lib_id}, Name: {lib_name}")
                        sys.exit(1)
            
            if not library_ids:
                log_message("No valid library IDs specified for scan. Exiting.")
                sys.exit(1)

            log_message(f"Starting CodeQL scan for library IDs: {', '.join(map(str, library_ids))} (Project: {project_context_path}) using DB: {codeql_db_path}")

            category_primitives = get_categories_and_primitives(conn, library_ids)
            
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
            
            if not generated_files:
                log_message("No QL files generated. Nothing to scan."); return
            
            outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs')
            os.makedirs(outputs_dir, exist_ok=True)
            
            bqrs_output_filename_suffix = '_'.join(map(str, library_ids)) if library_ids else 'all'
            bqrs_output_file = os.path.join(outputs_dir, f'output_{bqrs_output_filename_suffix}_CLI_scan.sarif')
            log_message(f"Running CodeQL queries, output to: {bqrs_output_file}")
            
            first_query = True
            for ql_file in generated_files:
                log_message(f"Running CodeQL query: {os.path.basename(ql_file)}")
                cmd = [
                    "codeql", "query", "run", 
                    f"--database={codeql_db_path}", 
                    ql_file, 
                    f"--output={bqrs_output_file}", 
                ]
                
                if not first_query:
                    cmd.append("--append")
                
                cmd.append(f"--sarif-category={os.path.basename(ql_file).replace('.ql', '')}")

                log_message(f"Executing: {' '.join(cmd)}")
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    
                    if result.stdout: log_message(f"CodeQL STDOUT:\n{result.stdout}")
                    if result.stderr: log_message(f"CodeQL STDERR:\n{result.stderr}")
                    log_message(f"Successfully ran query: {os.path.basename(ql_file)}")
                    first_query = False
                except subprocess.CalledProcessError as e:
                    log_message(f"Failed to run query: {os.path.basename(ql_file)}. Exit code: {e.returncode}")
                    log_message(f"CodeQL STDOUT:\n{e.stdout}")
                    log_message(f"CodeQL STDERR:\n{e.stderr}")
                except FileNotFoundError:
                    log_message("Error: 'codeql' command not found. Please ensure CodeQL CLI is in your PATH.")
                except Exception as e:
                    log_message(f"An unexpected error occurred during CodeQL query execution: {e}")

        except sqlite3.Error as e:
            log_message(f"Database error: {e}")
        except Exception as e:
            log_message(f"An unexpected error occurred in scan-project: {e}")
        finally:
            if conn:
                conn.close()
        log_message("CodeQL scan finished.")
        
    elif command == 'update-db':
        log_message("Creating or updating the database...")
        update()
        log_message("Database updated successfully.")

    elif command == 'report':
        log_message("Generating report...")            
        make_pdf_report(bqrs_path=='bqrs_file.json', output_pdf='report.pdf')                
        log_message("Report generated successfully.")

    else:
        print("Unknown command. Available commands: scan, generate, update-db, report")
        sys.exit(1)

if __name__ == "__main__":
    main()
