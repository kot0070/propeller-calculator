from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class Tooltip:
    enabled = True

    def __init__(self, widget: tk.Widget, text_provider: str | Callable[[], str]):
        self.widget = widget
        self.text_provider = text_provider
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Enter>", self.schedule, add=True)
        widget.bind("<Leave>", self.hide, add=True)
        widget.bind("<ButtonPress>", self.hide, add=True)

    def schedule(self, _event=None) -> None:
        self.hide()
        if self.enabled:
            self.after_id = self.widget.after(450, self.show)

    def show(self) -> None:
        if not self.enabled or self.window is not None:
            return
        text = self.text_provider() if callable(self.text_provider) else self.text_provider
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        window = self.window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(window, background="#14212B", highlightbackground="#3F5A6B", highlightthickness=1)
        frame.pack()
        label = tk.Label(frame, text=text, justify="left", background="#14212B", foreground="#F4F7F8",
                         font=("Segoe UI", 9), padx=10, pady=8, wraplength=430)
        label.pack()

    def hide(self, _event=None) -> None:
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window:
            self.window.destroy()
            self.window = None


class ScrollFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#F3F6F8")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._wheel, add=True)

    def _wheel(self, event) -> None:
        if self.winfo_containing(event.x_root, event.y_root) is not None:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
