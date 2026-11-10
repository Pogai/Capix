# -*- coding: utf-8 -*-
"""主面板 + 整体编排（托盘后台 + 懒加载预览 + 设置）。

交互：
  托盘左键/热键 → 框选 → 取景框 + 工具条[计数][截图][复制][设置][✕]
  首次截图 → 出现框侧长图预览窗（可缩放/滚轮/拖拽），并随截图刷新
  复制 → 长图入剪贴板+存档；不立即清零（支持多次复制），
         下一次截图时才从 0 开始新一轮拼接
  设置 → 参数对话框（最大截图张数 1~20，默认 20，即时生效并持久化）
  ✕  → 退出取景回托盘
"""

import queue
import threading
import time
import tkinter as tk
import os

from . import region, frame, preview, paths
from .logsetup import log, error as log_error

_FONT = ("Microsoft YaHei UI", 10)
_FONT_BIG = ("Microsoft YaHei UI", 13, "bold")
_FONT_S = ("Microsoft YaHei UI", 9)

# 预览源图宽度上限（越长越大，用宽度封顶控制内存；显示端按视口渲染）
_PREVIEW_MAX_WIDTH = 1000

# 浅色风色板（与工具栏同风格：白底、浅描边、蓝主色）
_C_BG = "#ffffff"        # 窗底白
_C_TITLE = "#14181f"     # 标题深色
_C_SUB = "#6b7280"       # 副文灰
_C_LINE = "#e8ebf0"      # 分隔线
_C_BOX = "#f1f3f7"       # 步进器底
_C_BOX_LINE = "#e2e6ee"
_C_BOX_HOVER = "#e7eefb"
_C_ACCENT = "#3388ff"    # 主色 = 边框蓝
_C_ACCENT_HOVER = "#2a77e6"
_C_ACCENT_PRESS = "#1f66cc"
_C_GHOST_HOVER = "#eceff4"
_C_TXT_MAIN = "#374151"


def _rr(cv, x0, y0, x1, y1, r=9, **kw):
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return cv.create_polygon(pts, smooth=True,
                             outline=kw.pop("outline", ""),
                             width=kw.pop("width", 1), **kw)


class SettingsDialog:
    """参数设置对话框（浅色简约风，与工具栏同风格；托盘模式下也能弹出）。"""

    W, H = 380, 252

    def __init__(self, root, ctrl, on_saved=None):
        self.ctrl = ctrl
        self.on_saved = on_saved
        try:
            self._val = max(1, min(20, int(ctrl.max_shots)))
        except Exception:
            self._val = 20

        self.win = tk.Toplevel(root)
        self.win.title("参数设置")
        self.win.resizable(False, False)
        self.win.configure(bg=_C_BG)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)
        # 窗口图标：用户提供的拼图图标
        try:
            ico = paths.resource_path(os.path.join("assets", "icon.ico"))
            if os.path.exists(ico):
                self.win.iconbitmap(ico)
        except Exception:
            pass

        self.cv = tk.Canvas(self.win, width=self.W, height=self.H, bg=_C_BG,
                            highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)

        self._draw()

        self.win.bind("<Escape>", lambda e: self._cancel())
        self.win.bind("<Return>", lambda e: self._save())
        self.win.bind("<KP_Enter>", lambda e: self._save())
        self.win.bind("<Up>", lambda e: self._step(1))
        self.win.bind("<Down>", lambda e: self._step(-1))

        # 先让窗口完成布局/映射，再定位、置顶、抓取，避免 grab 失败或不可见
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        self.win.geometry("+%d+%d" % ((sw - w) // 2, max(60, (sh - h) // 3)))
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.win.after(30, self._grab)
        try:
            self.cv.focus_set()
        except Exception:
            pass

    # ---------- 绘制 ----------
    def _draw(self):
        cv = self.cv
        # 顶部标题区（带主色小竖条，与工具栏蓝呼应）
        cv.create_rectangle(24, 24, 28, 44, fill=_C_ACCENT, outline="")
        cv.create_text(36, 33, text="参数设置", anchor="w",
                       font=("Microsoft YaHei UI", 13, "bold"), fill=_C_TITLE)
        cv.create_text(36, 55, text="调整本轮连续截图的上限", anchor="w",
                       font=("Microsoft YaHei UI", 9), fill=_C_SUB)
        cv.create_line(24, 78, self.W - 24, 78, fill=_C_LINE)

        # 步进器行
        cv.create_text(24, 112, text="单次最大截图张数", anchor="w",
                       font=("Microsoft YaHei UI", 10), fill=_C_TXT_MAIN)
        self._stepper()

        cv.create_text(24, 152, anchor="w",
                       text="范围 1 ~ 20，默认 20；保存后立即生效。",
                       font=("Microsoft YaHei UI", 8), fill="#9aa1ad")

        self._button(184, 196, 262, 230, "取消", False, "cancel")
        self._button(274, 196, 356, 230, "保存", True, "save")

    def _stepper(self):
        cv = self.cv
        # 数值大号显示
        cv.create_text(248, 112, text="", anchor="center")  # 占位保持布局稳定
        self._txt_val = cv.create_text(250, 112, text=str(self._val), anchor="center",
                                       font=("Consolas", 15, "bold"), fill=_C_TITLE)
        for tag, x0, glyph in (("minus", 286, "−"), ("plus", 324, "+")):
            x1 = x0 + 32
            fill0 = _C_ACCENT if tag == "plus" else _C_TXT_MAIN
            cv.create_text((x0 + x1) / 2, 112, text=glyph, fill=fill0,
                           font=("Segoe UI", 13), tags=("s_%s" % tag,))
            # 点击热区（透明块）
            cv.create_rectangle(x0 - 2, 96, x1 + 2, 128, fill="", outline="",
                                tags=("s_%s" % tag, "sbg_%s" % tag))
            cv.tag_lower("sbg_%s" % tag)
            cv.tag_bind("s_%s" % tag, "<Enter>",
                        lambda e, t=tag: cv.itemconfigure(
                            "s_%s" % t, fill=_C_ACCENT))
            cv.tag_bind("s_%s" % tag, "<Leave>",
                        lambda e, t=tag, c=fill0: cv.itemconfigure(
                            "s_%s" % t, fill=c))
            cv.tag_bind("s_%s" % tag, "<Button-1>",
                        lambda e, d=(1 if tag == "plus" else -1): self._step(d))

    def _button(self, x0, y0, x1, y1, text, primary, tag):
        cv = self.cv
        bg = _C_ACCENT if primary else "#ffffff"
        fg = "#ffffff" if primary else _C_TXT_MAIN
        line = _C_ACCENT if primary else "#dfe3ea"
        hover = _C_ACCENT_HOVER if primary else _C_GHOST_HOVER
        press = _C_ACCENT_PRESS if primary else _C_BOX_HOVER
        _rr(cv, x0, y0, x1, y1, r=9, fill=bg, outline=line, width=1,
            tags=("btn_%s" % tag, "bbg_%s" % tag))
        cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text, fill=fg,
                       font=("Microsoft YaHei UI", 10), tags=("btn_%s" % tag,))
        cv.tag_bind("btn_%s" % tag, "<Enter>",
                    lambda e, t=tag, c=hover: cv.itemconfigure("bbg_%s" % t, fill=c))
        cv.tag_bind("btn_%s" % tag, "<Leave>",
                    lambda e, t=tag, c=bg: cv.itemconfigure("bbg_%s" % t, fill=c))
        cv.tag_bind("btn_%s" % tag, "<ButtonPress-1>",
                    lambda e, t=tag, c=press: cv.itemconfigure("bbg_%s" % t, fill=c))
        cv.tag_bind("btn_%s" % tag, "<ButtonRelease-1>",
                    lambda e, n=tag: self._save() if n == "save" else self._cancel())

    # ---------- 逻辑 ----------
    def _step(self, delta):
        self._set_val(self._val + delta)

    def _set_val(self, v):
        self._val = max(1, min(20, int(v)))
        try:
            self.cv.itemconfigure(self._txt_val, text=str(self._val))
        except Exception:
            pass

    def _grab(self):
        try:
            self.win.grab_set()
        except Exception:
            pass

    def _clamp_now(self):
        try:
            self._set_val(self._val)
        except Exception:
            pass

    def _save(self):
        v = max(1, min(20, int(self._val)))
        self.ctrl.set_max_shots(v)
        if self.on_saved:
            try:
                self.on_saved(v)
            except Exception:
                log_error("设置保存回调异常", exc_info=True)
        self.win.destroy()

    def _cancel(self):
        self.win.destroy()


class App:
    def __init__(self, root, ctrl, hotkey_hints):
        self.root = root
        self.ctrl = ctrl
        self.hints = hotkey_hints
        self.overlay = None
        self.preview = None
        self._region = None            # 当前取景区域（预览懒加载用）
        self._selecting = False
        self._last_select_ts = 0.0
        self._settings = None
        self.tray = None
        self.tray_mode = False
        self._prev_seq = 0
        self._prev_lock = threading.Lock()

        self._build_panel()
        self.root.withdraw()
        self.root.after(120, self._poll)

    # ---------- 主面板（托盘不可用兜底） ----------
    def _build_panel(self):
        self.root.title("固定框连续截图")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f6f8")
        wrap = tk.Frame(self.root, bg="#f5f6f8", padx=16, pady=14)
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="固定框连续截图", font=_FONT_BIG,
                 bg="#f5f6f8", fg="#111827").pack(anchor="w")
        tk.Label(wrap, text="点击开始框选，拖出要连续截图的区域。\n"
                            "框选后框内可正常操作（如点“下一题”），点右下角「截图」。",
                 font=_FONT, bg="#f5f6f8", fg="#4b5563", justify="left"
                 ).pack(anchor="w", pady=(6, 10))
        tk.Button(wrap, text="开始框选区域   (Ctrl+Shift+R)", command=self.start_selection,
                  font=("Microsoft YaHei UI", 11, "bold"), bg=_C_ACCENT, fg="white",
                  activebackground=_C_ACCENT_HOVER, activeforeground="white",
                  relief="flat", padx=16, pady=8, cursor="hand2").pack(fill="x")

        row = tk.Frame(wrap, bg="#f5f6f8")
        row.pack(fill="x", pady=(10, 4))
        tk.Button(row, text="打开截图目录", command=self.ctrl.open_output_dir,
                  font=_FONT, relief="flat", bg="#e5e7eb", padx=10, pady=3
                  ).pack(side="left")
        tk.Button(row, text="参数设置", command=self.open_settings,
                  font=_FONT, relief="flat", bg="#e5e7eb", padx=10, pady=3
                  ).pack(side="left", padx=(6, 0))
        tk.Button(row, text="退出程序", command=self.request_quit,
                  font=_FONT, relief="flat", bg="#e5e7eb", padx=10, pady=3
                  ).pack(side="right")

        tips = "\n".join("%s  ——  %s" % (k, v) for k, v in self.hints)
        tk.Label(wrap, text=tips, font=_FONT_S, bg="#f5f6f8", fg="#6b7280",
                 justify="left").pack(anchor="w", pady=(8, 4))
        self.panel_status = tk.Label(wrap, text="就绪", font=_FONT_S, bg="#eef2ff",
                                     fg="#4338ca", anchor="w", padx=8, pady=4)
        self.panel_status.pack(fill="x", pady=(6, 0))

    def _panel_msg(self, text, ok=True):
        try:
            self.panel_status.config(text=text, fg="#4338ca" if ok else "#dc2626")
        except Exception:
            pass

    def _notify(self, title, text):
        if self.tray_mode and self.tray is not None:
            try:
                self.tray.notify(title, text)
            except Exception:
                pass

    # ---------- 设置 ----------
    def open_settings(self):
        try:
            if self._settings is not None:
                try:
                    if self._settings.win.winfo_exists():
                        self._settings.win.deiconify()
                        self._settings.win.lift()
                        self._settings.win.focus_force()
                        return
                except Exception:
                    pass
            self._settings = SettingsDialog(
                self.root, self.ctrl, on_saved=self._on_settings_saved
            )
            log("打开设置对话框")
        except Exception:
            log_error("打开设置对话框失败", exc_info=True)

    def _on_settings_saved(self, v):
        if self.overlay is not None:
            try:
                self.overlay.set_max_count(v)
            except Exception:
                pass
        self._panel_msg("最大截图张数已设为 %d" % v)

    # ---------- 框选 -> 取景框（预览延迟到首次截图） ----------
    def start_selection(self):
        if self._selecting:
            return
        self._selecting = True
        try:
            self._close_overlay()
            self.root.withdraw()
            self.root.update_idletasks()
            sel = region.select_region(self.root)
            if not sel:
                if not self.tray_mode:
                    self.root.deiconify()
                self._panel_msg("已取消框选")
                return
            self._region = sel
            self.ctrl.begin_session(sel)
            self.overlay = frame.FrameOverlay(
                self.root, sel,
                on_capture=self.on_capture,
                on_copy=self.on_copy,
                on_exit=self.on_exit,
                on_settings=self.open_settings,
                max_count=self.ctrl.max_shots,
                on_resize=self.on_region_changed,
            )
            self.overlay.update_count(0)
            # 预览不在此创建（首次截图后再出现）
            self._panel_msg("取景中：%s（框内可正常操作）" % self.ctrl.fmt_region(sel))
        finally:
            self._selecting = False

    def on_region_changed(self, region, final=False):
        """取景框拖拽调整后：同步控制器/预览位置，松手时记日志。"""
        self._region = region
        try:
            self.ctrl.update_region(region)
        except Exception:
            log_error("同步取景区域失败", exc_info=True)
        if self.preview is not None:
            try:
                self.preview.move_to(region)
            except Exception:
                log_error("预览窗跟随取景框失败", exc_info=True)
        if final:
            msg = "取景区域已调整：%s" % self.ctrl.fmt_region(region)
            log(msg)
            self._panel_msg(msg)
            size = self.ctrl.get_session_size()
            if size and size[0] != int(region[2]) and self.ctrl.get_session_count() > 0:
                warn = "新宽度与已截图片不同：长图按最大宽度拼接，较窄的右侧留底色"
                log(warn)
                if self.overlay is not None:
                    try:
                        self.overlay.toast(warn, ok=True, ms=3200)
                    except Exception:
                        pass
                self._notify("取景宽度已改变", warn)

    def _ensure_preview(self):
        """首次截图后才创建预览窗。"""
        if self.preview is None and self._region is not None:
            try:
                self.preview = preview.PreviewWindow(self.root, self._region)
            except Exception:
                log_error("创建预览窗失败", exc_info=True)
                self.preview = None

    def _close_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None
        if self.preview is not None:
            try:
                self.preview.destroy()
            except Exception:
                pass
            self.preview = None
        self._region = None
        try:
            self.ctrl.end_session()
        except Exception:
            pass

    def on_capture(self):
        if self.overlay is None:
            self._panel_msg("当前没有取景框", ok=False)
            return
        try:
            self.overlay.hide_toast()      # 提示不得被截进画面
            self.overlay.hide_dots()       # 手柄压线会伸入取景区 → 截图瞬间隐藏
            # 移动模式的内部捕获窗：截图期间隐藏，保证框内点击行为正常
            if getattr(self.overlay, "_move_mode", False):
                self.overlay._hide_inside()
        except Exception:
            pass
        inside = getattr(self.overlay, "toolbar_inside", False)
        if inside:
            self.overlay.hide_toolbar()
            self.root.update_idletasks()
            time.sleep(0.03)
        try:
            self.ctrl.capture_session("按钮")
        finally:
            if inside:
                self.overlay.show_toolbar()
            try:
                self.overlay.show_dots()
                if getattr(self.overlay, "_move_mode", False):
                    self.overlay._layout_inside()
            except Exception:
                pass

    def on_copy(self):
        if self.overlay is None:
            self._panel_msg("当前没有取景框", ok=False)
            return
        self.ctrl.copy_long_image()

    def on_exit(self):
        self._close_overlay()
        if not self.tray_mode:
            try:
                self.root.deiconify()
            except Exception:
                pass
        self._panel_msg("已退出取景，可重新框选")
        self._notify("固定框连续截图", "已退出框选，仍在后台运行。点托盘图标可再次框选。")

    # ---------- 预览源刷新（后台算快照，主线程贴图） ----------
    def _refresh_preview_async(self):
        with self._prev_lock:
            self._prev_seq += 1
            seq = self._prev_seq

        def worker():
            try:
                res = self.ctrl.stitch_snapshot(_PREVIEW_MAX_WIDTH)
            except Exception:
                log_error("生成预览快照失败", exc_info=True)
                res = None
            with self._prev_lock:
                if seq != self._prev_seq:
                    return
            if res is not None:
                self.ctrl.events.put(("preview_src", res[0], res[1], res[2]))

        threading.Thread(target=worker, name="preview", daemon=True).start()

    # ---------- 事件轮询 ----------
    def _poll(self):
        try:
            while True:
                ev = self.ctrl.events.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "request_select":
            now = time.time()
            if now - self._last_select_ts < 0.8:
                return
            self._last_select_ts = now
            self.start_selection()
        elif kind == "request_capture":
            self.on_capture()
        elif kind == "request_settings":
            self.open_settings()
        elif kind == "request_quit":
            self.request_quit()
        elif kind == "captured":
            cnt = ev[1]
            if self.overlay:
                self.overlay.update_count(cnt)
                self.overlay.flash_status("已截 %d" % cnt)
            self._ensure_preview()       # 首次截图才显示预览
            self._panel_msg("已截图，共 %d 张（本轮）" % cnt)
            self._refresh_preview_async()
        elif kind == "preview_src":
            _, w, h, rgb = ev
            if self.preview is not None:
                try:
                    self.preview.set_source(w, h, rgb)
                except Exception:
                    log_error("预览贴图失败", exc_info=True)
        elif kind == "copied":
            w, h, saved = ev[1], ev[2], ev[3]
            if self.overlay:
                self.overlay.flash_status("已复制")
                # 复制后解锁截图上限：下一次截图自动开启新一轮拼接
                # （在此之前仍可重复复制同一张长图）
                try:
                    self.overlay.mark_copied()
                except Exception:
                    log_error("复制后复位计数失败", exc_info=True)
            msg = "长图已复制到剪贴板（%dx%d）" % (w, h)
            if saved:
                msg += "，并已保存：%s" % saved
            self._panel_msg(msg)
            self._notify("长图已复制", "%dx%d 已复制到剪贴板" % (w, h))
            # 不回滚计数/预览：可继续多次复制；下次截图时才从 0 重新拼接
        elif kind == "error":
            msg = ev[1]
            if self.overlay is not None:
                try:
                    self.overlay.toast(msg, ok=False, ms=3200)
                except Exception:
                    log_error("显示提示失败", exc_info=True)
            self._panel_msg(msg, ok=False)
            self._notify("提示", msg)
        elif kind == "limit":
            n = ev[1]
            msg = "已达单次上限 %d 张。点「复制」后继续截图会重新拼接；或按 Ctrl+Shift+R 重新框选。" % n
            if self.overlay is not None:
                try:
                    self.overlay.flash_status("上限 %d" % n, ok=False)
                    self.overlay.toast("已达单次上限 %d 张" % n, ok=False, ms=3200)
                except Exception:
                    pass
            self._panel_msg(msg, ok=False)
            self._notify("已达上限", "本轮已截满 %d 张" % n)
        elif kind == "log":
            self._panel_msg(ev[1])

    def request_quit(self):
        if getattr(self, "on_quit", None):
            self.on_quit()