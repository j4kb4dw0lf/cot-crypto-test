import sys
import os
import sqlite3
from query_maker.query_maker import generate_query_no_args, generate_query_with_args
from environ_detector.environ_detector import scan_project
from db_creator_updater.db_creator_updater import update
from report_maker.report_maker import make_pdf_report
from utils.utils import log_message
import subprocess

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DB', 'crypto_primitives.db')
DB_PATH = os.path.normpath(DB_PATH)
print(f"DB_PATH: {DB_PATH}")
OUTPUT_DIR = 'generated_ql_queries'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_all_libraries(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT library_id, name FROM Libraries ORDER BY library_id")
    return cursor.fetchall()

def main():
    if len(sys.argv) < 2:
        print("Usage: python core.py <command> [options]")
        print("Commands: scan-project, update-db, report")
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

            query_noargs = generate_query_no_args(conn, library_ids)

            if not query_noargs:
                log_message("No QL file generated. Nothing to scan."); return
            
            filename = os.path.join(OUTPUT_DIR, "query_noargs.ql")
            with open(filename, 'w') as f:
                    f.write(query_noargs)
            log_message(f"Generated {filename}")

            
            outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs')
            os.makedirs(outputs_dir, exist_ok=True)
            
            bqrs_output_filename_suffix = '_'.join(map(str, library_ids)) if library_ids else 'all'
            bqrs_output_file = os.path.join(outputs_dir, f'problem_primitives-noargs-analysis.bqrs')
            log_message(f"Running CodeQL queries, output to: {bqrs_output_file}")
            
            log_message(f"Running CodeQL query: {os.path.basename(filename)}")
            cmd = [
                "codeql", "query", "run", 
                f"--database={codeql_db_path}", 
                filename, 
                f"--output={bqrs_output_file}", 
            ]

            log_message(f"Executing: {' '.join(cmd)}")

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                
                if result.stdout: log_message(f"CodeQL STDOUT:\n{result.stdout}")
                if result.stderr: log_message(f"CodeQL STDERR:\n{result.stderr}")
                log_message(f"Successfully ran query: {os.path.basename(filename)}")
            except subprocess.CalledProcessError as e:
                log_message(f"Failed to run query: {os.path.basename(filename)}. Exit code: {e.returncode}")
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
       
        outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs')
        if len(sys.argv) < 3:
            
            print("Usage: python report.py <filename>")
            print("List of bqrs in output folder:")
            for filename in os.listdir(outputs_dir):
                if filename.endswith('.bqrs'):
                    print(filename)
            sys.exit(1)   

        path_bqrs =   os.path.join(outputs_dir, sys.argv[2]) 
        log_message("Generating report...")   
        make_pdf_report(bqrs_path=path_bqrs)             
        log_message("Report generated successfully.")

    else:
        print("Unknown command. Available commands: scan-project, update-db, report")
        sys.exit(1)

if __name__ == "__main__":
    main()
