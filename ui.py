import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox, simpledialog
import os
import re
import threading
import subprocess
import queue
import sys
import inspect
import sqlite3
import traceback

_gui_script_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
CORE_SCRIPT_DIR = os.path.normpath(os.path.join(_gui_script_dir, 'cli_tool'))
if _gui_script_dir not in sys.path:
    sys.path.insert(0, _gui_script_dir)
cli_tool_path = os.path.join(_gui_script_dir, 'cli_tool')
if cli_tool_path not in sys.path:
    sys.path.insert(0, cli_tool_path)
try:
    from cli_tool.query_maker.query_maker import get_categories_and_primitives, generate_codeql_query
    from cli_tool.environ_detector.environ_detector import scan_project as cli_scan_environment
    from cli_tool.db_creator_updater.db_creator_updater import update as cli_update_db
    from cli_tool.report_maker.report_maker import make_pdf_report as cli_make_pdf_report
    cli_dependencies_found = True
except ImportError as e:
    print(f"CLI dependency import error: {e}")
    print(traceback.format_exc())
    messagebox.showerror("CLI Dependencies Missing",
                         "Could not import CLI tools. Please ensure the 'cli_tool' directory "
                         "is correctly structured and its modules are accessible. "
                         "Analysis actions will be disabled.")
    cli_dependencies_found = False
    def cli_scan_environment(path): raise NotImplementedError("environ_detector not found")
    def cli_update_db(): raise NotImplementedError("db_creator_updater not found")
    def get_categories_and_primitives(conn, lib_id): raise NotImplementedError("query_maker not found")
    def generate_codeql_query(cat, prim): raise NotImplementedError("query_maker not found")
    def cli_make_pdf_report(bqrs_path, output_pdf): raise NotImplementedError("report_maker not found")

CORE_DB_PATH = os.path.normpath(os.path.join(CORE_SCRIPT_DIR, 'DB', 'crypto_primitives.db'))
GENERATED_QL_OUTPUT_DIR = os.path.join(CORE_SCRIPT_DIR, 'generated_ql_queries')
os.makedirs(GENERATED_QL_OUTPUT_DIR, exist_ok=True)
PROJECT_ROOT_DIR = _gui_script_dir 
PROJECT_OUTPUTS_DIR = os.path.join(PROJECT_ROOT_DIR, 'outputs')
os.makedirs(PROJECT_OUTPUTS_DIR, exist_ok=True)

def get_all_libraries(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT library_id, name FROM Libraries ORDER BY name")
    return cursor.fetchall()

ORIGINAL_FOLDER_ICON_BASE64 = """
R0lGODlhEAAQAMQAAP///wAAAMLCwsbGxgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAACH5BAAAAAAALAAAAAAQABAAAAWjICCOZGmeqKqubOu+cCzPdFHMJkCCkYhMUQpFQZGpIQk
MowkK4UKBMHhGFQhNQBhMBYh0iQAFhAIBWUcOYMQiAq3ADs=
"""
ORIGINAL_FILE_ICON_BASE64 = """
R0lGODlhEAAQAMQAAABJSU5OTlBQUGZmZnZ2dmpqam5ubnZ2dn5+foqKiqCgoKWlpa6urri4uLu
7u729vebm5vz8/P///wAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAkAAB8ALAAAAAAQABAAAAVe
ICeOZGmeaKqubDsJgHEAgE4HAGaRkZB0CoOAgrZhgIBSDAFh+AgDJRBYUGBkRCUAYIQAkNww2j
CAAADs=
"""

COMMON_KEYWORDS = {
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if',
    'int', 'long', 'register', 'return', 'short', 'signed', 'sizeof', 'static',
    'struct', 'switch', 'typedef', 'union', 'unsigned', 'void', 'volatile', 'while',
    'asm', 'dynamic_cast', 'namespace', 'reinterpret_cast', 'try', 'bool',
    'explicit', 'new', 'static_cast', 'typeid', 'catch', 'false', 'operator',
    'template', 'typename', 'class', 'friend', 'private', 'this', 'throw',
    'true', 'virtual', 'delete', 'inline', 'public', 'protected', 'wchar_t',
    'using', 'constexpr', 'nullptr', 'decltype', 'noexcept', 'static_assert',
    'thread_local', 'alignas', 'alignof', 'char16_t', 'char32_t',
    'abstract', 'assert', 'boolean', 'byte', 'extends', 'final', 'finally', 'implements',
    'import', 'instanceof', 'interface', 'native', 'package', 'strictfp', 'super', 'synchronized',
    'throws', 'transient',
    'var', 'let', 'async', 'await', 'const', 'function', 'of',
    'and', 'as', 'async', 'await', 'del', 'elif', 'except', 'from', 'global',
    'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'with', 'yield',
}

SYNTAX_PATTERNS = {
    'comment': r'(//[^\n]*|/\*.*?\*/|#.*)',
    'preprocessor': r'(#\s*\w+)',
    'string': r'(".*?"|\'.*?\')',
    'keyword': r'\b(' + '|'.join(re.escape(k) for k in COMMON_KEYWORDS) + r')\b',
    'number': r'\b([0-9]+\.?[0-9]*f?|[0-9]*\.?[0-9]+f?|0x[0-9a-fA-F]+[ulL]*|[0-9]+[ulL]*)\b',
    'function_def': r'\b(def|function|class)\s+([a-zA-Z_]\w*)\b',
    'type': r'\b(int|void|char|long|float|double|bool|byte|short|string|String|array|Array|list|List|dict|Dict)\b',
}

SYNTAX_COLORS = {
    'comment': 'gray',
    'preprocessor': 'purple',
    'string': 'green',
    'keyword': 'blue',
    'number': 'orange',
    'function_def': 'dark red',
    'type': 'dark green',
    'default': 'black'
}

initial_root_window = None
folder_icon_tk = None
file_icon_tk = None

log_queue = queue.Queue()
current_opened_folder_path = None

def gui_log_message(log_text_widget, message):
    if log_text_widget and log_text_widget.winfo_exists():
        log_text_widget.config(state=tk.NORMAL)
        log_text_widget.insert(tk.END, str(message) + "\n")
        log_text_widget.see(tk.END)
        log_text_widget.config(state=tk.DISABLED)
    print(message)

def process_log_queue(log_text_widget):
    try:
        while True:
            message = log_queue.get_nowait()
            gui_log_message(log_text_widget, message)
    except queue.Empty:
        pass
    if log_text_widget and log_text_widget.winfo_exists():
        log_text_widget.after(100, lambda: process_log_queue(log_text_widget))

def run_in_thread(target_callable, *args, **kwargs):
    def threaded_callable():
        try:
            target_callable(*args, **kwargs)
        except Exception as e:
            log_queue.put(f"Error in thread for {target_callable.__name__ if hasattr(target_callable, '__name__') else 'unknown_task'}: {e}")
            log_queue.put(traceback.format_exc())
    thread = threading.Thread(target=threaded_callable, daemon=True)
    thread.start()

def apply_syntax_highlighting(text_widget, content, file_extension):
    text_widget.mark_set("range_start", "1.0")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", content)
    for tag_name in SYNTAX_COLORS.keys():
        text_widget.tag_remove(tag_name, "1.0", tk.END)
    text_widget.tag_add('default', "1.0", tk.END)
    for tag_name, color in SYNTAX_COLORS.items():
        text_widget.tag_configure(tag_name, foreground=color)
    patterns_to_apply = {}
    lang = file_extension.lower()
    if lang in ('.c', '.cpp', '.h', '.hpp'):
        patterns_to_apply = {k: v for k, v in SYNTAX_PATTERNS.items() if k not in ['function_def'] or k == 'type'}
    elif lang in ('.java', '.js', '.py', '.ts', '.jsx', '.tsx'):
        patterns_to_apply = {k: v for k, v in SYNTAX_PATTERNS.items() if k not in ['preprocessor']}
    else:
        patterns_to_apply = {k: v for k, v in SYNTAX_PATTERNS.items() if k not in ['preprocessor', 'function_def', 'type']}
    for tag_name, pattern in patterns_to_apply.items():
        flags = re.DOTALL if tag_name == 'comment' else 0
        if tag_name == 'function_def':
            for match in re.finditer(pattern, content, flags):
                if match.groups() and len(match.groups()) > 1:
                    name_start = match.start(2)
                    name_end = match.end(2)
                    start_index = "1.0 + %d chars" % name_start
                    end_index = "1.0 + %d chars" % name_end
                    text_widget.tag_remove('default', start_index, end_index)
                    text_widget.tag_add(tag_name, start_index, end_index)
        else:
            for match in re.finditer(pattern, content, flags):
                start_index = "1.0 + %d chars" % match.start()
                end_index = "1.0 + %d chars" % match.end()
                text_widget.tag_remove('default', start_index, end_index)
                text_widget.tag_add(tag_name, start_index, end_index)

def display_file_content_with_highlighting(item_path, text_preview_area):
    text_preview_area.config(state=tk.NORMAL)
    text_preview_area.delete(1.0, tk.END)
    try:
        if os.path.isdir(item_path):
            text_preview_area.insert(tk.END, f"Folder: {os.path.basename(item_path)}\nDouble-click a file to see its preview.")
        elif os.path.isfile(item_path):
            file_extension = os.path.splitext(item_path)[1]
            try:
                with open(item_path, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read(1024 * 1024)
                apply_syntax_highlighting(text_preview_area, content, file_extension)
                if len(content) == 1024 * 1024:
                    text_preview_area.insert(tk.END, "\n\n--- Preview truncated (1MB limit) ---", "comment")
            except Exception as e:
                text_preview_area.insert(tk.END, f"MISSING PREVIEW for {os.path.basename(item_path)}\n(Non-textual or unreadable file)\nError: {e}")
        else:
            text_preview_area.insert(tk.END, "Item not found or is not a file/directory.")
    except Exception as e:
        text_preview_area.insert(tk.END, f"An error occurred: {e}")
    finally:
        text_preview_area.config(state=tk.DISABLED)

def populate_tree(tree, parent_node_id, folder_path, force_refresh=False):
    global folder_icon_tk, file_icon_tk
    if parent_node_id:
        item_data = tree.item(parent_node_id)
        if item_data and 'values' in item_data and len(item_data['values']) == 3 and item_data['values'][2] == 'populated' and not force_refresh:
            return
    for child in tree.get_children(parent_node_id):
        tree.delete(child)
    try:
        if not os.path.exists(folder_path):
            log_queue.put(f"Error: Folder path does not exist: {folder_path}")
            tree.insert(parent_node_id, 'end', text=f"Error: Path '{os.path.basename(folder_path)}' not found", values=(folder_path, "error", "error"))
            return
        if not os.access(folder_path, os.R_OK):
            log_queue.put(f"Error: No read permission for folder: {folder_path}")
            tree.insert(parent_node_id, 'end', text=f"Error: No permission for '{os.path.basename(folder_path)}'", values=(folder_path, "error", "error"))
            return
        items = sorted(os.listdir(folder_path), key=lambda s: (not os.path.isdir(os.path.join(folder_path, s)), s.lower()))
        if not items and parent_node_id == '':
            tree.insert(parent_node_id, 'end', text="(Folder is empty)", values=(folder_path, "empty", "empty"))
            return
        for item_name in items:
            item_full_path = os.path.join(folder_path, item_name)
            item_values_dir = (item_full_path, 'folder', 'unpopulated')
            item_values_file = (item_full_path, 'file', 'file')
            try:
                if os.path.isdir(item_full_path):
                    node_id = tree.insert(parent_node_id, 'end', text=item_name, 
                                          image=folder_icon_tk if folder_icon_tk else '', 
                                          values=item_values_dir, open=False)
                    tree.insert(node_id, 'end', text="")
                elif os.path.isfile(item_full_path):
                    tree.insert(parent_node_id, 'end', text=item_name, 
                                image=file_icon_tk if file_icon_tk else '', 
                                values=item_values_file)
            except tk.TclError as item_insert_e:
                log_queue.put(f"TclError inserting item '{item_name}' (icon issue?): {item_insert_e}. Attempting without icon.")
                if os.path.isdir(item_full_path):
                    node_id = tree.insert(parent_node_id, 'end', text=item_name, values=item_values_dir, open=False)
                    tree.insert(node_id, 'end', text="")
                elif os.path.isfile(item_full_path):
                    tree.insert(parent_node_id, 'end', text=item_name, values=item_values_file)
            except Exception as item_e: 
                log_queue.put(f"General error inserting item '{item_name}': {item_e}")
                tree.insert(parent_node_id, 'end', text=f"{item_name} (Error)", values=(item_full_path, "error", "error"))
    except OSError as e:
        log_queue.put(f"OSError populating tree for '{folder_path}': {e}")
        tree.insert(parent_node_id, 'end', text=f"Error listing contents: {e.strerror}", values=(folder_path, "error", "error"))
    except Exception as general_e:
        log_queue.put(f"Unexpected error populating tree for '{folder_path}': {general_e}")
        log_queue.put(traceback.format_exc())
        tree.insert(parent_node_id, 'end', text=f"Unexpected error listing", values=(folder_path, "error", "error"))
    if parent_node_id:
        parent_item_data = tree.item(parent_node_id)
        if parent_item_data and 'values' in parent_item_data:
            parent_values = list(parent_item_data['values'])
            if len(parent_values) == 3:
                parent_values[2] = 'populated'
                tree.item(parent_node_id, values=tuple(parent_values))
            elif len(parent_values) == 2:
                tree.item(parent_node_id, values=(parent_values[0], parent_values[1], 'populated'))

def on_tree_select_changed(event, tree, text_preview_area):
    selected_item_id = tree.focus()
    if not selected_item_id or not tree.exists(selected_item_id):
        return
    item_data = tree.item(selected_item_id)
    if not item_data or 'values' not in item_data or not item_data['values']:
        return

def on_tree_double_click(event, tree, text_preview_area):
    region = tree.identify_region(event.x, event.y)
    item_id = tree.identify_row(event.y)
    if not item_id or region not in ('cell', 'tree'):
        return
    if not tree.exists(item_id):
        return
    item_values = tree.item(item_id, 'values')
    if item_values and len(item_values) >= 2 and item_values[1] == 'file':
        full_item_path = item_values[0]
        display_file_content_with_highlighting(full_item_path, text_preview_area)

def on_tree_open(event, tree):
    selected_item_id = tree.focus()
    if not selected_item_id or not tree.exists(selected_item_id):
        return
    item_values = tree.item(selected_item_id, 'values')
    if item_values and len(item_values) == 3 and item_values[1] == 'folder' and item_values[2] == 'unpopulated':
        folder_path = item_values[0]
        populate_tree(tree, selected_item_id, folder_path, force_refresh=False)

def action_scan_environment():
    global current_opened_folder_path
    if not cli_dependencies_found: log_queue.put("Action 'Scan Environment' disabled: CLI dependencies not found."); return
    path_to_scan = current_opened_folder_path
    if not path_to_scan:
        log_queue.put("No folder currently opened/selected for environment scan.")
        return
    log_queue.put(f"Scanning project environment at {path_to_scan}...")
    def task():
        try:
            environment_info = cli_scan_environment(path_to_scan)
            log_queue.put(f"Environment scan results: {environment_info}")
        except Exception as e:
            log_queue.put(f"Error during environment scan for {path_to_scan}: {e}")
    run_in_thread(task)

def action_update_db():
    if not cli_dependencies_found: log_queue.put("Action 'Update DB' disabled: CLI dependencies not found."); return
    log_queue.put("Creating or updating the database...")
    def task():
        try:
            cli_update_db()
            log_queue.put("Database updated successfully.")
        except Exception as e:
            log_queue.put(f"Error updating database: {e}")
    run_in_thread(task)

def action_scan_project_codeql(root_window):
    global current_opened_folder_path
    if not cli_dependencies_found:
        log_queue.put("Action 'Scan Project' disabled: CLI dependencies not found.")
        return
    project_context_path = current_opened_folder_path
    if not project_context_path:
        log_queue.put("No folder context for project scan. Please open a folder first.")
        return
    conn_db = None
    library_ids = []
    try:
        conn_db = sqlite3.connect(CORE_DB_PATH)
        all_libraries = get_all_libraries(conn_db)
        library_prompt = "Enter Library IDs (comma-separated, or 'any' for all):\n"
        if all_libraries:
            for lib_id, lib_name in all_libraries:
                library_prompt += f"  ID: {lib_id}, Name: {lib_name}\n"
        else:
            library_prompt += "No libraries found in the database.\n"
        library_ids_str = simpledialog.askstring("Library IDs", library_prompt, parent=root_window)
        if not library_ids_str:
            log_queue.put("Library IDs not provided. Scan cancelled."); return
        if library_ids_str.lower().strip() == 'any':
            log_queue.put("Input 'any' detected. Fetching all library IDs from the database.")
            if not all_libraries:
                log_queue.put("No libraries found in the database to scan. Scan cancelled.")
                return
            library_ids = [lib_id for lib_id, _ in all_libraries]
        else:
            try:
                library_ids = [int(lid.strip()) for lid in library_ids_str.split(',') if lid.strip()]
            except ValueError:
                log_queue.put("Error: Invalid Library ID format. Please enter comma-separated integers or 'any'. Scan cancelled."); return
            if not library_ids:
                log_queue.put("No valid Library IDs entered. Scan cancelled."); return
    except sqlite3.Error as e:
        log_queue.put(f"Error accessing database for library list: {e}")
        log_queue.put(traceback.format_exc())
        return
    except Exception as e:
        log_queue.put(f"Error during library ID input: {e}")
        log_queue.put(traceback.format_exc())
        return
    finally:
        if conn_db:
            conn_db.close()
    suggested_db_path = os.path.join(project_context_path, "codeql-db")
    codeql_db_path = filedialog.askdirectory(
        title=f"Select CodeQL DB for '{os.path.basename(project_context_path)}'",
        initialdir=suggested_db_path if os.path.isdir(suggested_db_path) and os.path.exists(suggested_db_path) else project_context_path,
        parent=root_window
    )
    if not codeql_db_path:
        log_queue.put("CodeQL database path not provided. Scan cancelled."); return
    log_queue.put(f"Starting CodeQL scan for library IDs: {', '.join(map(str, library_ids))} (Project: {project_context_path}) using DB: {codeql_db_path}")
    def task():
        conn_task = None
        try:
            conn_task = sqlite3.connect(CORE_DB_PATH)
            category_primitives = get_categories_and_primitives(conn_task, library_ids)
            if not category_primitives:
                log_queue.put(f"No categories or primitives found for library IDs: {', '.join(map(str, library_ids))}. No queries generated.")
                return
            generated_files = []
            generated_ids = []
            for category, primitives in category_primitives.items():
                if not primitives: continue
                query,kind,id = generate_codeql_query(category, primitives)
                os.makedirs(GENERATED_QL_OUTPUT_DIR, exist_ok=True) 
                filename = os.path.join(GENERATED_QL_OUTPUT_DIR, f"{category.replace(' ', '_')}.ql")
                with open(filename, 'w') as f:
                    f.write(query)
                log_queue.put(f"Generated QL query: {filename}")
                generated_files.append(filename)
                generated_ids.append(id)
            if not generated_files:
                log_queue.put("No QL files generated. Nothing to scan."); return
            os.makedirs(PROJECT_OUTPUTS_DIR, exist_ok=True)
            bqrs_output_filename_suffix = f'{kind}'
            bqrs_output_file = os.path.join(PROJECT_OUTPUTS_DIR, f'{bqrs_output_filename_suffix}_output.bqrs')
            log_queue.put(f"Running CodeQL queries, output to: {bqrs_output_file}")
            action_scan_project_codeql.last_bqrs_file = None 
            first_query = True 
            l = 0
            for ql_file in generated_files:
                bqrs_output_file_tmp = bqrs_output_file.replace('_output.bqrs', f'_{(os.path.basename(ql_file).replace(".ql", "")).replace("&","").replace(" ", "")}_output.bqrs')
                log_queue.put(f"Running CodeQL query: {os.path.basename(ql_file)}")
                cmd = [
                    "codeql", "query", "run", 
                    f"--database={codeql_db_path}", 
                    ql_file, 
                    f"--output={bqrs_output_file_tmp}", 
                ]
                log_queue.put(f"Executing: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
                if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
                if result.returncode == 0:
                    log_queue.put(f"Successfully ran query: {os.path.basename(ql_file)}")
                    if first_query:
                        action_scan_project_codeql.last_bqrs_file = bqrs_output_file_tmp
                        first_query = False
                else:
                    log_queue.put(f"Failed to run query: {os.path.basename(ql_file)}. Exit code: {result.returncode}")
            log_queue.put(f"CodeQL scan finished. bqrs output (if successful): {action_scan_project_codeql.last_bqrs_file or 'N/A'}")
        except FileNotFoundError:
            log_queue.put("Error: 'codeql' command not found. Please ensure CodeQL CLI is in your PATH.")
        except Exception as e:
            log_queue.put(f"Error during CodeQL project scan: {e}")
            log_queue.put(traceback.format_exc())
        finally:
            if conn_task:
                conn_task.close()
    run_in_thread(task)

def action_generate_report(root_window):
    if not cli_dependencies_found:
        log_queue.put("Action 'Generate Report' disabled: CLI dependencies not found.")
        return
    bqrs_file_to_report = getattr(action_scan_project_codeql, 'last_bqrs_file', None)
    initial_dir_bqrs = PROJECT_OUTPUTS_DIR if os.path.isdir(PROJECT_OUTPUTS_DIR) else "."
    target_directory = None
    if bqrs_file_to_report and os.path.exists(bqrs_file_to_report):
        target_directory = os.path.dirname(bqrs_file_to_report)
    else:
        selected_file = filedialog.askopenfilename(
            title="Select a .bqrs file to determine the report directory",
            initialdir=initial_dir_bqrs,
            filetypes=[("bqrs files", "*.bqrs"), ("JSON files", "*.json"), ("All files", "*.*")],
            parent=root_window
        )
        if selected_file:
            target_directory = os.path.dirname(selected_file)
        else:
            log_queue.put("No .bqrs file selected to determine the directory.")
            return
    if not target_directory or not os.path.isdir(target_directory):
        log_queue.put(f"Invalid directory determined for .bqrs files: {target_directory}")
        return
    bqrs_files_in_dir = [
        f for f in os.listdir(target_directory) if f.endswith(".bqrs") and os.path.isfile(os.path.join(target_directory, f))
    ]
    if not bqrs_files_in_dir:
        log_queue.put(f"No .bqrs files found in {target_directory}.")
        return
    log_queue.put(f"Found {len(bqrs_files_in_dir)} .bqrs files in {target_directory}. Preparing to generate reports...")
    def task_batch_report():
        for bqrs_filename in bqrs_files_in_dir:
            full_bqrs_path = os.path.join(target_directory, bqrs_filename)
            base_filename = os.path.splitext(bqrs_filename)[0]
            output_pdf_name = f"{base_filename}_report.pdf"
            output_pdf_path = os.path.join(PROJECT_OUTPUTS_DIR, output_pdf_name).replace('_output', '')
            log_queue.put(f"Generating PDF report from {full_bqrs_path} to {output_pdf_path}...")
            try:
                cli_make_pdf_report(bqrs_path=full_bqrs_path, output_pdf=output_pdf_path)
                log_queue.put(f"Report generation attempt finished for {output_pdf_path}")
                if os.path.exists(output_pdf_path) and os.path.getsize(output_pdf_path) > 0:
                    log_queue.put(f"Report successfully generated: {output_pdf_path}")
                else:
                    log_queue.put(f"Report file not found or is empty at {output_pdf_path}. Generation might have failed silently.")
            except Exception as e:
                log_queue.put(f"Error generating report for {bqrs_filename}: {e}")
                log_queue.put(traceback.format_exc())
        log_queue.put("Batch report generation complete.")
        if messagebox.askyesno("Reports Generated", f"All reports have been generated in {PROJECT_OUTPUTS_DIR}.\nDo you want to open the output directory?", parent=root_window):
            try:
                if sys.platform == "win32":
                    os.startfile(os.path.normpath(PROJECT_OUTPUTS_DIR))
                elif sys.platform == "darwin":
                    subprocess.call(["open", PROJECT_OUTPUTS_DIR])
                else:
                    subprocess.call(["xdg-open", PROJECT_OUTPUTS_DIR])
            except Exception as e_open:
                log_queue.put(f"Could not open output directory automatically: {e_open}")
    run_in_thread(task_batch_report)

def create_file_explorer_window(folder_path_to_explore, root_window_to_destroy):
    global initial_root_window, folder_icon_tk, file_icon_tk, current_opened_folder_path
    current_opened_folder_path = folder_path_to_explore
    if root_window_to_destroy:
        root_window_to_destroy.destroy()
    explorer_root = tk.Tk()
    explorer_root.title(f"File Explorer & Analyzer - {os.path.basename(folder_path_to_explore)}")
    explorer_root.geometry("1000x800")
    style = ttk.Style(explorer_root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        print("'clam' theme not available, using default.")
    try:
        folder_icon_tk = tk.PhotoImage(master=explorer_root, data=ORIGINAL_FOLDER_ICON_BASE64)
        file_icon_tk = tk.PhotoImage(master=explorer_root, data=ORIGINAL_FILE_ICON_BASE64)
        print("Successfully loaded custom icons from base64.")
    except tk.TclError as e: 
        print(f"Error loading custom icons from base64: {e}. Icons will be missing or default.")
        folder_icon_tk = None
        file_icon_tk = None
    actions_buttons_frame = ttk.Labelframe(explorer_root, text="Analysis Actions", padding=10)
    actions_buttons_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
    btn_scan_env = ttk.Button(actions_buttons_frame, text="Scan Environment", command=action_scan_environment)
    btn_scan_env.pack(side=tk.LEFT, padx=5, pady=5)
    btn_update_db = ttk.Button(actions_buttons_frame, text="Update DB", command=action_update_db)
    btn_update_db.pack(side=tk.LEFT, padx=5, pady=5)
    btn_scan_project = ttk.Button(actions_buttons_frame, text="Generate QL & Scan Project", command=lambda: action_scan_project_codeql(explorer_root))
    btn_scan_project.pack(side=tk.LEFT, padx=5, pady=5)
    btn_report = ttk.Button(actions_buttons_frame, text="Generate PDF Report", command=lambda: action_generate_report(explorer_root))
    btn_report.pack(side=tk.LEFT, padx=5, pady=5)
    main_v_pane = ttk.PanedWindow(explorer_root, orient=tk.VERTICAL)
    main_v_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
    explorer_h_pane = ttk.PanedWindow(main_v_pane, orient=tk.HORIZONTAL)
    main_v_pane.add(explorer_h_pane, weight=3)
    left_frame = ttk.Frame(explorer_h_pane, width=300)
    explorer_h_pane.add(left_frame, weight=1)
    tree_scrollbar_y = ttk.Scrollbar(left_frame, orient=tk.VERTICAL)
    tree_scrollbar_x = ttk.Scrollbar(left_frame, orient=tk.HORIZONTAL)
    file_tree = ttk.Treeview(left_frame, yscrollcommand=tree_scrollbar_y.set, xscrollcommand=tree_scrollbar_x.set, selectmode='browse')
    tree_scrollbar_y.config(command=file_tree.yview)
    tree_scrollbar_x.config(command=file_tree.xview)
    tree_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    tree_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
    file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    file_tree['columns'] = ("fullpath", "type", "status")
    file_tree.column("#0", width=250, minwidth=200, anchor='w')
    file_tree.heading("#0", text="Name", anchor='w')
    for col in ("fullpath", "type", "status"):
        file_tree.column(col, width=0, stretch=tk.NO)
    right_frame = ttk.Frame(explorer_h_pane)
    explorer_h_pane.add(right_frame, weight=3)
    text_preview_area = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10), relief="solid", borderwidth=1)
    text_preview_area.pack(fill=tk.BOTH, expand=True, padx=(0,5), pady=(0,5))
    text_preview_area.config(state=tk.NORMAL)
    text_preview_area.delete(1.0, tk.END)
    text_preview_area.insert(tk.END, "Double-click a file for preview. Select an item for context actions.")
    text_preview_area.config(state=tk.DISABLED)
    populate_tree(file_tree, '', folder_path_to_explore) 
    file_tree.bind("<<TreeviewSelect>>", lambda e: on_tree_select_changed(e, file_tree, text_preview_area))
    file_tree.bind("<Double-1>", lambda e: on_tree_double_click(e, file_tree, text_preview_area))
    file_tree.bind("<<TreeviewOpen>>", lambda e: on_tree_open(e, file_tree))
    log_display_frame = ttk.Labelframe(main_v_pane, text="Log Output", height=150, padding=10)
    main_v_pane.add(log_display_frame, weight=1)
    log_text_widget = scrolledtext.ScrolledText(log_display_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
    log_text_widget.pack(fill=tk.BOTH, expand=True)
    process_log_queue(log_text_widget)
    if not cli_dependencies_found:
        gui_log_message(log_text_widget, "Warning: CLI tool dependencies could not be imported. Analysis actions are disabled.")
        for btn in [btn_scan_env, btn_update_db, btn_scan_project, btn_report]:
            btn.config(state=tk.DISABLED)
    else:
        gui_log_message(log_text_widget, "CLI Analyzer Ready. Select an action.")
    explorer_root.protocol("WM_DELETE_WINDOW", lambda: on_explorer_close(explorer_root))
    explorer_root.mainloop()

def on_explorer_close(root):
    print("Explorer window closed.")
    root.destroy()

def select_folder_and_proceed():
    global initial_root_window
    folder_path = filedialog.askdirectory(parent=initial_root_window)
    if folder_path:
        create_file_explorer_window(folder_path, initial_root_window)
    else:
        print("No folder selected.")

def main_initial_window():
    global initial_root_window
    initial_root_window = tk.Tk()
    initial_root_window.title("Folder Analyzer Tool - Step 1")
    style = ttk.Style(initial_root_window)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    window_width = 400
    window_height = 200
    screen_width = initial_root_window.winfo_screenwidth()
    screen_height = initial_root_window.winfo_screenheight()
    center_x = int(screen_width / 2 - window_width / 2)
    center_y = int(screen_height / 2 - window_height / 2)
    initial_root_window.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    initial_root_window.focus_force()
    content_frame = ttk.Frame(initial_root_window, padding="20")
    content_frame.pack(expand=True, fill=tk.BOTH)
    label = ttk.Label(content_frame, text="Select a folder to explore and analyze.")
    label.pack(pady=10)
    select_button = ttk.Button(content_frame, text="Select Folder", command=select_folder_and_proceed)
    select_button.pack(pady=10)
    initial_root_window.mainloop()

if __name__ == "__main__":
    main_initial_window()
