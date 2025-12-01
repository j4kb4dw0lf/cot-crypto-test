"""
Custom input dialogs with enhanced clipboard support.
Provides text input dialogs that work properly in X11/remote environments.
"""

import tkinter as tk
from tkinter import ttk


def ask_string_with_paste(title, prompt, parent=None, initial_value=""):
    """
    Custom dialog for text input with full paste support.
    Replacement for simpledialog.askstring() with better paste functionality.

    Args:
        title: Dialog window title
        prompt: Prompt text to display
        parent: Parent window
        initial_value: Initial value for the entry field

    Returns:
        str: User input string, or None if cancelled
    """
    result = [None]  # Use list to store result from nested function

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("500x150")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    # Center the dialog
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
    y = (dialog.winfo_screenheight() // 2) - (150 // 2)
    dialog.geometry(f"500x150+{x}+{y}")

    # Prompt label
    prompt_label = ttk.Label(dialog, text=prompt, wraplength=480)
    prompt_label.pack(pady=(10, 5), padx=10)

    # Entry field with full clipboard support
    entry_var = tk.StringVar(value=initial_value)
    entry = ttk.Entry(dialog, textvariable=entry_var, width=60)
    entry.pack(pady=5, padx=10, fill=tk.X)
    entry.focus_set()
    entry.select_range(0, tk.END)

    # Enable standard copy/paste shortcuts with direct clipboard access
    def paste_text(event=None):
        try:
            # Get clipboard content
            clipboard_content = dialog.clipboard_get()
            # Get current cursor position
            cursor_pos = entry.index(tk.INSERT)
            # Get current selection if any
            try:
                sel_start = entry.index(tk.SEL_FIRST)
                sel_end = entry.index(tk.SEL_LAST)
                # Delete selection
                current_value = entry_var.get()
                new_value = current_value[:sel_start] + clipboard_content + current_value[sel_end:]
                entry_var.set(new_value)
                entry.icursor(sel_start + len(clipboard_content))
            except tk.TclError:
                # No selection, insert at cursor
                current_value = entry_var.get()
                new_value = current_value[:cursor_pos] + clipboard_content + current_value[cursor_pos:]
                entry_var.set(new_value)
                entry.icursor(cursor_pos + len(clipboard_content))
        except tk.TclError:
            # Clipboard empty or unavailable
            pass
        return "break"

    def copy_text(event=None):
        try:
            # Get selected text
            selected_text = entry.selection_get()
            dialog.clipboard_clear()
            dialog.clipboard_append(selected_text)
        except tk.TclError:
            pass
        return "break"

    def cut_text(event=None):
        try:
            # Get selected text
            selected_text = entry.selection_get()
            dialog.clipboard_clear()
            dialog.clipboard_append(selected_text)
            # Delete selection
            entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        return "break"

    # Bind clipboard shortcuts
    entry.bind('<Control-v>', paste_text)
    entry.bind('<Control-V>', paste_text)
    entry.bind('<Control-c>', copy_text)
    entry.bind('<Control-C>', copy_text)
    entry.bind('<Control-x>', cut_text)
    entry.bind('<Control-X>', cut_text)
    entry.bind('<Shift-Insert>', paste_text)  # Alternative paste shortcut
    entry.bind('<Control-Insert>', copy_text)  # Alternative copy shortcut
    entry.bind('<Shift-Delete>', cut_text)     # Alternative cut shortcut

    # Add right-click context menu
    def show_context_menu(event):
        context_menu = tk.Menu(entry, tearoff=0)
        context_menu.add_command(label="Cut", command=lambda: cut_text())
        context_menu.add_command(label="Copy", command=lambda: copy_text())
        context_menu.add_command(label="Paste", command=lambda: paste_text())
        context_menu.add_separator()
        context_menu.add_command(label="Select All", command=lambda: entry.select_range(0, tk.END))
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    entry.bind('<Button-3>', show_context_menu)  # Right-click

    # Button frame
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)

    def on_ok():
        result[0] = entry_var.get()
        dialog.destroy()

    def on_cancel():
        result[0] = None
        dialog.destroy()

    ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)

    # Bind Enter and Escape
    entry.bind('<Return>', lambda e: on_ok())
    dialog.bind('<Escape>', lambda e: on_cancel())

    # Wait for dialog to close
    dialog.wait_window()

    return result[0]
