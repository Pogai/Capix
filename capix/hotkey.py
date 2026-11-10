# -*- coding: utf-8 -*-
"""Windows 全局热键（ctypes 调 RegisterHotKey，无第三方依赖）。

用专用消息循环线程注册热键；按 `hWnd=None` 时 WM_HOTKEY 投递到该线程
自身的消息队列，由 GetMessage 循环取回并在该线程执行回调（不跨线程操作
tkinter，GUI 侧通过队列轮询同步状态）。
"""

import ctypes
import threading
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# 修饰键
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# 常用虚拟键码
VK_A = 0x41
VK_S = 0x53
VK_R = 0x52
VK_P = 0x50
VK_F8 = 0x77
VK_F9 = 0x78


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class GlobalHotkey:
    """管理一组全局热键。

    用法:
        gh = GlobalHotkey()
        gh.register(MOD_CONTROL | MOD_SHIFT, VK_S, on_shot)
        gh.start()
        ...
        gh.stop()
    """

    def __init__(self, on_registered=None):
        self._handlers = []        # [(hid, mod, vk, callback)]
        self._thread = None
        self._running = threading.Event()
        self._tid = None
        self._on_registered = on_registered  # callable(failures) 注册完成后回调

    def register(self, mod: int, vk: int, callback) -> int:
        """注册热键，返回句柄 id（也可用于后续反注册）。"""
        hid = len(self._handlers) + 1
        self._handlers.append((hid, mod, vk, callback))
        return hid

    def start(self):
        if self._thread is not None:
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()

    def stop(self):
        self._running.clear()
        if self._tid is not None:
            _user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def _run(self):
        self._tid = threading.get_ident()
        failures = []
        for hid, mod, vk, _cb in self._handlers:
            ok = _user32.RegisterHotKey(None, hid, mod | MOD_NOREPEAT, vk)
            if not ok:
                failures.append((hid, mod, vk))
        if failures and self._on_registered is not None:
            try:
                self._on_registered(failures)
            except Exception as exc:
                print("[hotkey] 注册结果回调异常:", exc)

        msg = _MSG()
        while self._running.is_set():
            res = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:  # WM_QUIT 或错误
                break
            if msg.message == WM_HOTKEY:
                hid = int(msg.wParam)
                for h, _m, _v, cb in self._handlers:
                    if h == hid:
                        try:
                            cb()
                        except Exception as exc:  # 不因单个回调崩溃退出
                            print("[hotkey] 回调异常:", exc)
                        break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        for hid, _m, _v, _cb in self._handlers:
            _user32.UnregisterHotKey(None, hid)