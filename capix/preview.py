# -*- coding: utf-8 -*-
"""长图预览窗（懒显示 + 可缩放/滚轮/拖拽）。

- 首次截图后才创建/显示（由上层控制）；未截前不出现。
- 按框外左侧（左侧放不下换右侧）贴附，深色卡片 + 标题栏 + 图区。
- 图区为视口：默认按宽度适配；支持
    · 鼠标滚轮：上下滚动
    · Ctrl+滚轮：以光标为中心缩放
    · 按住左键拖拽：平移
    · 双击：复位（按宽度适配）
    · 标题栏 [＋][－][⟲][✕] 按钮：放大/缩小/复位/关闭预览
- 渲染只绘制可见视口（O(卡面积)），内容长不影响流畅度；不抢焦点、在框外不被截入。
"""

import tkinter as tk
from tkinter import font as tkfont

from . import winutil, png

_KEY = "#010203"
_CARD_BG = "#1f2430"
_CARD_BG_RGB = b"\x1f\x24\x30"
_TITLE_FG = "#aab2c5"
_HINT_FG = "#6f7789"
_BORDER = "#39404e"
_BTN_BG = "#2b3242"
_BTN_HOVER = "#3b9dff"
_BTN_HOVER_CLOSE = "#e05555"

_TITLE_FONT = ("Microsoft YaHei UI", 8)
_HINT_FONT = ("Microsoft YaHei UI", 7)

_TITLE_H = 24
_PAD = 6

_MIN_SCALE = 0.05
_MAX_SCALE = 4.0


class PreviewWindow:
    def __init__(self, root, region, width=210, on_close=None):
        self.root = root
        self.x, self.y, self.w, self.h = (int(v) for v in region)
        self.on_close = on_close    # 用户点 ✕ 关闭预览时回调上层
        self.closed = False         # 本次会话内已关闭 → 不再自动显示

        self._src = None            # (w, h, rgb)
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._photo = None
        self._drag = None
        self._render_job = None

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.cw = width
        self.ch = max(260, min(int(sh * 0.56), 660))

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        self.win.configure(bg=_KEY)
        self.visible = self._place()
        if not self.visible:
            self.win.wm_geometry("1x1+0+0")
            return

        self.cv = tk.Canvas(self.win, bg=_KEY, highlightthickness=0, bd=0,
                            width=self.cw + 3, height=self.ch + 3)
        self.cv.pack()

        self._round_rect(self.cv, 1, 1, self.cw + 2, self.ch + 2, r=10,
                         fill=_CARD_BG, outline="")
        # 标题
        self.cv.create_text(_PAD + 4, 1 + _TITLE_H / 2, anchor="w",
                            text="长图预览", fill=_TITLE_FG, font=_TITLE_FONT)
        # 标题栏按钮 ＋ － ⟲ ✕（✕ 关闭预览，固定最右）
        self._hbtns = {}
        bx = self.cw - 8
        for name, glyph in (("close", "✕"), ("fit", "⟲"), ("zin", "＋"), ("zout", "－")):
            hcol = _BTN_HOVER_CLOSE if name == "close" else _BTN_HOVER
            self.cv.create_oval(bx - 7, 1 + _TITLE_H / 2 - 7, bx + 7, 1 + _TITLE_H / 2 + 7,
                                fill=_BTN_BG, outline="", tags=("h_%s" % name, "hbg_%s" % name))
            self.cv.create_text(bx, 1 + _TITLE_H / 2, text=glyph, fill="#d6dbe6",
                                font=("Microsoft YaHei UI", 8), tags=("h_%s" % name,))
            self.cv.tag_bind("h_%s" % name, "<Enter>",
                             lambda e, n=name, h=hcol: self.cv.itemconfigure("hbg_%s" % n, fill=h))
            self.cv.tag_bind("h_%s" % name, "<Leave>",
                             lambda e, n=name: self.cv.itemconfigure("hbg_%s" % n, fill=_BTN_BG))
            self.cv.tag_bind("h_%s" % name, "<Button-1>",
                             lambda e, n=name: self._btn(n))
            self._hbtns[name] = True
            bx -= 18

        # 图区边框
        ix0, iy0, ix1, iy1 = self._img_rect()
        self.cv.create_rectangle(ix0, iy0, ix1, iy1, outline=_BORDER, width=1)

        # 底部署名提示（按可用宽度自适应，避免文字被遮住）
        hint = self._pick_hint([
            "滚轮滚动 · Ctrl+滚轮缩放 · 拖拽移动 · 双击复位",
            "滚轮滚动 · Ctrl+缩放 · 拖拽 · 双击复位",
            "滚轮滚动 · Ctrl缩放 · 拖拽 · 双击复位",
            "滚轮/缩放/拖拽 · 双击复位",
            "滚轮 · 双击复位",
        ], self.cw - 16)
        self.cv.create_text(self.cw / 2 + 1, self.ch - 6,
                            text=hint, fill=_HINT_FG, font=_HINT_FONT)

        # 占位
        self._img_item = self.cv.create_image(ix0, iy0, anchor="nw", tags=("img",))
        self._placeholder = self.cv.create_text(
            (ix0 + ix1) // 2, (iy0 + iy1) // 2, text="等待截图…",
            fill=_TITLE_FG, font=_TITLE_FONT,
        )

        # 交互绑定（图区）
        self.cv.bind("<MouseWheel>", self._on_wheel)
        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_drag)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Double-Button-1>", self._on_reset)

        try:
            winutil.make_tool_window(self.win)
        except Exception:
            pass

    # ---------- 布局 ----------
    def _img_rect(self):
        return (_PAD, _TITLE_H + _PAD, self.cw - _PAD, self.ch - 20)

    def _pick_hint(self, candidates, avail):
        """选第一条能完整显示在 avail 像素内的提示文案。"""
        try:
            f = tkfont.Font(font=_HINT_FONT)
        except Exception:
            return candidates[-1]
        for text in candidates:
            try:
                if f.measure(text) <= avail:
                    return text
            except Exception:
                return text
        return candidates[-1]

    def _round_rect(self, cv, x0, y0, x1, y1, r=10, **kw):
        pts = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return cv.create_polygon(pts, smooth=True,
                                 outline=kw.pop("outline", ""),
                                 width=kw.pop("width", 1), **kw)

    def _place(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        W, H = self.cw + 3, self.ch + 3
        lx = self.x - 12 - W
        ry = self.y + max(0, (self.h - H) // 2)
        ry = max(0, min(ry, sh - H))
        if lx >= 0:                  # 优先贴取景框左侧
            self.win.wm_geometry("%dx%d+%d+%d" % (W, H, lx, ry))
            return True
        rx = self.x + self.w + 12    # 左侧放不下 → 换右侧
        if rx + W <= sw:
            self.win.wm_geometry("%dx%d+%d+%d" % (W, H, rx, ry))
            return True
        return False

    # ---------- 数据 ----------
    def set_source(self, w, h, rgb):
        """设置源长图（RGB）。每次刷新都回到“按宽适配 + 最新一张”。"""
        if self.closed or not self.visible:
            return
        if not w or not h or not rgb:
            return
        self._src = (w, h, rgb)
        try:
            self.cv.itemconfigure(self._placeholder, state="hidden")
        except Exception:
            pass
        self._fit_width()
        self._scroll_to_bottom()
        self._schedule_render()

    def move_to(self, region):
        """取景框改变尺寸/位置后重新贴附（轻量：仅窗口 geometry，不重渲染）。

        拖拽热路径高频调用：窗口平移不改变视口像素，无需 _schedule_render
        （渲染是 ~600 行纯 Python 像素循环，曾导致拖拽卡顿）。仅在从隐藏
        恢复显示时补渲染一次。"""
        self.x, self.y, self.w, self.h = (int(v) for v in region)
        if self.closed:
            return
        ok = self._place()
        self.visible = bool(ok)
        try:
            if ok:
                if not self.win.winfo_viewable():
                    self.win.deiconify()
                    if self._src is not None:
                        self._schedule_render()
            else:
                self.win.withdraw()
        except Exception:
            pass

    def _fit_width(self):
        if not self._src:
            return
        w, h, _ = self._src
        ix0, iy0, ix1, iy1 = self._img_rect()
        vw = ix1 - ix0
        self._scale = max(_MIN_SCALE, vw / float(w))
        self._ox = 0.0
        self._oy = 0.0

    def _fit_all(self):
        if not self._src:
            return
        w, h, _ = self._src
        ix0, iy0, ix1, iy1 = self._img_rect()
        vw, vh = ix1 - ix0, iy1 - iy0
        self._scale = max(_MIN_SCALE, min(vw / float(w), vh / float(h)))
        self._ox = max(0.0, (w - vw / self._scale) / 2)
        self._oy = max(0.0, (h - vh / self._scale) / 2)

    def clear(self):
        if not self.visible:
            return
        self._src = None
        self._photo = None
        try:
            self.cv.itemconfigure(self._img_item, image="")
            self.cv.itemconfigure(self._placeholder, state="normal")
        except Exception:
            pass

    # ---------- 渲染 ----------
    def _schedule_render(self):
        if self._render_job is not None:
            return
        self._render_job = self.cv.after(16, self._render)

    def _clamp(self):
        if not self._src:
            return
        w, h, _ = self._src
        ix0, iy0, ix1, iy1 = self._img_rect()
        vw, vh = ix1 - ix0, iy1 - iy0
        max_ox = max(0.0, w - vw / self._scale)
        max_oy = max(0.0, h - vh / self._scale)
        self._ox = min(max(0.0, self._ox), max_ox)
        self._oy = min(max(0.0, self._oy), max_oy)

    def _render(self):
        self._render_job = None
        if not self.visible or self._src is None:
            return
        self._clamp()
        w, h, rgb = self._src
        ix0, iy0, ix1, iy1 = self._img_rect()
        vw, vh = ix1 - ix0, iy1 - iy0
        if vw <= 1 or vh <= 1:
            return
        s = self._scale
        ox, oy = self._ox, self._oy
        xs = [min(w - 1, int(ox + i / s)) for i in range(vw)]
        # 先用卡片底色铺满视口：源图不够高时下方保持底色，
        # 不能把越界行钳到 h-1（那样会出现“撕裂 + 拉伸条纹”）。
        out = bytearray(_CARD_BG_RGB * (vw * vh))
        for j in range(vh):
            sy = int(oy + j / s)
            if sy >= h:
                break
            base = sy * w * 3
            row = j * vw * 3
            for i in range(vw):
                si = base + xs[i] * 3
                di = row + i * 3
                out[di] = rgb[si]
                out[di + 1] = rgb[si + 1]
                out[di + 2] = rgb[si + 2]
        try:
            data = png.encode_rgb(vw, vh, bytes(out))
            self._photo = tk.PhotoImage(master=self.cv, data=data, format="png")
            self.cv.itemconfigure(self._img_item, image=self._photo)
            self.cv.coords(self._img_item, ix0, iy0)
        except Exception:
            pass

    # ---------- 交互 ----------
    def _on_wheel(self, event):
        if not self._src:
            return
        ctrl = bool(event.state & 0x0004)
        if ctrl:
            self._zoom_at(event.x, event.y, 1.2 if event.delta > 0 else 1 / 1.2)
        else:
            self._oy -= (event.delta / 120.0) * (40.0 / self._scale)
            self._schedule_render()

    def _zoom_at(self, px, py, factor):
        if not self._src:
            return
        ix0, iy0, ix1, iy1 = self._img_rect()
        vx, vy = px - ix0, py - iy0
        if vx < 0 or vy < 0 or vx > ix1 - ix0 or vy > iy1 - iy0:
            vx = vy = None
        src_x = self._ox + (vx / self._scale if vx is not None else 0)
        src_y = self._oy + (vy / self._scale if vy is not None else 0)
        old = self._scale
        self._scale = min(_MAX_SCALE, max(_MIN_SCALE, self._scale * factor))
        if vx is not None:
            self._ox = src_x - vx / self._scale
            self._oy = src_y - vy / self._scale
        self._schedule_render()

    def _on_press(self, event):
        ix0, iy0, ix1, iy1 = self._img_rect()
        if ix0 <= event.x <= ix1 and iy0 <= event.y <= iy1:
            self._drag = (event.x, event.y, self._ox, self._oy)

    def _on_drag(self, event):
        if self._drag is None:
            return
        x0, y0, ox, oy = self._drag
        self._ox = ox - (event.x - x0) / self._scale
        self._oy = oy - (event.y - y0) / self._scale
        self._schedule_render()

    def _on_release(self, event):
        self._drag = None

    def _on_reset(self, event):
        ix0, iy0, ix1, iy1 = self._img_rect()
        if ix0 <= event.x <= ix1 and iy0 <= event.y <= iy1:
            self._fit_width()
            self._schedule_render()

    def _scroll_to_bottom(self):
        """滚到长图底部，让最新一张截图保持在可见区内。"""
        if not self._src:
            return
        w, h, _ = self._src
        ix0, iy0, ix1, iy1 = self._img_rect()
        vh = iy1 - iy0
        self._oy = max(0.0, h - vh / self._scale)

    def close(self):
        """关闭预览：本次取景内不再显示（重新框选后由新实例恢复）。"""
        if self.closed:
            return
        self.closed = True
        self.visible = False
        try:
            self.win.withdraw()
        except Exception:
            pass
        if self.on_close is not None:
            try:
                self.on_close()
            except Exception:
                pass

    def _btn(self, name):
        if name == "close":
            self.close()
            return
        if name == "zin":
            self._zoom_at(self.cw / 2, self.ch / 2, 1.25)
        elif name == "zout":
            self._zoom_at(self.cw / 2, self.ch / 2, 1 / 1.25)
        elif name == "fit":
            self._fit_width()
        self._schedule_render()

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        self._photo = None