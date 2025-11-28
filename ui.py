# ============================================================================
# IMPORTS AND DEPENDENCIES
# ============================================================================
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
import shutil
import csv
import json
import urllib.parse

# ============================================================================
# PATH CONFIGURATION AND SETUP
# ============================================================================
_gui_script_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
CORE_SCRIPT_DIR = os.path.normpath(os.path.join(_gui_script_dir, 'cli_tool'))
if _gui_script_dir not in sys.path:
    sys.path.insert(0, _gui_script_dir)
cli_tool_path = os.path.join(_gui_script_dir, 'cli_tool')
if cli_tool_path not in sys.path:
    sys.path.insert(0, cli_tool_path)
# ============================================================================
# CLI TOOLS IMPORT - Analysis backend functions
# ============================================================================
try:
    from cli_tool.query_maker.query_maker import generate_query_no_args, generate_query_with_args, generate_query_macros, generate_query_regexp_calls_and_args, generate_query_regexp_macro
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
    def generate_query_no_args(cat, prim): raise NotImplementedError("query_maker not found")
    def generate_query_with_args(cat, prim): raise NotImplementedError("query_maker not found")
    def generate_query_macros(): raise NotImplementedError("query_maker not found")
    def generate_query_regexp_calls_and_args(): raise NotImplementedError("query_maker not found")
    def generate_query_regexp_macro(): raise NotImplementedError("query_maker not found")
    def cli_make_pdf_report(bqrs_path, output_pdf): raise NotImplementedError("report_maker not found")

# ============================================================================
# UI UTILITIES IMPORT - Custom UI components
# ============================================================================
from ui_utils import ask_string_with_paste

# ============================================================================
# GLOBAL PATHS AND DIRECTORIES
# ============================================================================
CORE_DB_PATH = os.path.normpath(os.path.join(CORE_SCRIPT_DIR, 'DB', 'crypto_primitives.db'))
GENERATED_QL_OUTPUT_DIR = os.path.join(CORE_SCRIPT_DIR, 'generated_ql_queries')
os.makedirs(GENERATED_QL_OUTPUT_DIR, exist_ok=True)
PROJECT_ROOT_DIR = _gui_script_dir
PROJECT_OUTPUTS_DIR = os.path.join(PROJECT_ROOT_DIR, 'outputs')
os.makedirs(PROJECT_OUTPUTS_DIR, exist_ok=True)

# ============================================================================
# DATABASE HELPER FUNCTIONS
# ============================================================================
def get_all_libraries(conn):
    """Retrieve all library IDs and names from the database"""
    cursor = conn.cursor()
    cursor.execute("SELECT library_id, name FROM Libraries ORDER BY library_id")
    return cursor.fetchall()

# ============================================================================
# GUI ICONS - Base64 encoded images for file tree
# ============================================================================
ORIGINAL_FOLDER_ICON_BASE64 = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAdgAAAHYBTnsmCAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAADDSURBVDiNpdIxTsNAEIXhL3YXiTZNyhwiDQ00SOlzAw5CkRNwi3QpMLRYUFJRcYEQFHdBFEgQUxhLK2NgF0YaafVWeu+f0fDPGmCEQ+SB/oSbWJMH1D19HktQ//B/jaqjvWOJVSv0pf/Wu+8InnH6mZJFTHDfJThDmUBSdQ1OEke5CzEfMYnADqsIDS4wSzS4DEeY4yUBf4usJXjVbH6YkH6FfWtQ4jgRv2gfCxxhk4C/xgHNIeWYYhyZ/IZbX0/8b/UBywZkP+3SLOIAAAAASUVORK5CYII=/S5xBEMbxz5yCKGk0XWxtbMTisLNR7FKlSHWQdOlshZAyRVrLEAg2ltr6oxHsxXBiEYj5BwJRSNIoMhZ68hIxuVVyb8AbGHjngXnnu8PuMhuZqU5r1Fr9fwAY/F2IiHG8wFQX+Z8y8929CDLz2jGGE2SBL1b/UepR3YQRMYfnf2Gex0QlPsfTzNy8SwMiM0VEYPaqA3+yxA6W8bKi/8RhQd1jrGAdmvis+5ZvYwS7BTm3+VJgDc8K6OE93qBVkPMEC5iuaF8HsKr8ODbxCN8LcnbxGqcu9xGMcv82lngbQ9jqaHH10UtrYRgfqOcmnMeXTlAHQOPWoA7rA/QB+gAPHuC8boCNOgGO8PbGVNwj28NkZp41cNDj4u3M/JGZZx3hld4NJL8wdmMsj4gZl4+Rx/9w5fv4mJnfqmL0H6d1A1wA7a7l+w0x/NIAAAAASUVORK5CYII=
"""
ORIGINAL_FILE_ICON_BASE64 = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAdgAAAHYBTnsmCAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAADQSURBVDiNrdJPSkJRHMXxTy+jQMf2NtACmmg7cdIwaA3SoImuokGgU5fg0D24i/6REEHW4HnpIu/nU/DAHdzf5Xw558flX49Y4bfm3OAeJwJ18BOYE2CJKVq5scgAhWbdYobzbUCTWlhgjjbu8od99IBnVZ2kC3ylSynuH50ySjDAS5Ckh3E+qAOM8BEAyu1BHeAdbwGgsw/gCa8B4BrDKNrRl1hggssgTVghLfEM3V3mCHDVZMqVvvIn1gf41huP083gW7WYvir6Lq1UNefwB94DQhY2gk5mAAAAAElFTkSuQmCC/S5xBEMbxz5yCKGk0XWxtbMTisLNR7FKlSHWQdOlshZAyRVrLEAg2ltr6oxHsxXBiEYj5BwJRSNIoMhZ68hIxuVVyb8AbGHjngXnnu8PuMhuZqU5r1Fr9fwAY/F2IiHG8wFQX+Z8y8929CDLz2jGGE2SBL1b/UepR3YQRMYfnf2Gex0QlPsfTzNy8SwMiM0VEYPaqA3+yxA6W8bKi/8RhQd1jrGAdmvis+5ZvYwS7BTm3+VJgDc8K6OE93qBVkPMEC5iuaF8HsKr8ODbxCN8LcnbxGqcu9xGMcv82lngbQ9jqaHH10UtrYRgfqOcmnMeXTlAHQOPWoA7rA/QB+gAPHuC8boCNOgGO8PbGVNwj28NkZp41cNDj4u3M/JGZZx3hld4NJL8wdmMsj4gZl4+Rx/9w5fv4mJnfqmL0H6d1A1wA7a7l+w0x/NIAAAAASUVORK5CYII=
"""



# ============================================================================
# GLOBAL GUI STATE VARIABLES
# ============================================================================
log_queue = queue.Queue()
current_opened_folder_path = None
initial_root_window = None
folder_icon_tk = None  # Folder icon for tree view
file_icon_tk = None    # File icon for tree view
sarif_load_functions = {}  # Dictionary to store SARIF load functions for auto-refresh
last_analysis_output_dir = None  # Last directory where analysis results were saved
sarif_tabs_dict = {}  # Dictionary to store SARIF tab information (tab_name -> (sarif_file, text_widget))

# ============================================================================
# UTILITY FUNCTIONS - Logging and Threading
# ============================================================================
def gui_log_message(log_text_widget, message):
    """Log message - if no log widget, just print to console"""
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


# ============================================================================
# FILE TREE OPERATIONS - Building and navigating the file tree
# ============================================================================
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

def on_tree_open(event, tree):
    selected_item_id = tree.focus()
    if not selected_item_id or not tree.exists(selected_item_id):
        return
    item_values = tree.item(selected_item_id, 'values')
    if item_values and len(item_values) == 3 and item_values[1] == 'folder' and item_values[2] == 'unpopulated':
        folder_path = item_values[0]
        populate_tree(tree, selected_item_id, folder_path, force_refresh=False)

def refresh_tree_node(tree, node_id):
    """Refresh a specific tree node"""
    if node_id == '':
        # Get the root folder path from current_opened_folder_path
        global current_opened_folder_path
        if current_opened_folder_path:
            populate_tree(tree, '', current_opened_folder_path, force_refresh=True)
    else:
        item_values = tree.item(node_id, 'values')
        if item_values and len(item_values) >= 1:
            folder_path = item_values[0]
            populate_tree(tree, node_id, folder_path, force_refresh=True)

# ============================================================================
# FILE SYSTEM OPERATIONS - Delete and rename files and folders
# ============================================================================
def action_delete_item(tree, log_text_widget=None):
    """Delete selected file or folder"""
    selected_item_id = tree.focus()
    if not selected_item_id:
        messagebox.showwarning("No Selection", "Please select a file or folder to delete.")
        return

    item_values = tree.item(selected_item_id, 'values')
    if not item_values or len(item_values) < 2:
        return

    item_path = item_values[0]
    item_name = os.path.basename(item_path)

    # Confirm deletion
    confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{item_name}'?", parent=tree.winfo_toplevel())
    if not confirm:
        return

    try:
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
            print(f"Deleted folder: {item_path}")
        elif os.path.isfile(item_path):
            os.remove(item_path)
            print(f"Deleted file: {item_path}")

        # Refresh parent
        parent_id = tree.parent(selected_item_id)
        refresh_tree_node(tree, parent_id if parent_id else '')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to delete: {e}")
        print(f"Error deleting item: {e}")

def action_rename_item(tree, log_text_widget=None):
    """Rename selected file or folder"""
    selected_item_id = tree.focus()
    if not selected_item_id:
        messagebox.showwarning("No Selection", "Please select a file or folder to rename.")
        return

    item_values = tree.item(selected_item_id, 'values')
    if not item_values or len(item_values) < 2:
        return

    old_path = item_values[0]
    old_name = os.path.basename(old_path)

    # Ask for new name using custom dialog with paste support
    new_name = ask_string_with_paste("Rename", f"Enter new name for '{old_name}':", parent=tree.winfo_toplevel(), initial_value=old_name)
    if not new_name or new_name == old_name:
        return

    new_path = os.path.join(os.path.dirname(old_path), new_name)

    try:
        os.rename(old_path, new_path)
        print(f"Renamed: {old_name} -> {new_name}")
        # Refresh parent
        parent_id = tree.parent(selected_item_id)
        refresh_tree_node(tree, parent_id if parent_id else '')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to rename: {e}")
        print(f"Error renaming item: {e}")

def action_open_in_system_explorer(tree):
    """Open the selected folder in system file explorer"""
    selected_item_id = tree.focus()
    if not selected_item_id:
        return

    item_values = tree.item(selected_item_id, 'values')
    if not item_values or len(item_values) < 2:
        return

    path = item_values[0]
    if os.path.isfile(path):
        path = os.path.dirname(path)

    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        log_queue.put(f"Error opening in system explorer: {e}")

# ============================================================================
# CODEQL DATABASE CREATION - Generate CodeQL database for analysis
# ============================================================================
def action_create_codeql_database(tree, status_label_widget=None):
    """Create CodeQL database for the selected folder"""
    selected_item_id = tree.focus()
    if not selected_item_id:
        messagebox.showwarning("No Selection", "Please select a folder to create CodeQL database.")
        return

    item_values = tree.item(selected_item_id, 'values')
    if not item_values or len(item_values) < 2:
        return

    folder_path = item_values[0]

    # Check if it's a folder
    if not os.path.isdir(folder_path):
        messagebox.showerror("Error", "Please select a folder.")
        return

    # Ask if user wants default build options
    use_default = messagebox.askyesno(
        "Build Options",
        "Do you want to use the default build options?",
        parent=tree.winfo_toplevel()
    )

    if use_default:
        # Use default options (no --command flag)
        build_command = None
    else:
        # Ask for build options using custom dialog with paste support
        build_options = ask_string_with_paste(
            "Build Options",
            "Enter build options (e.g., make, cmake --build .):",
            parent=tree.winfo_toplevel()
        )
        if not build_options:
            print("Build options not provided. Operation cancelled.")
            return
        build_command = build_options

    # Create DB directory path
    db_path = os.path.join(folder_path, "DB")

    # Update status
    if status_label_widget:
        status_label_widget.config(text="Status: creating database...")
        status_label_widget.update()

    def create_db_task():
        try:
            # Build command
            cmd = [
                "codeql", "database", "create",
                db_path,
                "--language=c-cpp",
                f"--source-root={folder_path}",
                "--overwrite"
            ]

            if build_command:
                cmd.append(f"--command={build_command}")

            print(f"Creating CodeQL database at {db_path}...")
            print(f"Executing: {' '.join(cmd)}")
            print("-" * 80)

            # Use Popen to stream output in real-time
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr to stdout
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )

            # Stream output line by line
            for line in process.stdout:
                print(line.rstrip())  # Print without extra newline

            # Wait for process to complete
            return_code = process.wait()

            print("-" * 80)

            if return_code == 0:
                print(f"Successfully created CodeQL database at: {db_path}")
                messagebox.showinfo("Success", f"CodeQL database created successfully at:\n{db_path}", parent=tree.winfo_toplevel())
            else:
                print(f"Failed to create CodeQL database. Exit code: {return_code}")
                messagebox.showerror("Error", f"Failed to create CodeQL database.\nExit code: {return_code}", parent=tree.winfo_toplevel())

        except FileNotFoundError:
            print("Error: 'codeql' command not found. Please ensure CodeQL CLI is in your PATH.")
            messagebox.showerror("Error", "'codeql' command not found.\nPlease ensure CodeQL CLI is in your PATH.", parent=tree.winfo_toplevel())
        except Exception as e:
            print(f"Error creating CodeQL database: {e}")
            print(traceback.format_exc())
            messagebox.showerror("Error", f"Error creating CodeQL database:\n{e}", parent=tree.winfo_toplevel())
        finally:
            # Reset status
            if status_label_widget:
                status_label_widget.config(text="Status: ready")

    # Run in thread
    run_in_thread(create_db_task)

# ============================================================================
# CODEQL ANALYSIS - Analyze database with pre-generated queries
# ============================================================================
def action_analyze_codeql_database(tree, status_label_widget=None, tab_creator_callback=None, explorer_window=None):
    """Analyze a CodeQL database using pre-generated queries"""
    selected_item_id = tree.focus()
    if not selected_item_id:
        messagebox.showwarning("No Selection", "Please select a CodeQL database folder to analyze.")
        return

    item_values = tree.item(selected_item_id, 'values')
    if not item_values or len(item_values) < 2:
        return

    selected_path = item_values[0]

    # Verify it's a valid directory
    if not os.path.isdir(selected_path):
        messagebox.showerror("Invalid Selection", "Please select a valid directory (CodeQL database folder).")
        return

    log_queue.put(f"Starting CodeQL analysis on database: {selected_path}")

    # Define only the two regexp query files to run
    query_files = [
        "query_regexp_calls_and_args.ql",
        "query_regexp_macro.ql"
    ]

    def analysis_task():
        global last_analysis_output_dir
        try:
            if status_label_widget:
                status_label_widget.config(text=f"Status: Analyzing database...")

            # Save output files in the parent directory of the database
            output_dir = os.path.dirname(selected_path)
            last_analysis_output_dir = output_dir  # Store for SARIF loading
            log_queue.put(f"Output directory: {output_dir}")

            successful_queries = 0
            failed_queries = 0
            sarif_files_to_merge = []

            for query_file in query_files:
                query_path = os.path.join(GENERATED_QL_OUTPUT_DIR, query_file)

                if not os.path.exists(query_path):
                    log_queue.put(f"WARNING: Skipping {query_file} - file not found")
                    continue

                # Define output paths
                query_basename = os.path.splitext(query_file)[0]
                bqrs_path = os.path.join(output_dir, f"{query_basename}.bqrs")
                sarif_path = os.path.join(output_dir, f"{query_basename}.sarif")

                print(f"\n{'='*60}")
                print(f"Running query: {query_file}")
                print(f"{'='*60}")

                # Step 1: Run CodeQL query
                cmd_run = [
                    "codeql", "query", "run",
                    f"--database={selected_path}",
                    query_path,
                    f"--output={bqrs_path}"
                ]

                print(f"Command: {' '.join(cmd_run)}")

                try:
                    result = subprocess.run(
                        cmd_run,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )

                    if result.stdout:
                        print(f"STDOUT:\n{result.stdout}")
                    if result.stderr:
                        print(f"STDERR:\n{result.stderr}")

                    if result.returncode != 0:
                        print(f"FAILED: Could not run query {query_file}. Exit code: {result.returncode}")
                        failed_queries += 1
                        continue

                    print(f"SUCCESS: Query executed successfully: {bqrs_path}")

                    # Step 2: Convert BQRS to SARIF
                    print(f"Converting BQRS to SARIF...")
                    cmd_interpret = [
                        "codeql", "bqrs", "interpret",
                        "--format=sarifv2.1.0",
                        "-t=kind=problem",
                        f"--output={sarif_path}",
                        "--",
                        bqrs_path
                    ]

                    print(f"Command: {' '.join(cmd_interpret)}")

                    result_interpret = subprocess.run(
                        cmd_interpret,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )

                    if result_interpret.stdout:
                        print(f"STDOUT:\n{result_interpret.stdout}")
                    if result_interpret.stderr:
                        print(f"STDERR:\n{result_interpret.stderr}")

                    if result_interpret.returncode == 0:
                        print(f"SUCCESS: SARIF generated: {sarif_path}")
                        successful_queries += 1
                        # Add to merge list if SARIF exists
                        if os.path.exists(sarif_path):
                            sarif_files_to_merge.append(sarif_path)
                    else:
                        print(f"WARNING: SARIF conversion failed for {query_file}")
                        successful_queries += 1  # Still count as success since query ran

                except FileNotFoundError:
                    print(f"ERROR: 'codeql' command not found. Please ensure CodeQL CLI is in your PATH.")
                    failed_queries += 1
                    break
                except Exception as e:
                    print(f"ERROR: Error processing {query_file}: {e}")
                    print(traceback.format_exc())
                    failed_queries += 1

            # Merge SARIF files into res.sarif
            res_sarif_path = os.path.join(output_dir, "res.sarif")
            if sarif_files_to_merge:
                try:
                    print(f"\n{'='*60}")
                    print(f"Merging SARIF files into res.sarif...")
                    print(f"{'='*60}")

                    # Build the merge command
                    cmd_merge = ["codeql", "github", "merge-results"]
                    for sarif_file in sarif_files_to_merge:
                        cmd_merge.append(f"--sarif={sarif_file}")
                    cmd_merge.append(f"--output={res_sarif_path}")

                    print(f"Command: {' '.join(cmd_merge)}")

                    result_merge = subprocess.run(
                        cmd_merge,
                        capture_output=True,
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )

                    if result_merge.stdout:
                        print(f"STDOUT:\n{result_merge.stdout}")
                    if result_merge.stderr:
                        print(f"STDERR:\n{result_merge.stderr}")

                    if result_merge.returncode == 0:
                        print(f"SUCCESS: Merged SARIF saved to: {res_sarif_path}")
                    else:
                        print(f"ERROR: Failed to merge SARIF files. Exit code: {result_merge.returncode}")

                except Exception as e:
                    print(f"ERROR: Failed to merge SARIF files: {e}")
                    print(traceback.format_exc())

            # Summary
            print(f"\n{'='*60}")
            print(f"Analysis Complete!")
            print(f"{'='*60}")
            print(f"Successful queries: {successful_queries}/{len(query_files)}")
            print(f"Results saved to: {output_dir}")

            # Create or update tab for this database
            if os.path.exists(res_sarif_path) and tab_creator_callback and explorer_window:
                # Get database name (parent folder name)
                db_parent_folder = os.path.basename(output_dir)
                print(f"\nCreating/updating tab for: {db_parent_folder}")
                try:
                    # Schedule tab creation on the main thread
                    explorer_window.after(0, lambda: tab_creator_callback(db_parent_folder, res_sarif_path))
                except Exception as e:
                    print(f"Error creating tab: {e}")
                    print(traceback.format_exc())


        except Exception as e:
            print(f"Critical error during analysis: {e}")
            print(traceback.format_exc())
        finally:
            if status_label_widget:
                status_label_widget.config(text="Status: ready")

    run_in_thread(analysis_task)

# ============================================================================
# SEARCH FUNCTIONALITY - Search within text widgets
# ============================================================================
def show_search_dialog(text_widget):
    """Show search dialog for text widget"""
    search_window = tk.Toplevel()
    search_window.title("Find")
    search_window.geometry("400x100")
    search_window.resizable(False, False)

    # Search frame
    search_frame = ttk.Frame(search_window, padding=10)
    search_frame.pack(fill=tk.BOTH, expand=True)

    # Search entry
    ttk.Label(search_frame, text="Find:").grid(row=0, column=0, sticky=tk.W, pady=5)
    search_entry = ttk.Entry(search_frame, width=30)
    search_entry.grid(row=0, column=1, padx=5, pady=5)
    search_entry.focus()

    # Status label
    status_label = ttk.Label(search_frame, text="")
    status_label.grid(row=1, column=0, columnspan=3, sticky=tk.W)

    # Search state
    current_index = {"value": "1.0"}

    def do_search(event=None):
        # Remove previous highlights
        text_widget.tag_remove("search_highlight", "1.0", tk.END)

        search_text = search_entry.get()
        if not search_text:
            status_label.config(text="Please enter search text")
            return

        # Search from current position
        start_pos = current_index["value"]
        pos = text_widget.search(search_text, start_pos, stopindex=tk.END, nocase=True)

        if pos:
            # Found match
            end_pos = f"{pos}+{len(search_text)}c"
            text_widget.tag_add("search_highlight", pos, end_pos)
            text_widget.tag_config("search_highlight", background="yellow", foreground="black")
            text_widget.see(pos)
            current_index["value"] = end_pos
            status_label.config(text=f"Found at {pos}")
        else:
            # No more matches, wrap around
            current_index["value"] = "1.0"
            pos = text_widget.search(search_text, "1.0", stopindex=tk.END, nocase=True)
            if pos:
                end_pos = f"{pos}+{len(search_text)}c"
                text_widget.tag_add("search_highlight", pos, end_pos)
                text_widget.tag_config("search_highlight", background="yellow", foreground="black")
                text_widget.see(pos)
                current_index["value"] = end_pos
                status_label.config(text=f"Wrapped to beginning - Found at {pos}")
            else:
                status_label.config(text="Not found")

    def find_next(event=None):
        do_search()

    # Buttons
    btn_frame = ttk.Frame(search_frame)
    btn_frame.grid(row=0, column=2, padx=5)

    ttk.Button(btn_frame, text="Find Next", command=find_next).pack(side=tk.LEFT, padx=2)
    ttk.Button(btn_frame, text="Close", command=search_window.destroy).pack(side=tk.LEFT, padx=2)

    # Bind Enter key to search
    search_entry.bind("<Return>", find_next)

    # Bind Escape to close
    search_window.bind("<Escape>", lambda e: search_window.destroy())

# ============================================================================
# SARIF PARSING HELPER - Parse SARIF files into human-readable format
# ============================================================================
def readSarif(sarif_path):
    """
    Parse a SARIF file and return formatted, human-readable text.
    Based on logic from testsarif.py

    Args:
        sarif_path: Path to the SARIF file

    Returns:
        str: Formatted text with results from the SARIF file
    """
    try:
        # Read and validate JSON
        with open(sarif_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate basic SARIF structure
        if not isinstance(data, dict):
            return "Error: SARIF file must contain a JSON object.\n"

        if "runs" not in data:
            return "Error: SARIF file is missing required 'runs' field.\n"

        output_lines = []
        result_count = 0

        for run in data.get("runs", []):
            results = run.get("results", [])
            for res in results:
                result_count += 1

                # Extract message
                msg = None
                m = res.get("message")
                if m:
                    # SARIF message object may have 'text' or 'message' etc
                    msg = m.get("text") or m.get("message") or str(m)
                if not msg:
                    msg = "<no message>"

                # Extract location(s)
                locs = res.get("locations") or []
                if not locs:
                    # No location, just print the message
                    output_lines.append(f"[Result {result_count}]")
                    output_lines.append(msg)
                    output_lines.append("")
                else:
                    for loc in locs:
                        phys = loc.get("physicalLocation")
                        if not phys:
                            output_lines.append(f"[Result {result_count}]")
                            output_lines.append(msg)
                            output_lines.append("")
                            continue

                        art = phys.get("artifactLocation")
                        uri = None
                        if art:
                            uri = art.get("uri")
                            # Sometimes URIs are file:///... — unwrap if so
                            if uri and uri.startswith("file://"):
                                uri = urllib.parse.unquote(uri[len("file://"):])

                        region = phys.get("region")
                        if region:
                            start_line = region.get("startLine")
                            start_col = region.get("startColumn")
                            loc_str = uri or "<unknown file>"
                            if start_line is not None:
                                loc_str += f":{start_line}"
                                if start_col is not None:
                                    loc_str += f":{start_col}"
                        else:
                            loc_str = uri or "<unknown file>"

                        output_lines.append(f"[Result {result_count}]")
                        output_lines.append(msg)
                        output_lines.append(f"Location: {loc_str}")
                        output_lines.append("")

        if result_count == 0:
            return "No results found in SARIF file.\n"

        header = f"Total Results: {result_count}\n{'='*80}\n\n"
        return header + "\n".join(output_lines)

    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in SARIF file.\n\nDetails: {str(e)}\n\nThe file may be corrupted or not a valid JSON file."
    except FileNotFoundError:
        return f"Error: SARIF file not found at path:\n{sarif_path}\n"
    except PermissionError:
        return f"Error: Permission denied reading SARIF file:\n{sarif_path}\n"
    except Exception as e:
        return f"Error reading SARIF file:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"

# ============================================================================
# SARIF VIEWING FUNCTIONS - Load SARIF from specific directory into tabs
# ============================================================================
def action_view_csv_result(tree, tab_creator_callback=None, explorer_window=None):
    """View SARIF result from the selected directory in a new tab"""
    selected_item = tree.selection()
    if not selected_item:
        messagebox.showwarning("No Selection", "Please select a folder containing res.sarif.")
        return

    selected_path = tree.set(selected_item[0], 'fullpath')

    # If the selected path is a file, use its parent directory
    if os.path.isfile(selected_path):
        sarif_dir = os.path.dirname(selected_path)
    else:
        sarif_dir = selected_path

    # Look for res.sarif in the selected directory
    sarif_path = os.path.join(sarif_dir, "res.sarif")

    if not os.path.exists(sarif_path):
        messagebox.showerror("SARIF Not Found", f"res.sarif not found in:\n{sarif_dir}\n\nMake sure analysis has been run for this database.")
        log_queue.put(f"SARIF file not found: {sarif_path}")
        return

    # Get parent folder name for the tab
    db_name = os.path.basename(sarif_dir)

    # Create or update tab with the SARIF content
    if tab_creator_callback and explorer_window:
        try:
            explorer_window.after(0, lambda: tab_creator_callback(db_name, sarif_path))
            log_queue.put(f"Opened res.sarif from {sarif_dir} in tab '{db_name}'")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open SARIF:\n{e}")
            log_queue.put(f"Error opening SARIF: {e}")
    else:
        messagebox.showerror("Error", "Tab creator not available")
        log_queue.put("Error: Tab creator callback not provided")

# ============================================================================
# CONTEXT MENU - Right-click menu for file operations
# ============================================================================
def show_context_menu(event, tree, log_text_widget=None, status_label=None, tab_creator_callback=None, explorer_window=None):
    """Show right-click context menu"""
    # Select the item under cursor
    item_id = tree.identify_row(event.y)
    if item_id:
        tree.selection_set(item_id)
        tree.focus(item_id)

    # Create context menu
    context_menu = tk.Menu(tree, tearoff=0)
    context_menu.add_command(label="Create CodeQL Database", command=lambda: action_create_codeql_database(tree, status_label))
    context_menu.add_command(label="Analyze CodeQL Database", command=lambda: action_analyze_codeql_database(tree, status_label, tab_creator_callback, explorer_window))
    context_menu.add_command(label="View SARIF result", command=lambda: action_view_csv_result(tree, tab_creator_callback, explorer_window))

    context_menu.add_separator()
    context_menu.add_command(label="Rename", command=lambda: action_rename_item(tree, log_text_widget))
    context_menu.add_command(label="Delete", command=lambda: action_delete_item(tree, log_text_widget))
    context_menu.add_separator()
    context_menu.add_command(label="Refresh", command=lambda: refresh_tree_node(tree, item_id if item_id else ''))
    context_menu.add_command(label="Open in System Explorer", command=lambda: action_open_in_system_explorer(tree))

    try:
        context_menu.tk_popup(event.x_root, event.y_root)
    finally:
        context_menu.grab_release()

# ============================================================================
# ANALYSIS ACTIONS - Main analysis functions (Scan, Update, Generate)
# ============================================================================
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

    # Ask for CodeQL database path
    suggested_db_path = os.path.join(project_context_path, "codeql-db")
    codeql_db_path = filedialog.askdirectory(
        title=f"Select CodeQL DB for '{os.path.basename(project_context_path)}'",
        initialdir=suggested_db_path if os.path.isdir(suggested_db_path) and os.path.exists(suggested_db_path) else project_context_path,
        parent=root_window
    )
    if not codeql_db_path:
        log_queue.put("CodeQL database path not provided. Scan cancelled."); return

    log_queue.put(f"Starting CodeQL scan for library IDs 1-7 (Project: {project_context_path}) using DB: {codeql_db_path}")
    def task():
        try:
            # Use pre-generated query files (all 5 queries)
            filename1 = os.path.join(GENERATED_QL_OUTPUT_DIR, "query_noargs.ql")
            filename2 = os.path.join(GENERATED_QL_OUTPUT_DIR, "query_withargs.ql")
            filename3 = os.path.join(GENERATED_QL_OUTPUT_DIR, "query_macro.ql")
            filename4 = os.path.join(GENERATED_QL_OUTPUT_DIR, "query_regexp_calls_and_args.ql")
            filename5 = os.path.join(GENERATED_QL_OUTPUT_DIR, "query_regexp_macro.ql")

            # Verify that the pre-generated queries exist
            if not os.path.exists(filename1):
                log_queue.put(f"Error: Pre-generated query file not found: {filename1}"); return
            if not os.path.exists(filename2):
                log_queue.put(f"Error: Pre-generated query file not found: {filename2}"); return
            if not os.path.exists(filename3):
                log_queue.put(f"Error: Pre-generated query file not found: {filename3}"); return
            if not os.path.exists(filename4):
                log_queue.put(f"Error: Pre-generated query file not found: {filename4}"); return
            if not os.path.exists(filename5):
                log_queue.put(f"Error: Pre-generated query file not found: {filename5}"); return

            log_queue.put("Using pre-generated query files:")
            log_queue.put(f"  - {os.path.basename(filename1)}")
            log_queue.put(f"  - {os.path.basename(filename2)}")
            log_queue.put(f"  - {os.path.basename(filename3)}")
            log_queue.put(f"  - {os.path.basename(filename4)}")
            log_queue.put(f"  - {os.path.basename(filename5)}")



            os.makedirs(PROJECT_OUTPUTS_DIR, exist_ok=True)
            bqrs_output_file_noargs = os.path.join(PROJECT_OUTPUTS_DIR, 'problem_primitives-noargs-analysis.bqrs')
            bqrs_output_file_withargs = os.path.join(PROJECT_OUTPUTS_DIR, 'problem_primitives-withargs-analysis.bqrs')
            brqs_output_file_macro = os.path.join(PROJECT_OUTPUTS_DIR, 'problem_primitives-macro-analysis.bqrs')
            brqs_output_file_regexp_calls_and_args = os.path.join(PROJECT_OUTPUTS_DIR, 'problem_primitives-regexp-calls-and-args-analysis.bqrs')
            brqs_output_file_regexp_macro = os.path.join(PROJECT_OUTPUTS_DIR, 'problem_primitives-regexp-macro-analysis.bqrs')
            log_queue.put(f"Running CodeQL queries, output to:")
            log_queue.put(f"  - {bqrs_output_file_noargs}")
            log_queue.put(f"  - {bqrs_output_file_withargs}")
            log_queue.put(f"  - {brqs_output_file_macro}")
            log_queue.put(f"  - {brqs_output_file_regexp_calls_and_args}")
            log_queue.put(f"  - {brqs_output_file_regexp_macro}")

            # NO ARGS CODEQL COMMAND
            cmd = [
                "codeql", "query", "run",
                f"--database={codeql_db_path}",
                filename1,
                f"--output={bqrs_output_file_noargs}",
            ]
            log_queue.put(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
            if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
            if result.returncode == 0:
                log_queue.put(f"Successfully ran query: {os.path.basename(filename1)}")
            else:
                log_queue.put(f"Failed to run query: {os.path.basename(filename1)}. Exit code: {result.returncode}")

            # WITH ARGS CODEQL COMMAND
            cmd = [
                "codeql", "query", "run",
                f"--database={codeql_db_path}",
                filename2,
                f"--output={bqrs_output_file_withargs}",
            ]
            log_queue.put(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
            if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
            if result.returncode == 0:
                log_queue.put(f"Successfully ran query: {os.path.basename(filename2)}")
            else:
                log_queue.put(f"Failed to run query: {os.path.basename(filename2)}. Exit code: {result.returncode}")

            # MACRO CODEQL COMMAND
            cmd = [
                "codeql", "query", "run",
                f"--database={codeql_db_path}",
                filename3,
                f"--output={brqs_output_file_macro}",
            ]
            log_queue.put(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
            if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
            if result.returncode == 0:
                log_queue.put(f"Successfully ran query: {os.path.basename(filename3)}")
            else:
                log_queue.put(f"Failed to run query: {os.path.basename(filename3)}. Exit code: {result.returncode}")

            # REGEXP CALLS AND ARGS CODEQL COMMAND
            cmd = [
                "codeql", "query", "run",
                f"--database={codeql_db_path}",
                filename4,
                f"--output={brqs_output_file_regexp_calls_and_args}",
            ]
            log_queue.put(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
            if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
            if result.returncode == 0:
                log_queue.put(f"Successfully ran query: {os.path.basename(filename4)}")
            else:
                log_queue.put(f"Failed to run query: {os.path.basename(filename4)}. Exit code: {result.returncode}")

            # REGEXP MACRO CODEQL COMMAND
            cmd = [
                "codeql", "query", "run",
                f"--database={codeql_db_path}",
                filename5,
                f"--output={brqs_output_file_regexp_macro}",
            ]
            log_queue.put(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.stdout: log_queue.put(f"CodeQL STDOUT:\n{result.stdout}")
            if result.stderr: log_queue.put(f"CodeQL STDERR:\n{result.stderr}")
            if result.returncode == 0:
                log_queue.put(f"Successfully ran query: {os.path.basename(filename5)}")
            else:
                log_queue.put(f"Failed to run query: {os.path.basename(filename5)}. Exit code: {result.returncode}")

        except FileNotFoundError:
            log_queue.put("Error: 'codeql' command not found. Please ensure CodeQL CLI is in your PATH.")
        except Exception as e:
            log_queue.put(f"Error during CodeQL project scan: {e}")
            log_queue.put(traceback.format_exc())
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
            output_pdf_path = os.path.join(PROJECT_OUTPUTS_DIR, output_pdf_name)
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

# ============================================================================
# MAIN GUI WINDOW CREATION
# ============================================================================
def create_file_explorer_window(folder_path_to_explore, root_window_to_destroy):
    """
    Creates the main application window with:
    - Top: Navigation bar with workspace path
    - Action buttons bar
    - Middle: Split view with file tree (left) and preview pane (right)
    - Bottom: Status bar
    """
    print(f"Creating file explorer window for: {folder_path_to_explore}")
    global initial_root_window, folder_icon_tk, file_icon_tk, current_opened_folder_path
    current_opened_folder_path = folder_path_to_explore

    # Destroy previous window if exists
    if root_window_to_destroy:
        root_window_to_destroy.destroy()

    # ========================================================================
    # WINDOW SETUP - Main window configuration
    # ========================================================================
    print("Creating Tk window...")
    explorer_root = tk.Tk()
    if folder_path_to_explore:
        explorer_root.title(f"File Explorer & Analyzer - {os.path.basename(folder_path_to_explore)}")
    else:
        explorer_root.title("File Explorer & Analyzer - No Workspace")
    explorer_root.geometry("1000x800")
    print("Tk window created")

    # Apply theme
    style = ttk.Style(explorer_root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        print("'clam' theme not available, using default.")

    # Load custom icons for file tree
    try:
        folder_icon_tk = tk.PhotoImage(master=explorer_root, data=ORIGINAL_FOLDER_ICON_BASE64)
        file_icon_tk = tk.PhotoImage(master=explorer_root, data=ORIGINAL_FILE_ICON_BASE64)
        print("Successfully loaded custom icons from base64.")
    except tk.TclError as e:
        print(f"Error loading custom icons from base64: {e}. Icons will be missing or default.")
        folder_icon_tk = None
        file_icon_tk = None

    # ========================================================================
    # NAVIGATION BAR (TOP) - Workspace path display and folder selection
    # ========================================================================
    nav_frame = ttk.Frame(explorer_root)
    nav_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

    def choose_workspace():
        global current_opened_folder_path
        new_folder = filedialog.askdirectory(
            title="Choose Workspace Folder",
            initialdir=current_opened_folder_path if current_opened_folder_path else os.path.expanduser("~"),
            parent=explorer_root
        )
        if new_folder:
            current_opened_folder_path = new_folder
            path_label.config(text=f"Path: {new_folder}")
            explorer_root.title(f"File Explorer & Analyzer - {os.path.basename(new_folder)}")
            populate_tree(file_tree, '', new_folder, force_refresh=True)

    ttk.Button(nav_frame, text="Choose Workspace", command=choose_workspace).pack(side=tk.LEFT, padx=(0, 5))
    path_label = ttk.Label(nav_frame, text=f"Path: {folder_path_to_explore}" if folder_path_to_explore else "Path: (No workspace selected - Click 'Choose Workspace')", relief="sunken", anchor='w')
    path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # ========================================================================
    # MAIN LAYOUT - Vertical and horizontal paned windows
    # ========================================================================
    main_v_pane = ttk.PanedWindow(explorer_root, orient=tk.VERTICAL)
    main_v_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
    explorer_h_pane = ttk.PanedWindow(main_v_pane, orient=tk.HORIZONTAL)
    main_v_pane.add(explorer_h_pane, weight=3)

    # ========================================================================
    # LEFT PANE - File tree navigation
    # ========================================================================
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
    file_tree.heading("#0", text="Workspace", anchor='w')
    for col in ("fullpath", "type", "status"):
        file_tree.column(col, width=0, stretch=tk.NO)

    # ========================================================================
    # RIGHT PANE - SARIF Results Tabbed View
    # ========================================================================
    right_frame = ttk.Frame(explorer_h_pane)
    explorer_h_pane.add(right_frame, weight=3)

    # Create tabbed notebook for SARIF results
    csv_notebook = ttk.Notebook(right_frame)
    csv_notebook.pack(fill=tk.BOTH, expand=True, padx=(0,5), pady=(0,5))

    # Dictionary to store tabs: {db_name: (tab_frame, text_area, res_sarif_path)}
    dynamic_tabs = {}

    # Function to create a new tab for a database
    def create_tab_for_database(db_name, res_sarif_path):
        """Create a new tab for a database analysis result"""
        # Check if tab already exists
        if db_name in dynamic_tabs:
            # Update existing tab
            _, text_area, _ = dynamic_tabs[db_name]
            text_area.delete(1.0, tk.END)
        else:
            # Create new tab
            tab_frame = ttk.Frame(csv_notebook)
            csv_notebook.add(tab_frame, text=db_name)

            # Text area for SARIF content
            text_area = scrolledtext.ScrolledText(
                tab_frame,
                wrap=tk.NONE,
                font=("Consolas", 9)
            )
            text_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Make text area read-only but searchable
            def make_readonly(event):
                # Allow Ctrl+C, Ctrl+A, and navigation keys
                if event.state & 0x4:  # Ctrl key
                    if event.keysym in ('c', 'a', 'f', 'C', 'A', 'F'):
                        return
                # Allow arrow keys, home, end, page up/down
                if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next'):
                    return
                return "break"

            text_area.bind("<Key>", make_readonly)

            # Bind Ctrl+F to open search dialog
            text_area.bind("<Control-f>", lambda e, tw=text_area: show_search_dialog(tw))

            # Store tab reference
            dynamic_tabs[db_name] = (tab_frame, text_area, res_sarif_path)

        # Load the SARIF content using the helper function
        _, text_area, _ = dynamic_tabs[db_name]
        if os.path.exists(res_sarif_path):
            try:
                # Use readSarif helper to parse and format the SARIF file
                formatted_content = readSarif(res_sarif_path)
                text_area.insert(tk.END, formatted_content)
                text_area.insert(1.0, f"File: {res_sarif_path}\n{'='*80}\n\n")
                print(f"Loaded SARIF into tab '{db_name}': {res_sarif_path}")
            except Exception as e:
                text_area.insert(tk.END, f"Error loading SARIF file:\n{e}")
                print(f"Error loading SARIF for tab '{db_name}': {e}")
        else:
            text_area.insert(tk.END, f"SARIF file not found: {res_sarif_path}\n\n")
            text_area.insert(tk.END, f"The analysis may have failed to generate this file.")
            print(f"SARIF not found for tab '{db_name}': {res_sarif_path}")

        # Switch to the new/updated tab
        for i in range(csv_notebook.index("end")):
            if csv_notebook.tab(i, "text") == db_name:
                csv_notebook.select(i)
                break

    # Populate the file tree with initial data (only if a workspace is provided)
    if folder_path_to_explore:
        print("Populating file tree...")
        populate_tree(file_tree, '', folder_path_to_explore)
        print("File tree populated")
    else:
        print("No workspace selected - file tree is empty")

    # ========================================================================
    # EVENT BINDINGS - File tree interactions
    # ========================================================================
    file_tree.bind("<<TreeviewOpen>>", lambda e: on_tree_open(e, file_tree))

    # ========================================================================
    # STATUS BAR (BOTTOM) - Application status display
    # ========================================================================
    status_frame = ttk.Frame(explorer_root)
    status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
    status_label = ttk.Label(status_frame, text="Status: ready", relief="sunken", anchor='w')
    status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ========================================================================
    # CONTEXT MENU BINDINGS - Right-click menu
    # ========================================================================
    file_tree.bind("<Button-3>", lambda e: show_context_menu(e, file_tree, None, status_label, create_tab_for_database, explorer_root))  # Right-click (Linux/Windows)
    file_tree.bind("<Button-2>", lambda e: show_context_menu(e, file_tree, None, status_label, create_tab_for_database, explorer_root))  # Right-click (Mac)

    # ========================================================================
    # FINALIZATION - Check CLI tools availability
    # ========================================================================
    if not cli_dependencies_found:
        print("Warning: CLI tool dependencies could not be imported. Analysis actions are disabled.")
    else:
        print("CLI Analyzer Ready. Right-click on a CodeQL database to analyze.")

    # Start the main event loop
    print("Starting main event loop...")
    explorer_root.protocol("WM_DELETE_WINDOW", lambda: on_explorer_close(explorer_root))
    explorer_root.mainloop()
    print("Main loop exited")

# ============================================================================
# WINDOW LIFECYCLE
# ============================================================================
def on_explorer_close(root):
    """Handle window close event"""
    print("Explorer window closed.")
    root.destroy()

# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================
def main_initial_window():
    """Main entry point - Pre-generates queries and launches GUI"""
    if cli_dependencies_found:
        try:
            # Define library IDs to use (1 to 7)
            library_ids = [1, 2, 3, 4, 5, 6, 7]
            print(f"Pre-generating queries for library IDs: {library_ids}")

            # Generate all 5 queries (create separate connections for each)
            conn1 = sqlite3.connect(CORE_DB_PATH)
            query_noargs_cached = generate_query_no_args(conn1, library_ids)
            conn1.close()

            conn2 = sqlite3.connect(CORE_DB_PATH)
            query_withargs_cached = generate_query_with_args(conn2, library_ids)
            conn2.close()

            query_macro_cached = generate_query_macros()
            query_regexp_calls_cached = generate_query_regexp_calls_and_args()
            query_regexp_macro_cached = generate_query_regexp_macro()

            # Write them to files immediately
            if query_noargs_cached:
                with open(os.path.join(GENERATED_QL_OUTPUT_DIR, "query_noargs.ql"), 'w') as f:
                    f.write(query_noargs_cached)
                print("Generated query_noargs.ql")

            if query_withargs_cached:
                with open(os.path.join(GENERATED_QL_OUTPUT_DIR, "query_withargs.ql"), 'w') as f:
                    f.write(query_withargs_cached)
                print("Generated query_withargs.ql")

            if query_macro_cached:
                with open(os.path.join(GENERATED_QL_OUTPUT_DIR, "query_macro.ql"), 'w') as f:
                    f.write(query_macro_cached)
                print("Generated query_macro.ql")

            if query_regexp_calls_cached:
                with open(os.path.join(GENERATED_QL_OUTPUT_DIR, "query_regexp_calls_and_args.ql"), 'w') as f:
                    f.write(query_regexp_calls_cached)
                print("Generated query_regexp_calls_and_args.ql")

            if query_regexp_macro_cached:
                with open(os.path.join(GENERATED_QL_OUTPUT_DIR, "query_regexp_macro.ql"), 'w') as f:
                    f.write(query_regexp_macro_cached)
                print("Generated query_regexp_macro.ql")

        except Exception as e:
            print(f"Warning: Failed to generate queries: {e}")
            print(traceback.format_exc())

    # Launch the main GUI window
    print("Launching GUI...")
    # Start with no workspace, user must choose one
    create_file_explorer_window(None, None)

# ============================================================================
# SCRIPT EXECUTION
# ============================================================================
if __name__ == "__main__":
    main_initial_window()
