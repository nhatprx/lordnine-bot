"""
Shared styled dialog helpers for the application.

Consolidates duplicated dialog boilerplate from tab_loops, tab_accounts,
tab_nodes, tab_macros, and flowchart_ui into reusable functions.
"""
import customtkinter as ctk
import os

from constants import COLOR


def _get_icon_path():
    """Get the logo.ico path relative to this module."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")


def create_styled_dialog(parent, title, width, height, fg_color=None):
    """
    Create a centered, styled CTkToplevel dialog.

    Returns the dialog widget. Caller is responsible for adding content.
    """
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.resizable(False, False)
    dialog.configure(fg_color=fg_color or COLOR["surface"])
    dialog.transient(parent if isinstance(parent, (ctk.CTk, ctk.CTkToplevel)) else parent.winfo_toplevel())
    dialog.grab_set()

    ico_path = _get_icon_path()
    if os.path.exists(ico_path):
        dialog.after(200, lambda: dialog.iconbitmap(ico_path) if dialog.winfo_exists() else None)

    dialog.update_idletasks()
    root = parent.winfo_toplevel()
    x = root.winfo_x() + (root.winfo_width() - width) // 2
    y = root.winfo_y() + (root.winfo_height() - height) // 2
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    return dialog


def show_styled_info(parent, title, text):
    """Simple info popup with an OK button. Replaces 4+ duplicate methods."""
    info = create_styled_dialog(parent, "Lordbot Control", 300, 130)

    ctk.CTkLabel(
        info, text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=COLOR["text"],
    ).pack(pady=(20, 4))

    ctk.CTkLabel(
        info, text=text,
        font=ctk.CTkFont(size=11),
        text_color=COLOR["text_muted"],
    ).pack(pady=(0, 12))

    ctk.CTkButton(
        info, text="OK", command=info.destroy,
        fg_color=COLOR["primary"], text_color="#FFFFFF",
        font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6, width=100,
    ).pack()


def show_confirm_dialog(parent, title, text, confirm_text="Delete",
                        danger=True, title_color=None):
    """
    Confirmation dialog with confirm/cancel buttons.
    Returns True if confirmed, False otherwise.
    """
    dialog = create_styled_dialog(parent, "Lordbot Control", 380, 180)

    result = {"confirmed": False}

    ctk.CTkLabel(
        dialog, text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=title_color or COLOR["warning"],
    ).pack(pady=(20, 4))

    ctk.CTkLabel(
        dialog, text=text,
        font=ctk.CTkFont(size=11),
        text_color=COLOR["text_muted"], justify="center",
    ).pack(pady=(0, 12))

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(fill="x", padx=24, pady=(0, 16))

    def on_confirm():
        result["confirmed"] = True
        dialog.destroy()

    confirm_bg = COLOR["danger"] if danger else COLOR["primary"]
    confirm_hover = "#8B2020" if danger else COLOR["primary_h"]

    ctk.CTkButton(
        btn_row, text=confirm_text, command=on_confirm,
        fg_color=confirm_bg, hover_color=confirm_hover,
        text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6,
    ).pack(side="left", expand=True, fill="x", padx=(0, 4))

    ctk.CTkButton(
        btn_row, text="Cancel", command=dialog.destroy,
        fg_color="transparent", hover_color=COLOR["surface2"],
        border_width=1, border_color=COLOR["border"],
        text_color=COLOR["text_muted"],
        font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6,
    ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    dialog.wait_window()
    return result["confirmed"]


def show_input_dialog(parent, title, subtitle="", placeholder="",
                      title_color=None, width=360, height=180):
    """
    Text input dialog. Returns the entered string or None if cancelled.
    """
    dialog = create_styled_dialog(parent, "Lordbot Control", width, height)

    result = {"value": None}

    ctk.CTkLabel(
        dialog, text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=title_color or COLOR["text"],
    ).pack(pady=(20, 4))

    if subtitle:
        ctk.CTkLabel(
            dialog, text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color=COLOR["text_muted"],
        ).pack(pady=(0, 8))

    entry = ctk.CTkEntry(
        dialog, fg_color=COLOR["bg"], border_color=COLOR["border"],
        border_width=1, corner_radius=6, height=34,
        font=ctk.CTkFont(size=12), text_color=COLOR["text"],
        placeholder_text=placeholder, placeholder_text_color=COLOR["text_muted"],
    )
    entry.pack(fill="x", padx=24, pady=(0, 12))
    entry.focus_set()

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(fill="x", padx=24, pady=(0, 16))

    def on_ok(*_):
        result["value"] = entry.get()
        dialog.destroy()

    entry.bind("<Return>", on_ok)
    entry.bind("<Escape>", lambda _: dialog.destroy())

    ctk.CTkButton(
        btn_row, text="Create", command=on_ok,
        fg_color=COLOR["primary"], hover_color=COLOR["surface2"],
        text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6,
    ).pack(side="left", expand=True, fill="x", padx=(0, 4))

    ctk.CTkButton(
        btn_row, text="Cancel", command=lambda: dialog.destroy(),
        fg_color="transparent", hover_color=COLOR["surface2"],
        border_width=1, border_color=COLOR["border"],
        text_color=COLOR["text_muted"],
        font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6,
    ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    dialog.wait_window()
    return result["value"]


def show_selection_dialog(parent, title, items, title_color=None,
                          item_color=None, item_hover=None):
    """
    Scrollable selection list dialog.
    Returns the selected item string, or None if cancelled.
    """
    dialog = create_styled_dialog(parent, "Lordbot Control", 300, 380)

    result = {"value": None}

    ctk.CTkLabel(
        dialog, text=title,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=title_color or COLOR["primary"],
    ).pack(pady=(16, 8))

    frame = ctk.CTkScrollableFrame(
        dialog, fg_color=COLOR["bg"],
        scrollbar_button_color=COLOR["text_dim"], corner_radius=8,
    )
    frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    def on_sel(item):
        result["value"] = item
        dialog.destroy()

    btn_fg = item_color or COLOR["primary"]
    btn_hover = item_hover or COLOR["primary_h"]

    for item in items:
        ctk.CTkButton(
            frame, text=item, command=lambda x=item: on_sel(x),
            fg_color=btn_fg, hover_color=btn_hover,
            text_color="#FFFFFF", font=ctk.CTkFont(size=11),
            height=32, corner_radius=6,
        ).pack(pady=3, fill="x", padx=4)

    ctk.CTkButton(
        dialog, text="Cancel", command=dialog.destroy,
        fg_color="transparent", hover_color=COLOR["surface2"],
        border_width=1, border_color=COLOR["text_dim"],
        text_color=COLOR["text_dim"],
        font=ctk.CTkFont(size=11, weight="bold"),
        height=30, corner_radius=6, width=100,
    ).pack(pady=(0, 12))

    dialog.wait_window()
    return result["value"]
