# -*- coding: utf-8 -*-
"""常驻取景框 + 浅色工具条。

取景框由 12 个独立小窗组成（4 条边条 + 8 个圆点手柄），都是原生可点击窗口：
- 框内不覆盖任何窗口，桌面/应用照常操作（点“下一题”等）；
- 按住边条或圆点拖动即可实时调整截图区域，最小 80×60，限制在屏幕内；
- 圆点手柄：白圈 + 蓝芯，压在边线上（assets/ui/dot.png，构建期生成）。

工具条：[计数] [截图] [复制] [设置] [✕]，默认锚定框右下角外侧。
图标为构建期 Pillow 生成的 PNG（assets/ui），缺失时回退矢量绘制。
"""

import math
import os
import tkinter as tk
from tkinter import font as tkfont

from . import paths, winutil
from .logsetup import log

_BORDER = "#3388ff"      # 边框蓝
_BORDER_W = 4            # 边框粗细（与框选拖拽线一致）
_ARROW = 24              # 白色开口箭头手柄窗口边长
_MIN_W, _MIN_H = 80, 60  # 最小取景尺寸

_KEY = "#010203"         # 透明色键
_FONT_S = ("Consolas", 11)
_FONT_LBL = ("Microsoft YaHei UI", 9)
_DOT_CORE = "#3388ff"    # 圆点蓝芯（备选皮肤时与边框同色）

# 浅色工具栏配色（白底 + 深色图标，不透明）
_BAR_BG = "#ffffff"       # 条底（白，不透明）
_BAR_LINE = "#d7dbe2"     # 条描边（浅灰供轮廓）
_ICON = "#336fe6"         # 图标主色蓝（实心填充风格，与素材一致）
_ICON_OFF = "#c3c8d2"     # 禁用浅灰
_COUNTER = "#5b6470"      # 计数文字（深灰）
_BTN_HOVER = "#e9f1fd"    # hover：浅蓝垫色（图标保持深色）
_BTN_HOVER_EXIT = "#fdecec"  # 关闭 hover：浅红垫色
_BTN_PRESS = "#d6e3fb"    # 按下：稍深浅蓝
_BTN_PRESS_EXIT = "#f7d7d7"
_BTN_ACTIVE = "#dbe8fc"   # 移动模式开启中的持续高亮
_GRIP_BG = "#f1f3f7"      # 把手底色
_GRIP_HOVER = "#e8edf5"
_GRIP_DOT = "#b6bdc9"     # 把手圆点
_SEP = "#e6e9ee"          # 分隔线

# 移动模式捕获层（淡色罩，屏幕仍可见；鼠标不穿透）
_INSIDE_TINT = "#3388ff"      # 淡色罩基色（alpha 极低）
_INSIDE_ALPHA = 0.06           # 5%~ → 可看见屏幕，又可捕获鼠标
_INSIDE_GLYPH = "#336fe6"      # 徽标图形主色（与图标同蓝）

_BTN = 38                 # 按钮边长（圆角方形）
_BTN_RADIUS = 10
_PAD = 11
_GAP = 8
_COUNTER_W = 96           # 计数/状态文字区（容纳"已截 20""上限 20" 11号字）
_GRIP_W = 26              # 六点拖拽把手宽度

# 尺寸标签（底 #222222、贴上边框正上方）
_LBL_BG = "#222222"
_LBL_FG = "#ffffff"
_LBL_H = 20
_LBL_R = 6

# 浮动提示（深色气泡，浅色工具栏上的对比强调）
_TOAST_FONT = ("Microsoft YaHei UI", 9)
_TOAST_MAX_W = 320
_TOAST_BG = "#2a2f3a"
_TOAST_FG = "#f2f5fa"
_TOAST_OK = "#4ade80"
_TOAST_ERR = "#ff6b6b"

# 图标资源文件名（构建期生成，直接按显示尺寸输出）与按钮名的对应
_ICON_FILE = {"shot": "camera", "copy": "copy", "gear": "gear",
             "exit": "close", "move": "move"}

_LEFT = frozenset(("left", "mleft", "nw", "sw"))
_RIGHT = frozenset(("right", "mright", "ne", "se"))
_TOP = frozenset(("top", "mtop", "nw", "ne"))
_BOTTOM = frozenset(("bottom", "mbottom", "sw", "se"))


def _round_rect(cv, x0, y0, x1, y1, r=10, **kw):
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return cv.create_polygon(pts, smooth=True,
                             outline=kw.pop("outline", ""),
                             width=kw.pop("width", 1), **kw)


class FrameOverlay:
    def __init__(self, root, region, on_capture, on_copy, on_exit,
                 on_settings=None, max_count=20, on_resize=None):
        self.root = root
        self.x, self.y, self.w, self.h = (int(v) for v in region)
        self.on_capture = on_capture
        self.on_copy = on_copy
        self.on_exit = on_exit
        self.on_settings = on_settings
        self.on_resize = on_resize
        self.max_count = int(max_count)
        self.toolbar_inside = False
        self._last_count = 0
        self._shot_disabled = False
        self._btns = {}
        self._photos = {}            # (name,state) -> PhotoImage
        self._icon_items = {}        # name -> canvas image item id（位图模式）
        self._drag = None
        self._borders = {}        # 4 条边条（纯色实心窗）
        self._dots = {}           # 8 个白色开口箭头手柄
        self._lbl_win = None      # 尺寸标签窗
        self._dot_img = None
        self._dot_raw = None
        self._toast_win = None
        self._tb_custom = False   # 用户拖拽过工具条 → 保持自定义位置
        self._grip_drag = None
        self._hover_on = {}       # 按钮当前是否处于 hover
        self._move_mode = False   # 移动模式：框内任意位置可拖（工具条「移动」按钮切换）
        self._inside_win = None   # 移动模式的内部捕获窗
        self._cursors = {}        # 边框窗口原光标（移动模式时换 fleur）
        self._geo_cache = {}      # 窗口 geometry 去重缓存（拖拽性能）
        self._screen = (root.winfo_screenwidth(), root.winfo_screenheight())

        self._build_borders()
        self._build_toolbar()
        self._build_label()
        self._inside_win = self._make_inside()
        self._inside_badge = self._make_inside_badge()   # 中央移动徽标
        self._place_toolbar()

        # 无闪烁呈现：窗口全部先创建为隐藏，布局完成后一次性显示边框与工具条，
        # 手柄稍后呈现（避免逐个弹窗造成的闪烁）
        self.show_borders()
        self.show_toolbar()
        self.show_label()
        self.root.after(140, self.show_dots)

        try:
            ok = all(self._icon_items.get(n) is not None
                     for n in ("shot", "copy", "gear", "exit"))
            log("工具条图标: %s" % ("PNG" if ok else "矢量回退"))
            log("取景框: %d×%d @ (%d,%d)" % (self.w, self.h, self.x, self.y))
        except Exception:
            pass

    # ---------------- 取景框（4 边条 + 8 圆点手柄） ----------------
    def _build_borders(self):
        for name, cursor in (("top", "sb_v_double_arrow"),
                             ("bottom", "sb_v_double_arrow"),
                             ("left", "sb_h_double_arrow"),
                             ("right", "sb_h_double_arrow")):
            self._borders[name] = self._make_strip(name, cursor)
        # 圆点：4 角 + 每边中点（压在边线上，拖拽语义与所在边一致；白箭头朝向随边/角）
        dots = (
            ("nw", "size_nw_se", "nw"), ("ne", "size_ne_sw", "ne"),
            ("sw", "size_ne_sw", "sw"), ("se", "size_nw_se", "se"),
            ("mtop", "sb_v_double_arrow", "n"), ("mbottom", "sb_v_double_arrow", "s"),
            ("mleft", "sb_h_double_arrow", "w"), ("mright", "sb_h_double_arrow", "e"),
        )
        for name, cursor, direction in dots:
            self._dots[name] = self._make_dot(name, cursor, direction)
        self._layout_borders()

    def _bind_drag(self, win, name):
        win.bind("<Button-1>", lambda e, n=name: self._drag_start(n, e))
        win.bind("<B1-Motion>", self._drag_move)
        win.bind("<ButtonRelease-1>", self._drag_end)

    def _make_strip(self, name, cursor):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.withdraw()                       # 先隐藏，布局完统一显示（防闪烁）
        win.configure(bg=_BORDER, cursor=cursor)
        self._cursors[name] = cursor
        self._bind_drag(win, name)
        try:
            winutil.make_tool_window(win)
        except Exception:
            pass
        return win

    def _arrow_photo(self, direction):
        """加载指定朝向的白色开口箭头（显示尺寸 24px）。"""
        key = ("arrow", direction)
        if key in self._photos:
            return self._photos[key]
        photo = None
        p = ""
        try:
            p = paths.resource_path(os.path.join("assets", "ui",
                                                 "arrow_%s.png" % direction))
            if os.path.exists(p):
                photo = tk.PhotoImage(master=self.root, file=p)
            else:
                log("箭头素材不存在: %s" % p)
        except Exception as exc:
            log("箭头加载失败 %s: %r" % (p, exc))
            photo = None
        self._photos[key] = photo
        return photo

    def _make_dot(self, name, cursor, direction):
        """手柄窗：白箭头（方向随边/角）；素材缺失时矢量回退。"""
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        win.withdraw()                       # 先隐藏，稍后呈现（防闪烁）
        win.configure(bg=_KEY)
        win.configure(cursor=cursor)
        self._cursors[name] = cursor
        photo = self._arrow_photo(direction)
        cv = tk.Canvas(win, bg=_KEY, highlightthickness=0, bd=0,
                       width=_ARROW, height=_ARROW)
        cv.pack()
        if photo is not None:
            cv.create_image(_ARROW / 2, _ARROW / 2, image=photo)
        else:
            self._vec_arrow(cv, _ARROW / 2, _ARROW / 2, direction)
        self._bind_drag(win, name)
        self._bind_drag(cv, name)
        try:
            winutil.make_tool_window(win)
        except Exception:
            pass
        return win

    def _vec_arrow(self, cv, cx, cy, direction):
        """矢量回退：白色开口箭头（单边 V / 角双 V）。"""
        arm, lw = 7.0, 3.0

        def v_at(px, py, dxdy):
            dx, dy = dxdy
            # 顶点在 (px,py)，两臂张开方向随 dx,dy
            cv.create_line(px - dx * arm, py - dy * arm, px, py,
                           fill=_ICON, width=lw, capstyle="round")
            cv.create_line(px, py, px + dx * arm, py + dy * arm,
                           fill=_ICON, width=lw, capstyle="round")

        dirs = {"n": (0, 1), "s": (0, -1), "e": (-1, 0), "w": (1, 0)}
        if direction in dirs:
            v_at(cx, cy, dirs[direction])
        else:
            # 角：双箭头，中心向角点方向压偏
            dx = -1 if "w" in direction else 1
            dy = -1 if "n" in direction else 1
            off = 5.0
            v_at(cx + dx * off, cy, (0, dy if "s" in direction else -0)
                 if False else (0, -1 if "n" in direction else 1))
            v_at(cx, cy + dy * off, (-1 if "w" in direction else 1, 0))

    def _set_geo(self, win, geo):
        """geometry 去重：拖拽热路径上跳过未变化的窗口，减少刷新压力。"""
        cache = self._geo_cache
        if cache.get(win) == geo:
            return
        cache[win] = geo
        try:
            win.geometry(geo)
        except Exception:
            pass

    # ---------------- 尺寸标签（贴上边框正上方，随拖拽实时更新） ----------------
    def _build_label(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        win.withdraw()
        win.configure(bg=_KEY)
        self._lbl_cv = tk.Canvas(win, bg=_KEY, highlightthickness=0, bd=0,
                                 width=120, height=_LBL_H + 4)
        self._lbl_cv.pack()
        self._lbl_rect = None
        self._lbl_text = None
        self._lbl_win = win
        try:
            winutil.make_tool_window(win)
        except Exception:
            pass

    def _update_label(self):
        """按当前 w/h 更新尺寸标签内容与位置（贴上边框正上方、左对齐）。"""
        win = self._lbl_win
        if win is None:
            return
        text = "%d × %d" % (self.w, self.h)
        try:
            f = tkfont.Font(font=_FONT_LBL)
            tw = f.measure(text) + 20
        except Exception:
            tw = 60
        win_w = max(48, min(tw, 200))
        try:
            cv = self._lbl_cv
            cv.delete("all")
            cv.configure(width=win_w, height=_LBL_H + 4)
            _round_rect(cv, 1, 1, win_w, _LBL_H + 1, r=_LBL_R,
                        fill=_LBL_BG, outline="")
            cv.create_text(win_w / 2, 2 + _LBL_H / 2, text=text,
                           fill=_LBL_FG, font=_FONT_LBL)
        except Exception:
            pass
        # 位置：上边框正上方、与左边框对齐；贴屏幕顶时翻到框内上方
        gx = self.x
        gy = self.y - _BORDER_W - _LBL_H - 8
        if gy < 0:
            gy = self.y + _BORDER_W + 4
        sw = self._screen[0]
        gx = max(0, min(gx, sw - win_w))
        self._set_geo(win, "%dx%d+%d+%d" % (win_w, _LBL_H + 4, gx, gy))

    def show_label(self):
        try:
            if self._lbl_win is not None:
                self._update_label()
                self._lbl_win.deiconify()
        except Exception:
            pass

    def hide_label(self):
        try:
            if self._lbl_win is not None:
                self._lbl_win.withdraw()
        except Exception:
            pass

    def _layout_borders(self):
        x, y, w, h = self.x, self.y, self.w, self.h
        t = _BORDER_W
        geo = {
            "top": (x - t, y - t, w + 2 * t, t),
            "bottom": (x - t, y + h, w + 2 * t, t),
            "left": (x - t, y - t, t, h + 2 * t),
            "right": (x + w, y - t, t, h + 2 * t),
        }
        for name, win in self._borders.items():
            gx, gy, gw, gh = geo[name]
            self._set_geo(win, "%dx%d+%d+%d" % (max(1, gw), max(1, gh), gx, gy))

        # 手柄中心：压在边框线带上（中心在边线上），箭头朝向随边/角。
        # 因手柄会伸入取景区，截图瞬间由 hide_dots()/show_dots() 隐藏恢复。
        t2 = _BORDER_W / 2.0
        half = _ARROW / 2
        centers = {
            "nw": (x - t2, y - t2),
            "ne": (x + w + t2, y - t2),
            "sw": (x - t2, y + h + t2),
            "se": (x + w + t2, y + h + t2),
            "mtop": (x + w / 2, y - t2),
            "mbottom": (x + w / 2, y + h + t2),
            "mleft": (x - t2, y + h / 2),
            "mright": (x + w + t2, y + h / 2),
        }
        for name, win in self._dots.items():
            cx, cy = centers[name]
            gx, gy = int(cx - half), int(cy - half)
            self._set_geo(win, "%dx%d+%d+%d" % (_ARROW, _ARROW, gx, gy))

        # 移动模式捕获层 + 中央徽标跟随区域（仅显示时才真正生效）
        if self._move_mode and self._inside_win is not None:
            try:
                self._layout_inside()
            except Exception:
                pass

    def hide_dots(self):
        """截图前隐藏手柄（中心压线后会伸入取景区）。"""
        for win in self._dots.values():
            try:
                win.withdraw()
            except Exception:
                pass

    def show_dots(self):
        for win in self._dots.values():
            try:
                win.deiconify()
            except Exception:
                pass

    def dots_visible(self):
        try:
            return all(w.winfo_viewable() for w in self._dots.values())
        except Exception:
            return False

    def hide_borders(self):
        for win in self._borders.values():
            try:
                win.withdraw()
            except Exception:
                pass

    def show_borders(self):
        for win in self._borders.values():
            try:
                win.deiconify()
            except Exception:
                pass

    # ---------------- 拖拽调整区域 ----------------
    def _drag_start(self, name, event):
        self._drag = {"name": name, "sx": event.x_root, "sy": event.y_root,
                      "region": (self.x, self.y, self.w, self.h),
                      "move": self._move_mode}

    def _drag_move(self, event):
        d = self._drag
        if not d:
            return
        dx = event.x_root - d["sx"]
        dy = event.y_root - d["sy"]
        x, y, w, h = d["region"]
        sw, sh = self._screen
        if d.get("move"):
            # 移动模式：整框平移（尺寸不变，不越屏）
            nx = max(0, min(x + dx, sw - w))
            ny = max(0, min(y + dy, sh - h))
            self._apply_region(nx, ny, w, h)
            return
        left, top, right, bottom = x, y, x + w, y + h
        name = d["name"]
        if name in _LEFT:
            left = max(0, min(x + dx, right - _MIN_W))
        if name in _RIGHT:
            right = min(sw, max(x + w + dx, left + _MIN_W))
        if name in _TOP:
            top = max(0, min(y + dy, bottom - _MIN_H))
        if name in _BOTTOM:
            bottom = min(sh, max(y + h + dy, top + _MIN_H))
        self._apply_region(left, top, right - left, bottom - top)

    def _drag_end(self, event):
        if not self._drag:
            return
        moved = self._drag.get("move")
        self._drag = None
        log("%s: %d×%d @ (%d,%d)" % ("取景框移动" if moved else "取景框调整",
                                    self.w, self.h, self.x, self.y))
        if self.on_resize:
            self.on_resize((self.x, self.y, self.w, self.h), True)

    def _apply_region(self, x, y, w, h):
        changed = (x, y, w, h) != (self.x, self.y, self.w, self.h)
        self.x, self.y, self.w, self.h = int(x), int(y), int(w), int(h)
        self._layout_borders()
        if changed:
            self._update_label()          # 拖拽中实时同步尺寸标签
        self._place_toolbar()
        if self.on_resize:
            self.on_resize((self.x, self.y, self.w, self.h), False)

    # ---------------- 工具条 ----------------
    def _build_toolbar(self):
        n = 5
        bar_w = (_PAD + _GRIP_W + _GAP + _COUNTER_W + _GAP
                 + n * (_BTN + _GAP) + _PAD - _GAP)
        bar_h = _PAD * 2 + _BTN
        self._bar_w, self._bar_h = bar_w, bar_h

        self.bar = tk.Toplevel(self.root)
        self.bar.overrideredirect(True)
        self.bar.attributes("-topmost", True)
        try:
            self.bar.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        self.bar.withdraw()                  # 先隐藏，布局完统一显示（防闪烁）
        self.bar.configure(bg=_KEY)
        self.bar.geometry("%dx%d+0+0" % (bar_w + 4, bar_h + 4))

        self.cv = tk.Canvas(self.bar, bg=_KEY, highlightthickness=0, bd=0,
                            width=bar_w + 4, height=bar_h + 4)
        self.cv.pack()

        # 浅色圆角条（白底不透明 + 浅灰描边）
        _round_rect(self.cv, 2, 2, bar_w + 2, bar_h + 2, r=12,
                    fill=_BAR_BG, outline=_BAR_LINE, width=1)

        cy = 2 + bar_h / 2

        # 六点拖拽把手（可移动整条工具栏，双击复位）
        gx0 = 2 + _PAD
        self._draw_grip(gx0, cy)

        # 把手与计数之间的分隔线
        sep1 = gx0 + _GRIP_W + _GAP / 2
        self.cv.create_line(sep1, 2 + _PAD + 2, sep1, 2 + bar_h - _PAD - 2,
                            fill=_SEP, width=1)

        # 计数
        cx0 = gx0 + _GRIP_W + _GAP
        self.counter = self.cv.create_text(
            cx0 + _COUNTER_W / 2, cy, text="0/%d" % self.max_count,
            fill=_COUNTER, font=_FONT_S,
        )
        # 计数与按钮之间的分隔线
        sep_x = cx0 + _COUNTER_W + _GAP / 2
        self.cv.create_line(sep_x, 2 + _PAD + 2, sep_x, 2 + bar_h - _PAD - 2,
                            fill=_SEP, width=1)

        step = _BTN + _GAP
        bx = cx0 + _COUNTER_W + _GAP + _BTN / 2
        self._draw_shot(bx, cy)
        self._draw_copy(bx + step, cy)
        self._draw_move(bx + step * 2, cy)
        self._draw_gear(bx + step * 3, cy)
        self._draw_exit(bx + step * 4, cy)
        try:
            winutil.make_tool_window(self.bar)   # 仅创建时一次，不进热路径
        except Exception:
            pass

    # ---------------- 图标（打包期生成的 PNG，失败回退矢量绘制） ----------------
    def _icon_photo(self, name, state):
        key = (name, state)
        if key in self._photos:
            return self._photos[key]
        photo = None
        p = ""
        try:
            p = paths.resource_path(os.path.join("assets", "ui",
                                                 "%s_%s.png" % (_ICON_FILE.get(name, name), state)))
            if os.path.exists(p):
                raw = tk.PhotoImage(master=self.cv, file=p)
                self._photos[(name, state, "#raw")] = raw
                photo = raw                # 素材即显示尺寸(32px)，直接使用
            else:
                log("图标文件不存在: %s" % p)
        except Exception as exc:
            log("图标加载失败 %s: %r" % (p, exc))
            photo = None
        self._photos[key] = photo
        return photo

    def _place_icon(self, cx, cy, name, tags, fallback):
        photo = self._icon_photo(name, "normal")
        if photo is not None:
            self._icon_items[name] = self.cv.create_image(
                cx, cy, image=photo, tags=tags + ("i_%s" % name,))
        else:
            self._icon_items[name] = None
            fallback()

    def _mk_btn(self, cx, cy, name, hover_color, press_color=None):
        tags = ("b_%s" % name,)
        bg_tag = "bg_%s" % name
        self._btns[name] = {"cx": cx, "cy": cy, "hover": hover_color,
                            "press": press_color or _BTN_PRESS}
        self._hover_on[name] = False
        half = _BTN / 2
        # 圆角方形底（默认与条同色，hover 变蓝，按下更深）
        _round_rect(self.cv, cx - half, cy - half, cx + half, cy + half,
                    r=_BTN_RADIUS, fill=_BAR_BG, outline="",
                    tags=tags + (bg_tag,))
        self.cv.tag_bind(tags, "<Enter>", lambda e, n=name: self._hover(n, True))
        self.cv.tag_bind(tags, "<Leave>", lambda e, n=name: self._hover(n, False))
        # 按下即给按压反馈；松开恢复（指针仍在按钮上则回到 hover 态）
        self.cv.tag_bind(tags, "<ButtonPress-1>",
                         lambda e, n=name: self._press(n, True))
        self.cv.tag_bind(tags, "<ButtonRelease-1>",
                         lambda e, n=name: self._press(n, False))
        return list(tags)

    def _draw_grip(self, gx0, cy):
        """六点拖拽把手：拖动移动整条工具栏，双击复位到默认锚点。"""
        gy0 = 2 + _PAD
        gy1 = 2 + self._bar_h - _PAD
        _round_rect(self.cv, gx0, gy0, gx0 + _GRIP_W, gy1, r=8,
                    fill=_GRIP_BG, outline="", tags=("grip", "gripbg"))
        gcx = gx0 + _GRIP_W / 2
        for dx in (-4, 4):
            for dy in (-7, 0, 7):
                self.cv.create_oval(gcx + dx - 1.8, cy + dy - 1.8,
                                    gcx + dx + 1.8, cy + dy + 1.8,
                                    fill=_GRIP_DOT, outline="", tags=("grip",))
        self.cv.tag_bind("grip", "<Enter>",
                         lambda e: self.cv.itemconfigure("gripbg", fill=_GRIP_HOVER))
        self.cv.tag_bind("grip", "<Leave>",
                         lambda e: self.cv.itemconfigure("gripbg", fill=_GRIP_BG))
        self.cv.tag_bind("grip", "<ButtonPress-1>", self._grip_press)
        self.cv.tag_bind("grip", "<B1-Motion>", self._grip_motion)
        self.cv.tag_bind("grip", "<ButtonRelease-1>", self._grip_release)
        self.cv.tag_bind("grip", "<Double-Button-1>", self._grip_reset)
        self.cv.tag_bind("grip", "<ButtonPress-1>",
                         lambda e: self.cv.itemconfigure("gripbg", fill=_BTN_PRESS),
                         add="+")
        self.cv.tag_bind("grip", "<ButtonRelease-1>",
                         lambda e: self.cv.itemconfigure("gripbg", fill=_GRIP_HOVER),
                         add="+")

    def _draw_shot(self, cx, cy):
        t = self._mk_btn(cx, cy, "shot", _BTN_HOVER)
        self._place_icon(cx, cy, "shot", tuple(t),
                         lambda: self._vec_shot(cx, cy, t + ["i_shot"]))

    def _draw_copy(self, cx, cy):
        t = self._mk_btn(cx, cy, "copy", _BTN_HOVER)
        self._place_icon(cx, cy, "copy", tuple(t),
                         lambda: self._vec_copy(cx, cy, t + ["i_copy"]))

    def _draw_gear(self, cx, cy):
        t = self._mk_btn(cx, cy, "gear", _BTN_HOVER)
        self._place_icon(cx, cy, "gear", tuple(t),
                         lambda: self._vec_gear(cx, cy, t + ["i_gear"]))

    def _draw_move(self, cx, cy):
        t = self._mk_btn(cx, cy, "move", _BTN_HOVER)
        self._place_icon(cx, cy, "move", tuple(t),
                         lambda: self._vec_move(cx, cy, t + ["i_move"]))

    def _draw_exit(self, cx, cy):
        t = self._mk_btn(cx, cy, "exit", _BTN_HOVER_EXIT,
                         press_color=_BTN_PRESS_EXIT)
        self._place_icon(cx, cy, "exit", tuple(t),
                         lambda: self._vec_exit(cx, cy, t + ["i_exit"]))

    # ----- 矢量回退（无 assets/ui 时） -----
    def _vec_shot(self, cx, cy, t):
        _round_rect(self.cv, cx - 8, cy - 4, cx + 8, cy + 7, r=2.5,
                    outline=_ICON, width=1.7, fill="", tags=t)
        _round_rect(self.cv, cx - 3.2, cy - 7.5, cx + 3.2, cy - 4, r=1.2,
                    outline=_ICON, width=1.7, fill="", tags=t)
        self.cv.create_oval(cx - 3.2, cy - 0.5, cx + 3.2, cy + 5.7,
                            outline=_ICON, width=1.7, fill="", tags=t)

    def _vec_copy(self, cx, cy, t):
        _round_rect(self.cv, cx - 7.5, cy - 7.5, cx + 3, cy + 3, r=2,
                    outline=_ICON, width=1.7, fill="", tags=t)
        _round_rect(self.cv, cx - 3, cy - 3, cx + 7.5, cy + 7.5, r=2,
                    outline=_ICON, width=1.7, fill="", tags=t)

    def _vec_gear(self, cx, cy, t):
        self.cv.create_oval(cx - 4.2, cy - 4.2, cx + 4.2, cy + 4.2,
                            outline=_ICON, width=1.7, fill="", tags=t)
        self.cv.create_oval(cx - 1.3, cy - 1.3, cx + 1.3, cy + 1.3,
                            outline=_ICON, width=1.5, fill=_ICON, tags=t)
        for k in range(8):
            a = math.radians(k * 45)
            self.cv.create_line(cx + 5.2 * math.cos(a), cy + 5.2 * math.sin(a),
                                cx + 8.0 * math.cos(a), cy + 8.0 * math.sin(a),
                                fill=_ICON, width=1.9, capstyle="round", tags=t)

    def _vec_exit(self, cx, cy, t):
        self.cv.create_line(cx - 5, cy - 5, cx + 5, cy + 5,
                            fill=_ICON, width=2.0, capstyle="round", tags=t)
        self.cv.create_line(cx + 5, cy - 5, cx - 5, cy + 5,
                            fill=_ICON, width=2.0, capstyle="round", tags=t)

    def _vec_move(self, cx, cy, t):
        """矢量回退：四向移动箭头。"""
        import math as _m
        self.cv.create_line(cx, cy - 8, cx, cy + 8, fill=_ICON, width=1.7, tags=t)
        self.cv.create_line(cx - 8, cy, cx + 8, cy, fill=_ICON, width=1.7, tags=t)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tx, ty = cx + dx * 8, cy + dy * 8
            self.cv.create_polygon(
                tx - dy * 3, ty - dx * 3, tx + dy * 3, ty + dx * 3,
                tx - dx * 4, ty - dy * 4, fill=_ICON, outline="", tags=t)

    # ---------------- 交互 ----------------
    def _set_icon(self, name, state):
        """state: normal / white / off"""
        it = self._icon_items.get(name)
        if it is not None:
            photo = self._icon_photo(name, state)
            if photo is not None:
                try:
                    self.cv.itemconfigure(it, image=photo)
                except Exception:
                    pass
            return
        color = {"normal": _ICON, "white": "#ffffff", "off": _ICON_OFF}.get(state, _ICON)
        for iid in self.cv.find_withtag("i_%s" % name):
            typ = self.cv.type(iid)
            try:
                if typ in ("polygon", "oval"):
                    self.cv.itemconfigure(iid, outline=color)
                    # 齿轮中心实心圆需同步 fill
                    if typ == "oval" and name == "gear":
                        coords = self.cv.coords(iid)
                        if abs(coords[2] - coords[0]) < 4:
                            self.cv.itemconfigure(iid, fill=color)
                else:  # line / text
                    self.cv.itemconfigure(iid, fill=color)
            except Exception:
                pass

    def _hover(self, name, on):
        self._hover_on[name] = on
        if name == "shot" and self._shot_disabled and on:
            return
        info = self._btns.get(name)
        if not info:
            return
        if on:
            self.cv.itemconfigure("bg_%s" % name, fill=info["hover"])
        elif name == "move" and self._move_mode:
            # 移动模式激活中：保持高亮（图标始终深色）
            self.cv.itemconfigure("bg_move", fill=_BTN_ACTIVE)
        else:
            self.cv.itemconfigure("bg_%s" % name, fill=_BAR_BG)
        # 图标不随 hover 变色（浅色底 + 深色图标方案）

    def _press(self, name, on):
        """按压交互：按下垫色加深，松开恢复并触发动作；图标保持深色。"""
        try:
            info = self._btns.get(name)
            if not info:
                return
            if on:
                if name == "shot" and self._shot_disabled:
                    self.flash_status("上限 %d" % self.max_count, ok=False)
                    return
                self.cv.itemconfigure("bg_%s" % name, fill=info["press"])
            else:
                if name == "move" and self._move_mode:
                    self.cv.itemconfigure("bg_move", fill=_BTN_ACTIVE)
                elif self._hover_on.get(name):
                    self.cv.itemconfigure("bg_%s" % name, fill=info["hover"])
                else:
                    self.cv.itemconfigure("bg_%s" % name, fill=_BAR_BG)
                if not (name == "shot" and self._shot_disabled):
                    self._click(name)
        except Exception:
            pass

    # ----- 六点把手：拖动移动工具条 -----
    def _grip_press(self, event):
        self._grip_drag = {"sx": event.x_root, "sy": event.y_root,
                           "bx": self.bar.winfo_rootx(), "by": self.bar.winfo_rooty()}

    def _grip_motion(self, event):
        d = self._grip_drag
        if not d:
            return
        sw, sh = self._screen
        bw, bh = self._bar_w + 4, self._bar_h + 4
        px = d["bx"] + (event.x_root - d["sx"])
        py = d["by"] + (event.y_root - d["sy"])
        px = max(0, min(px, sw - bw))
        py = max(0, min(py, sh - bh))
        self._set_geo(self.bar, "+%d+%d" % (px, py))
        self.toolbar_inside = self._toolbar_overlaps_region()

    def _grip_release(self, event):
        if self._grip_drag:
            self._grip_drag = None
            self._tb_custom = True
            log("工具条已移动到自定义位置")

    def _grip_reset(self, event):
        self._grip_drag = None
        self._tb_custom = False
        self._place_toolbar()
        log("工具条位置已复位")

    def _toolbar_overlaps_region(self):
        try:
            bx, by = self.bar.winfo_rootx(), self.bar.winfo_rooty()
            bw, bh = self._bar_w + 4, self._bar_h + 4
            return not (bx + bw <= self.x or bx >= self.x + self.w or
                        by + bh <= self.y or by >= self.y + self.h)
        except Exception:
            return False

    def _click(self, name):
        if name == "shot":
            if self._shot_disabled:
                self.flash_status("上限 %d" % self.max_count, ok=False)
                return
            if self.on_capture:
                self.on_capture()
        elif name == "copy" and self.on_copy:
            self.on_copy()
        elif name == "gear" and self.on_settings:
            self.on_settings()
        elif name == "move":
            self._set_move_mode(not self._move_mode)
        elif name == "exit" and self.on_exit:
            self.on_exit()

    # ---------------- 移动模式（拖任意位置=整框平移） ----------------
    def _set_move_mode(self, on):
        self._move_mode = bool(on)
        for name, win in list(self._borders.items()) + list(self._dots.items()):
            try:
                win.configure(cursor="fleur" if self._move_mode
                              else self._cursors.get(name, "arrow"))
            except Exception:
                pass
        if self._move_mode:
            # 开启：显示内部捕获窗 → 框内任意位置可拖动平移
            self._layout_inside()
            self.cv.itemconfigure("bg_move", fill=_BTN_ACTIVE)
            self.flash_status("可拖动")
        else:
            # 关闭：隐藏内部捕获窗，恢复框内点击穿透
            self._hide_inside()
            self.cv.itemconfigure("bg_move", fill=_BAR_BG)
        log("移动模式: %s" % ("开（框内任意位置可拖动平移）" if self._move_mode else "关"))

    def _make_inside(self):
        """移动模式捕获层：5% 淡色罩 + fleur 光标，鼠标不穿透，屏幕仍清晰可见。

        形态说明：色键透明像素会穿透鼠标（无法承载拖拽），alpha=0 也穿透；
        alpha 只要 ≥1/255 即可命中鼠标。这里用 alpha≈0.06 的极淡蓝罩：
        既能看见框内屏幕内容，又能整框拖动；中央另有一个移动徽标做视觉提示。"""
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=_INSIDE_TINT, cursor="fleur")
        try:
            win.attributes("-alpha", _INSIDE_ALPHA)
        except tk.TclError:
            pass
        win.withdraw()                               # 默认隐藏
        for seq, fn in (("<Button-1>", lambda e: self._drag_start("inside", e)),
                        ("<B1-Motion>", self._drag_move),
                        ("<ButtonRelease-1>", self._drag_end)):
            win.bind(seq, fn)
        try:
            winutil.make_tool_window(win)
        except Exception:
            pass
        return win

    def _make_inside_badge(self):
        """中央移动徽标：白色圆角卡片 + 蓝色四向箭头（小而不挡视线）。"""
        size = 84
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        win.configure(bg=_KEY, cursor="fleur")
        win.withdraw()
        cv = tk.Canvas(win, bg=_KEY, highlightthickness=0, bd=0,
                       width=size, height=size)
        cv.pack()
        _round_rect(cv, 1, 1, size - 1, size - 1, r=16,
                    fill="#ffffff", outline="#d7dbe2", width=1)
        cx = cy = size / 2
        s = 17
        lw = max(3, int(s * 0.17))
        arm, ah, aw = s * 0.62, s * 0.5, s * 0.36
        cv.create_line(cx, cy - arm, cx, cy + arm, fill=_INSIDE_GLYPH,
                       width=lw, capstyle="round")
        cv.create_line(cx - arm, cy, cx + arm, cy, fill=_INSIDE_GLYPH,
                       width=lw, capstyle="round")
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tx, ty = cx + dx * s, cy + dy * s
            cv.create_polygon(tx - dy * aw, ty - dx * aw,
                              tx + dy * aw, ty + dx * aw,
                              tx - dx * ah, ty - dy * ah,
                              fill=_INSIDE_GLYPH, outline="")
        for target in (win, cv):
            target.bind("<Button-1>", lambda e: self._drag_start("inside", e))
            target.bind("<B1-Motion>", self._drag_move)
            target.bind("<ButtonRelease-1>", self._drag_end)
        try:
            winutil.make_tool_window(win)
        except Exception:
            pass
        self._inside_badge_size = size
        return win

    def _layout_inside(self):
        win = self._inside_win
        if win is None:
            return
        self._set_geo(win, "%dx%d+%d+%d" % (max(1, self.w), max(1, self.h),
                                           self.x, self.y))
        try:
            win.deiconify()
            win.lift()
        except Exception:
            pass
        badge = getattr(self, "_inside_badge", None)
        if badge is not None:
            bs = getattr(self, "_inside_badge_size", 84)
            bx = int(self.x + self.w / 2 - bs / 2)
            by = int(self.y + self.h / 2 - bs / 2)
            self._set_geo(badge, "%dx%d+%d+%d" % (bs, bs, bx, by))
            try:
                badge.deiconify()
                badge.lift()
            except Exception:
                pass

    def _hide_inside(self):
        for win in (self._inside_win, getattr(self, "_inside_badge", None)):
            if win is not None:
                try:
                    win.withdraw()
                except Exception:
                    pass
                self._geo_cache.pop(win, None)   # 重新显示时允许重新布局

    def mark_copied(self):
        """复制成功：解除截图上限禁用，计数显示归 0 —— 下一次截图即开启新一轮。

        会话缓冲不清空：在点击「截图」之前仍可重复点「复制」（复制同一张长图）。
        """
        self._last_count = 0
        self._shot_disabled = False
        try:
            self.cv.itemconfigure(self.counter, text="0/%d" % self.max_count,
                                  fill=_COUNTER)
            self._set_icon("shot", "normal")
        except Exception:
            pass

    # ---------------- 布局 ----------------
    def _place_toolbar(self):
        """热路径优化：不再 per-move 调 update_idletasks / make_tool_window（这两者
        会强制同步刷新与改窗口样式，是拖拽卡顿主因）；仅设置 geometry。"""
        bw, bh = self._bar_w + 4, self._bar_h + 4
        sw, sh = self._screen
        if self._tb_custom:
            # 用户拖过把手：保持自定义位置，仅夹在屏幕内
            px, py = self.bar.winfo_x(), self.bar.winfo_y()
            px = max(0, min(px, sw - bw))
            py = max(0, min(py, sh - bh))
            self._set_geo(self.bar, "+%d+%d" % (px, py))
            self.toolbar_inside = self._toolbar_overlaps_region()
            return
        x, y, w, h = self.x, self.y, self.w, self.h
        px, py = x + w - bw, y + h + 12
        self.toolbar_inside = False
        if py + bh > sh:
            py = y - bh - 12
        if py < 0:
            py = y + h - bh - 6
            self.toolbar_inside = True
        px = max(0, min(px, sw - bw))
        py = max(0, min(py, sh - bh))
        self._set_geo(self.bar, "+%d+%d" % (px, py))

    # ---------------- 对外 ----------------
    def get_region(self):
        return (self.x, self.y, self.w, self.h)

    def hide_toolbar(self):
        try:
            self.bar.withdraw()
        except Exception:
            pass

    def show_toolbar(self):
        try:
            self.bar.deiconify()
        except Exception:
            pass

    def update_count(self, n):
        self._last_count = n
        full = n >= self.max_count
        self._shot_disabled = full
        try:
            self.cv.itemconfigure(self.counter, text="%d/%d" % (n, self.max_count))
            if full:
                self.cv.itemconfigure("bg_shot", fill=_BAR_BG)
                self._set_icon("shot", "off")
            else:
                self._set_icon("shot", "normal")
        except Exception:
            pass

    def set_max_count(self, n):
        self.max_count = int(n)
        self.update_count(self._last_count)

    def flash_status(self, text, ok=True, ms=1400):
        try:
            self.cv.itemconfigure(self.counter, text=text[:10],
                                  fill="#12a150" if ok else "#e5484d")
            self.bar.after(ms, self._restore_counter)
        except Exception:
            pass

    def _restore_counter(self):
        try:
            self.cv.itemconfigure(self.counter,
                                  text="%d/%d" % (self._last_count, self.max_count),
                                  fill=_COUNTER)
        except Exception:
            pass

    # ---------------- 浮动提示 ----------------
    def toast(self, text, ok=True, ms=2400):
        """在工具条上方弹一条完整提示（自动换行，不截断）。"""
        self.hide_toast()
        if not text:
            return
        try:
            f = tkfont.Font(font=_TOAST_FONT)
        except Exception:
            f = None
        maxw = _TOAST_MAX_W
        lines = [text]
        if f is not None and f.measure(text) > maxw:
            lines, cur = [], ""
            for ch in text:
                if not cur or f.measure(cur + ch) <= maxw:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
            if cur:
                lines.append(cur)
            lines = lines[:3]

        tw = max((f.measure(l) if f is not None else len(l) * 9) for l in lines)
        w = max(120, tw + 44)
        h = 20 + 18 * len(lines)

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        win.configure(bg=_KEY)
        cv = tk.Canvas(win, width=w + 4, height=h + 4, bg=_KEY,
                       highlightthickness=0, bd=0)
        cv.pack()
        _round_rect(cv, 2, 2, w + 2, h + 2, r=9, fill=_TOAST_BG, outline="")
        cy = 2 + h / 2
        cv.create_oval(14, cy - 3.5, 21, cy + 3.5,
                       fill=_TOAST_OK if ok else _TOAST_ERR, outline="")
        for i, line in enumerate(lines):
            cv.create_text(30, 12 + i * 18, anchor="nw", text=line,
                           fill=_TOAST_FG, font=_TOAST_FONT)

        self.bar.update_idletasks()
        bx, by = self.bar.winfo_rootx(), self.bar.winfo_rooty()
        bw, bh = self.bar.winfo_width(), self.bar.winfo_height()
        sw, sh = self._screen
        px = bx + (bw - (w + 4)) // 2

        def hits_frame(x, y):
            return not (x + w + 4 <= self.x or x >= self.x + self.w or
                        y + h + 4 <= self.y or y >= self.y + self.h)

        below = by + bh + 12
        above = by - h - 16
        if below + h + 4 <= sh and not hits_frame(px, below):
            py = below
        elif above >= 0 and not hits_frame(px, above):
            py = above
        else:
            py = below if below + h + 4 <= sh else above
        px = max(0, min(px, sw - w - 4))
        py = max(0, min(py, sh - h - 4))
        win.geometry("%dx%d+%d+%d" % (w + 4, h + 4, px, py))
        self._toast_win = win
        try:
            win.after(ms, lambda: self._expire_toast(win))
        except Exception:
            pass

    def _expire_toast(self, win):
        if getattr(self, "_toast_win", None) is win:
            self.hide_toast()

    def hide_toast(self):
        win = getattr(self, "_toast_win", None)
        self._toast_win = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def destroy(self):
        self.hide_toast()
        wins = [getattr(self, "bar", None), getattr(self, "_lbl_win", None),
                getattr(self, "_inside_win", None),
                getattr(self, "_inside_badge", None)]
        wins.extend(getattr(self, "_borders", {}).values())
        wins.extend(getattr(self, "_dots", {}).values())
        for win in wins:
            try:
                if win is not None:
                    win.destroy()
            except Exception:
                pass
        self._borders = {}
        self._dots = {}
        self._dot_img = None
        self._dot_raw = None