# -*- coding: utf-8 -*-
"""核心控制器（会话模型）。

一次框选 = 一个会话：会话内多次截图累积，可纵向拼接成长图并复制到剪贴板。
- 最大截图张数可配置（settings，默认 20，范围 1~20），保存即时生效。
- 点「复制」成功后清空本会话拼接缓冲（下轮截图从 0 重新拼接），
  取景框与全局文件编号保留。
- build_preview 供预览窗使用（可在后台线程调用）。
"""

import os
import queue
import threading
import time

from . import capture, png, stitch, clipboard, settings
from .thumb import scale_fit
from .logsetup import log, error as log_error

_PREFIX = "题"

# 兼容旧引用（现在实际上限动态来自 settings）
MAX_SESSION_SHOTS = settings.DEFAULTS["max_shots"]


class Controller:
    def __init__(self, output_dir: str, max_shots: int = None):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._region = None          # (x, y, w, h)
        self._session = []           # [(w, h, rgb), ...] 当前会话截图
        self._session_count = 0
        self._global_counter = 0     # 全局文件编号（跨会话递增，防覆盖）
        self._pending_reset = False  # 复制后置 True；下一次截图时先清零
        self.events = queue.Queue()

        if max_shots is None:
            max_shots = settings.load()["max_shots"]
        self.max_shots = settings._clamp(max_shots)

        self._resume_counter()

    # ---------- 内部 ----------
    def _resume_counter(self):
        maxn = 0
        try:
            for name in os.listdir(self.output_dir):
                if name.startswith(_PREFIX) and name.endswith(".png"):
                    stem = name[len(_PREFIX):-4]
                    if stem.isdigit():
                        maxn = max(maxn, int(stem))
        except OSError:
            pass
        self._global_counter = maxn

    # ---------- 状态 ----------
    def get_region(self):
        with self._lock:
            return self._region

    def get_session_count(self):
        with self._lock:
            return self._session_count

    def get_session_size(self):
        """当前会话首张截图的 (w, h)，没有则 None。"""
        with self._lock:
            if not self._session:
                return None
            w, h, _rgb = self._session[0]
            return (w, h)

    def get_global_counter(self):
        with self._lock:
            return self._global_counter

    @staticmethod
    def fmt_region(region):
        if not region:
            return "未框选"
        x, y, w, h = region
        return "(%d, %d)  %d × %d" % (x, y, w, h)

    # ---------- 设置 ----------
    def set_max_shots(self, n):
        """更新最大张数（clamp 1~20）并持久化。"""
        old = self.max_shots
        self.max_shots = settings._clamp(n)
        path = settings.save({"max_shots": self.max_shots})
        log("设置 max_shots: %s -> %s (%s)" % (old, self.max_shots, path))
        self.events.put(("log", "最大截图张数已设为 %d" % self.max_shots))
        return self.max_shots

    # ---------- 会话 ----------
    def begin_session(self, region):
        """开始新会话（新框选）：设置区域并清空上一会话截图。"""
        with self._lock:
            self._region = tuple(int(v) for v in region)
            self._session = []
            self._session_count = 0
        self.events.put(("log", "已框选区域 %s" % self.fmt_region(region)))

    def end_session(self):
        with self._lock:
            self._region = None

    def update_region(self, region):
        """拖拽调整取景框后同步截图区域（保留已截内容）。"""
        with self._lock:
            self._region = tuple(int(v) for v in region)

    def reset_session_buffer(self):
        """清空拼接缓冲（复制成功后调用）：计数归 0，区域与文件编号保留。"""
        with self._lock:
            self._session = []
            self._session_count = 0
        log("会话拼接缓冲已重置")

    def capture_session(self, source="按钮"):
        """截取当前区域，加入会话并保存单张文件。返回是否成功。"""
        with self._lock:
            region = self._region
            if self._pending_reset:
                # 上轮已复制过：本张作为新一轮的第 1 张（此时才回滚计数）
                self._session = []
                self._session_count = 0
                self._pending_reset = False
            count = self._session_count
        if region is None:
            self.events.put(("error", "当前没有取景框，请先框选区域"))
            return False
        if count >= self.max_shots:
            self.events.put(("limit", self.max_shots))
            return False

        try:
            x, y, w, h = region
            rgb = capture.capture_rgb(x, y, w, h)
        except Exception as exc:
            log_error("截图失败: %r" % exc, exc_info=True)
            return_error = "截图失败：%s" % exc
            self.events.put(("error", return_error))
            return False

        with self._lock:
            self._session.append((w, h, rgb))
            self._session_count += 1
            self._global_counter += 1
            num = self._global_counter
            cnt = self._session_count

        # 另存单张，便于单独查看
        path = os.path.join(self.output_dir, "%s%d.png" % (_PREFIX, num))
        try:
            with open(path, "wb") as fh:
                fh.write(png.encode_rgb(w, h, rgb))
        except OSError as exc:
            self.events.put(("error", "保存单张失败：%s" % exc))

        self.events.put(("captured", cnt, path, source))
        log("截图 #%d 已保存: %s (%dx%d)" % (num, path, w, h))
        return True

    # ---------- 拼接 / 复制 ----------
    def stitch_image(self):
        with self._lock:
            imgs = list(self._session)
        return stitch.stitch_vertical(imgs)

    def build_preview(self, max_w: int, max_h: int):
        """（旧接口）拼接长图 -> 等比 fit 缩略 -> PNG bytes。"""
        st = self.stitch_image()
        if not st:
            return None
        w, h, rgb = st
        tw, th, trgb = scale_fit(w, h, rgb, max_w, max_h)
        return tw, th, png.encode_rgb(tw, th, trgb)

    def stitch_snapshot(self, max_width: int = 1000):
        """供预览窗使用的源图（按宽度上限缩放，保持长图全貌）。"""
        st = self.stitch_image()
        if not st:
            return None
        w, h, rgb = st
        if w > max_width:
            tw, th, trgb = scale_fit(w, h, rgb, max_width, 10 ** 9)
            return tw, th, trgb
        return w, h, rgb

    def copy_long_image(self):
        """拼接长图 -> 复制到剪贴板 -> 标记下轮重置（可多次复制）。"""
        with self._lock:
            imgs = list(self._session)
        if imgs:
            widths = sorted({w for w, _h, _rgb in imgs})
            if len(widths) > 1:
                log("长图拼接: 宽度不一致 %s, 按最大宽度拼接(较窄的右侧留底色)" % widths)
        st = stitch.stitch_vertical(imgs)
        if not st:
            self.events.put(("error", "还没有任何截图，无法复制长图"))
            return False
        width, height, rgb = st

        saved = None
        try:
            saved = os.path.join(
                self.output_dir, "%s长图_%s.png" % (_PREFIX, time.strftime("%H%M%S"))
            )
            with open(saved, "wb") as fh:
                fh.write(png.encode_rgb(width, height, rgb))
        except OSError:
            saved = None

        try:
            clipboard.copy_image(width, height, rgb)
            self.events.put(("copied", width, height, saved))
            log("长图已复制: %dx%d, 保存=%s" % (width, height, saved))
        except Exception as exc:
            log_error("复制到剪贴板失败: %r" % exc, exc_info=True)
            self.events.put(("error", "复制到剪贴板失败：%s" % exc))
            return False

        # 不立即回滚：计数与拼接保持，支持多次复制。
        # 标记 pending；下一次截图时才从 0 开始新一轮拼接。
        with self._lock:
            self._pending_reset = True
        return True

    def open_output_dir(self):
        try:
            os.startfile(self.output_dir)  # noqa: S606
        except Exception as exc:
            log_error("无法打开目录: %r" % exc)
            self.events.put(("error", "无法打开目录：%s" % exc))