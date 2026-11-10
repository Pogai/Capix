# -*- coding: utf-8 -*-
"""全屏框选截图区域（tkinter 半透明遮罩 + 拖框）。

`select_region(root)` 打开全屏半透明遮罩，用户拖拽出一个矩形，
松手后返回标准化 (x, y, w, h)。Esc / 右键 / 太小 取消返回 None。
"""

import tkinter as tk

_TINT = "#101010"   # 遮罩底色
_LINE = "#3388ff"   # 框线（与取景框同蓝）
_GRID = "#ffffff"   # 文字


class _RegionOverlay:
    def __init__(self, root: tk.Tk, result: dict):
        self.root = root
        self.result = result

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.screen_w = self.win.winfo_screenwidth()
        self.screen_h = self.win.winfo_screenheight()
        self.win.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.win.configure(bg=_TINT)
        self.win.attributes("-alpha", 0.55)

        self.cv = tk.Canvas(self.win, bg=_TINT, highlightthickness=0, cursor="crosshair")
        self.cv.pack(fill="both", expand=True)

        self._start = None
        self._cur = None

        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Button-3>", lambda _e: self._on_cancel())
        self.win.bind("<Escape>", lambda _e: self._on_cancel())
        self.win.bind("<Return>", lambda _e: self._on_cancel())

        self.cv.create_text(
            24, 22, anchor="nw", fill=_GRID,
            font=("Microsoft YaHei UI", 12),
            text="拖拽框选要持续截图的区域，松开确认；Esc / 右键取消",
        )

    def _on_press(self, event):
        self._start = (event.x_root, event.y_root)

    def _on_drag(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x_root, event.y_root
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        self.cv.delete("drawn")
        self._rad =         self.cv.create_rectangle(
            left, top, right, bottom, outline=_LINE, width=4, tags="drawn"
        )
        w, h = right - left, bottom - top
        # 拖拽中尺寸标签（贴选区上方/下方，白字）
        ly = top - 26 if top > 40 else bottom + 8
        ly = max(4, min(ly, self.screen_h - 24))
        self.cv.create_text(
            left + 4, ly, anchor="nw", fill=_GRID,
            font=("Consolas", 12), text=f"{w} × {h}", tags="drawn",
        )

    def _on_release(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x_root, event.y_root
        left, top = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        self._close(left, top, w, h)

    def _on_cancel(self):
        self.win.destroy()

    def _close(self, x, y, w, h):
        if w >= 4 and h >= 4:
            self.result["region"] = (int(x), int(y), int(w), int(h))
        self.win.destroy()


def select_region(root: tk.Tk):
    """在主线程弹框选遮罩，返回 (x, y, w, h) 或 None。"""
    result = {}
    overlay = _RegionOverlay(root, result)
    overlay.win.grab_set()
    root.wait_window(overlay.win)
    return result.get("region")