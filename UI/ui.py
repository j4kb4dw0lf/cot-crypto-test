import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
import os
import re

# --- Base64 Encoded Icons ---
FOLDER_ICON_BASE64 = """
R0lGODlhEAAQAMQAAORyAP///8x/ANx7AE9cAP/zAOdzAPDAAPrXAPXiAPvjANOLAF9TAHtUAHxU
AHxVAI9Nmp9qmKOimqmlnsrDydrT1+Tg4P///wAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAkA
ABkALAAAAAAQABAAAAVTICWOZFlKBACHqQQUKzdbDEFzQxDQ3LCc2LQwmjExiQ1yTVEhD0En
SjPKNgDEsTaA8YQBYDEKlIAAAxYBCQoWJZeXElmAWTkYSAgCADs=
"""
FILE_ICON_BASE64 = """
R0lGODlhEAAQAMQAAKOgoP///3BwcPDw8GRkZOzs7ERERFRUVIqKimbGyL6+vq6urtLS0uTk5P//
/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACH5BAkAABkA
LAAAAAAQABAAAAVV4CSOZGlKulwDENTfANgEEoLlCpqDAXBjDYCBNbAIJVAQCFIBRaG4EIYAwU
JARkKJgCRkE0gMCgZsDRkQCk4gLTDEDgWAQjmwFIEq4G4IhgkCADs=
"""

# --- Syntax Highlighting Configuration ---
C_CPP_KEYWORDS = {
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if',
    'int', 'long', 'register', 'return', 'short', 'signed', 'sizeof', 'static',
    'struct', 'switch', 'typedef', 'union', 'unsigned', 'void', 'volatile', 'while',
    'asm', 'dynamic_cast', 'namespace', 'reinterpret_cast', 'try', 'bool',
    'explicit', 'new', 'static_cast', 'typeid', 'catch', 'false', 'operator',
    'template', 'typename', 'class', 'friend', 'private', 'this', 'throw',
    'true', 'virtual', 'delete', 'inline', 'public', 'protected', 'wchar_t',
    'using', 'constexpr', 'nullptr', 'decltype', 'noexcept', 'static_assert',
    'thread_local', 'alignas', 'alignof', 'char16_t', 'char32_t'
}
SYNTAX_PATTERNS = {
    'comment': r'(//[^\n]*|/\*.*?\*/)',
    'preprocessor': r'(#\s*\w+)',
    'string': r'(".*?"|\'.*?\')',
    'keyword': r'\b(' + '|'.join(C_CPP_KEYWORDS) + r')\b',
    'number': r'\b([0-9]+\.?[0-9]*f?|[0-9]*\.?[0-9]+f?|0x[0-9a-fA-F]+[ulL]*|[0-9]+[ulL]*)\b'
}
SYNTAX_COLORS = {
    'comment': 'gray',
    'preprocessor': 'purple',
    'string': 'green',
    'keyword': 'blue',
    'number': 'orange',
    'default': 'black'
}

initial_root_window = None
folder_icon_tk = None
file_icon_tk = None

def apply_syntax_highlighting(text_widget, content, file_extension):
    text_widget.mark_set("range_start", "1.0")
    text_widget.delete("1.0", tk.END)
    text_widget.insert("1.0", content)

    if file_extension.lower() not in ('.c', '.cpp', '.h', '.hpp'):
        return

    for tag_name, color in SYNTAX_COLORS.items():
        text_widget.tag_configure(tag_name, foreground=color)
    
    text_widget.tag_add('default', "1.0", tk.END)

    for tag_name, pattern in SYNTAX_PATTERNS.items():
        for match in re.finditer(pattern, content, re.DOTALL if tag_name == 'comment' else 0):
            start_index = "1.0 + %d chars" % match.start()
            end_index = "1.0 + %d chars" % match.end()
            text_widget.tag_remove('default', start_index, end_index)
            text_widget.tag_add(tag_name, start_index, end_index)

def display_file_content_with_highlighting(item_path, text_preview_area):
    text_preview_area.config(state=tk.NORMAL)
    text_preview_area.delete(1.0, tk.END)
    try:
        if os.path.isdir(item_path):
            text_preview_area.insert(tk.END, "PREVIEW NOT AVAILABLE FOR DIRECTORIES\n(Double-click a file to see its preview)")
        elif os.path.isfile(item_path):
            file_extension = os.path.splitext(item_path)[1]
            try:
                with open(item_path, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read(1024 * 1024) # Read up to 1MB
                apply_syntax_highlighting(text_preview_area, content, file_extension)
                if len(content) == 1024 * 1024:
                    text_preview_area.insert(tk.END, "\n\n--- Preview truncated (1MB limit) ---", "comment")
            except Exception as e:
                text_preview_area.insert(tk.END, f"MISSING PREVIEW\n(Non-textual or unreadable file)\nError: {e}")
        else:
            text_preview_area.insert(tk.END, "Item not found or is not a file/directory.")
    except Exception as e:
        text_preview_area.insert(tk.END, f"An error occurred: {e}")
    finally:
        text_preview_area.config(state=tk.DISABLED)

def populate_tree(tree, parent_node_id, folder_path, force_refresh=False):
    if parent_node_id:
        parent_values = list(tree.item(parent_node_id, 'values'))
        if len(parent_values) == 3 and parent_values[2] == 'populated' and not force_refresh:
            return

    for child in tree.get_children(parent_node_id):
        tree.delete(child)

    try:
        items = sorted(os.listdir(folder_path), key=lambda s: (not os.path.isdir(os.path.join(folder_path, s)), s.lower()))
        for item_name in items:
            item_full_path = os.path.join(folder_path, item_name)
            if os.path.isdir(item_full_path):
                node_id = tree.insert(parent_node_id, 'end', text=item_name, image=folder_icon_tk,
                                      values=[item_full_path, 'folder', 'unpopulated'], open=False)
                tree.insert(node_id, 'end', text="") 
            elif os.path.isfile(item_full_path):
                tree.insert(parent_node_id, 'end', text=item_name, image=file_icon_tk, values=[item_full_path, 'file'])
    except OSError as e:
        tree.insert(parent_node_id, 'end', text=f"Error: {e.strerror}", values=["error", "error", "error"]) # Ensure 3 values

    if parent_node_id:
        parent_values = list(tree.item(parent_node_id, 'values'))
        if len(parent_values) == 3:
            parent_values[2] = 'populated'
            tree.item(parent_node_id, values=tuple(parent_values))

def on_tree_select_changed(event, tree, text_preview_area):
    """
    Handles item selection in the treeview.
    Now, this function will NOT automatically load the preview.
    It can be used for other single-click actions if needed in the future (e.g., status bar update).
    For now, it can clear the preview or show a hint.
    """
    selected_item_id = tree.focus()
    if not selected_item_id:
        return

    item_values = tree.item(selected_item_id, 'values')
    if item_values:
        item_type = item_values[1] if len(item_values) > 1 else None
        text_preview_area.config(state=tk.NORMAL)
        text_preview_area.delete(1.0, tk.END)
        if item_type == 'folder':
            text_preview_area.insert(tk.END, "Selected a folder.\nDouble-click a file to see its preview.")
        elif item_type == 'file':
            text_preview_area.insert(tk.END, f"Selected file: {tree.item(selected_item_id, 'text')}\nDouble-click to open preview.")
        else:
            text_preview_area.insert(tk.END, "Double-click a file to see its preview.")
        text_preview_area.config(state=tk.DISABLED)


def on_tree_double_click(event, tree, text_preview_area):
    """Handles double-click on a tree item. Loads preview if it's a file."""
    region = tree.identify_region(event.x, event.y)
    item_id = tree.identify_row(event.y)

    if not item_id or region not in ('cell', 'tree'): # 'tree' is for the icon area
        return # Click was not on a valid item's content or icon

    item_values = tree.item(item_id, 'values')
    if item_values and len(item_values) >= 2 and item_values[1] == 'file':
        full_item_path = item_values[0]
        display_file_content_with_highlighting(full_item_path, text_preview_area)
    # If it's a folder, the default Treeview binding will handle expansion/collapse,
    # which in turn triggers <<TreeviewOpen>> or <<TreeviewClose>>.

def on_tree_open(event, tree):
    selected_item_id = tree.focus()
    if not selected_item_id: return

    item_values = tree.item(selected_item_id, 'values')
    if item_values and len(item_values) == 3 and item_values[1] == 'folder' and item_values[2] == 'unpopulated':
        folder_path = item_values[0]
        populate_tree(tree, selected_item_id, folder_path, force_refresh=False)

def create_file_explorer_window(folder_path_to_explore):
    global initial_root_window, folder_icon_tk, file_icon_tk
    if initial_root_window:
        initial_root_window.destroy()

    explorer_root = tk.Tk()
    explorer_root.title(f"File Explorer - {os.path.basename(folder_path_to_explore)}")
    explorer_root.geometry("900x700")

    # --- Apply Clam Theme for potentially rounder/modern widgets ---
    # Note: The extent of "roundedness" is theme and platform-dependent.
    # This is the most straightforward way to influence widget appearance in ttk.
    style = ttk.Style(explorer_root)
    try:
        style.theme_use('clam')
        print("Using 'clam' theme.")
    except tk.TclError:
        print("'clam' theme not available, using default.")
        # You could try other themes like 'alt', 'default', 'classic' as fallbacks
        # style.theme_use('alt') 

    try:
        folder_icon_tk = tk.PhotoImage(data=FOLDER_ICON_BASE64)
        file_icon_tk = tk.PhotoImage(data=FILE_ICON_BASE64)
    except tk.TclError as e:
        print(f"Error loading icons: {e}. Icons will be missing.")
        folder_icon_tk = None
        file_icon_tk = None

    paned_window = ttk.PanedWindow(explorer_root, orient=tk.HORIZONTAL)
    paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5) # Added padding

    left_frame = ttk.Frame(paned_window, width=300) # ttk.Frame will be affected by theme
    paned_window.add(left_frame, weight=1)

    tree_scrollbar_y = ttk.Scrollbar(left_frame, orient=tk.VERTICAL) # ttk.Scrollbar
    tree_scrollbar_x = ttk.Scrollbar(left_frame, orient=tk.HORIZONTAL) # ttk.Scrollbar
    file_tree = ttk.Treeview(left_frame,
                             yscrollcommand=tree_scrollbar_y.set,
                             xscrollcommand=tree_scrollbar_x.set,
                             selectmode='browse') # ttk.Treeview
    tree_scrollbar_y.config(command=file_tree.yview)
    tree_scrollbar_x.config(command=file_tree.xview)
    tree_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    tree_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
    file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    file_tree['columns'] = ("fullpath", "type", "status")
    file_tree.column("#0", width=250, minwidth=200, anchor='w')
    file_tree.column("fullpath", width=0, stretch=tk.NO)
    file_tree.column("type", width=0, stretch=tk.NO)
    file_tree.column("status", width=0, stretch=tk.NO)
    file_tree.heading("#0", text="Name", anchor='w')

    right_frame = ttk.Frame(paned_window) # ttk.Frame
    paned_window.add(right_frame, weight=3)
    
    # ScrolledText uses tk.Text, not ttk.Text, so theme might not affect its core as much.
    text_preview_area = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10, "normal"),
                                                  relief="solid", borderwidth=1) # Added relief for definition
    text_preview_area.pack(fill=tk.BOTH, expand=True, padx=(0,5), pady=(0,5)) # Adjusted padding

    # Initial message in preview
    text_preview_area.config(state=tk.NORMAL)
    text_preview_area.delete(1.0, tk.END)
    text_preview_area.insert(tk.END, "Double-click a file to see its preview.")
    text_preview_area.config(state=tk.DISABLED)

    populate_tree(file_tree, '', folder_path_to_explore)

    file_tree.bind("<<TreeviewSelect>>", lambda event: on_tree_select_changed(event, file_tree, text_preview_area))
    file_tree.bind("<Double-1>", lambda event: on_tree_double_click(event, file_tree, text_preview_area))
    file_tree.bind("<<TreeviewOpen>>", lambda event: on_tree_open(event, file_tree))
    
    explorer_root.mainloop()

def select_folder_and_proceed():
    global initial_root_window
    folder_path = filedialog.askdirectory(parent=initial_root_window)
    if folder_path:
        create_file_explorer_window(folder_path)
    else:
        print("No folder selected.")

def main_initial_window():
    global initial_root_window
    initial_root_window = tk.Tk()
    initial_root_window.title("Folder Analyzer Tool - Step 1")

    # --- Apply Clam Theme for potentially rounder/modern widgets also to initial window ---
    style = ttk.Style(initial_root_window)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass # Ignore if clam theme is not available, use default

    window_width = 400
    window_height = 200
    screen_width = initial_root_window.winfo_screenwidth()
    screen_height = initial_root_window.winfo_screenheight()
    center_x = int(screen_width/2 - window_width / 2)
    center_y = int(screen_height/2 - window_height / 2)
    initial_root_window.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    initial_root_window.focus_force()

    # Use ttk.Frame for main content area to get theme benefits
    content_frame = ttk.Frame(initial_root_window, padding="20")
    content_frame.pack(expand=True, fill=tk.BOTH)

    label = ttk.Label(content_frame, text="Click the button to select a folder for analysis.")
    label.pack(pady=10)
    select_button = ttk.Button(content_frame, text="Select Folder to Analyze", command=select_folder_and_proceed)
    select_button.pack(pady=10)
    initial_root_window.mainloop()

if __name__ == "__main__":
    main_initial_window()
