# -*- coding: utf-8 -*-
"""系统托盘图标（Windows 通知区域），纯 ctypes 实现，无第三方依赖。

后台常驻：启动后在托盘显示图标。左键单击 = 开始框选；右键 = 菜单
（开始框选 / 打开截图目录 / 退出程序）。支持气泡通知。

实现要点：
  - 注册窗口类 + 创建消息窗口（HWND_MESSAGE）承载托盘回调消息；
  - Shell_NotifyIconW(NIM_ADD) 添加图标，WM_TRAYICON 中处理鼠标；
  - 独立线程跑消息循环；跨线程通过回调（投递到队列）通知主线程。
"""

import ctypes
import os
import tempfile
import threading
from ctypes import wintypes

from . import paths
from .logsetup import log

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

# 消息
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_TRAYICON = 0x8000 + 1          # WM_APP + 1
WM_QUIT = 0x0012

# Shell_NotifyIcon
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
IDI_APPLICATION = 32512

MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002

HWND_MESSAGE = ctypes.c_void_p(-3)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


# 函数签名
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = LRESULT
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.restype = LRESULT
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.CreatePopupMenu.restype = wintypes.HMENU
_user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
_user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
_user32.DestroyMenu.argtypes = [wintypes.HMENU]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.LoadImageW.restype = wintypes.HANDLE
_user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
_user32.LoadIconW.restype = wintypes.HICON
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)]
_shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def _build_frame_icon_rgba(size=32):
    """生成“取景框”图标（红色方框环，透明背景）。"""
    from . import png
    buf = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            outer = 2 <= x <= size - 3 and 2 <= y <= size - 3
            inner = 6 <= x <= size - 7 and 6 <= y <= size - 7
            i = (y * size + x) * 4
            if outer and not inner:
                buf[i:i + 4] = bytes((235, 59, 48, 255))
            # 四角加粗
            corner = (
                (outer and not inner) and
                ((x < 7 and y < 7) or (x > size - 8 and y < 7) or
                 (x < 7 and y > size - 8) or (x > size - 8 and y > size - 8))
            )
            if corner:
                buf[i:i + 4] = bytes((255, 255, 255, 255))
    return png.encode_rgba(size, size, bytes(buf))


def _write_ico(path, png_bytes, size=32):
    """把 PNG 封装为 ICO 文件（PNG 内嵌，Vista+ 支持）。"""
    import struct
    header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=icon, count
    entry = struct.pack(
        "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png_bytes), 6 + 16
    )
    with open(path, "wb") as f:
        f.write(header + entry + png_bytes)


class TrayIcon:
    def __init__(self, on_select, on_open_dir=None, on_open_log=None, on_quit=None,
                 on_settings=None, title="固定框连续截图"):
        self.on_select = on_select
        self.on_open_dir = on_open_dir
        self.on_open_log = on_open_log
        self.on_quit = on_quit
        self.on_settings = on_settings
        self.title = title

        self._thread = None
        self._hwnd = None
        self._tid = None
        self._running = False
        self._ok = False
        self._started = threading.Event()
        self._wndproc = WNDPROC(self._wnd_proc)   # 保活，防止回收
        self._nid = None
        self._hicon = None

    # ---------- 生命周期 ----------
    def start(self, timeout=4.0):
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._started.wait(timeout)
        return self._ok

    def stop(self):
        self._running = False
        if self._tid:
            _user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2.0)

    # ---------- 内部线程 ----------
    def _run(self):
        try:
            hinst = _kernel32.GetModuleHandleW(None)
            classname = "CapixTrayWnd"
            wc = _WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = classname
            _user32.RegisterClassW(ctypes.byref(wc))

            self._hwnd = _user32.CreateWindowExW(
                0, classname, self.title, 0, 0, 0, 0, 0,
                HWND_MESSAGE, None, hinst, None,
            )
            if not self._hwnd:
                self._ok = False
                self._started.set()
                return

            hicon = self._load_icon()
            nid = _NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAYICON
            nid.hIcon = hicon
            nid.szTip = self.title
            self._nid = nid
            self._hicon = hicon

            ok = _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
            self._ok = bool(ok)
            self._started.set()
            if not ok:
                _user32.DestroyWindow(self._hwnd)
                return

            self._tid = threading.get_ident()
            self._running = True
            msg = _MSG()
            while self._running:
                r = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            log("[tray] 运行异常: %r" % exc)
            self._ok = False
            self._started.set()
        finally:
            try:
                if self._nid is not None:
                    _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass
            try:
                if self._hwnd:
                    _user32.DestroyWindow(self._hwnd)
            except Exception:
                pass

    def _load_icon(self):
        # 1) 优先使用随包分发的 icon.ico（用户自定义图标）
        try:
            ico = paths.resource_path(os.path.join("assets", "icon.ico"))
            if os.path.exists(ico):
                h = _user32.LoadImageW(None, ico, IMAGE_ICON, 0, 0,
                                       LR_LOADFROMFILE | 0x0040)  # LR_DEFAULTSIZE
                if h:
                    return h
                log("[tray] 加载 assets/icon.ico 失败（LoadImage 返回0）")
        except Exception as exc:
            log("[tray] 加载自定义图标异常: %r" % exc)
        # 2) 回退：运行时生成“取景框”图标
        try:
            path = os.path.join(tempfile.gettempdir(), "capix_tray.ico")
            _write_ico(path, _build_frame_icon_rgba())
            h = _user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if h:
                return h
        except Exception as exc:
            log("[tray] 生成默认图标失败: %r" % exc)
        return _user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    # ---------- 消息处理 ----------
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                ev = lparam & 0xFFFF
                if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._fire(self.on_select)
                elif ev == WM_RBUTTONUP:
                    self._show_menu(hwnd)
                return 0
            if msg == WM_COMMAND:
                mid = wparam & 0xFFFF
                if mid == 1:
                    self._fire(self.on_select)
                elif mid == 2:
                    self._fire(self.on_open_dir)
                elif mid == 3:
                    self._fire(self.on_quit)
                elif mid == 4:
                    self._fire(self.on_open_log)
                elif mid == 5:
                    self._fire(self.on_settings)
                return 0
            if msg == WM_DESTROY:
                _user32.PostQuitMessage(0)
                return 0
        except Exception as exc:
            log("[tray] 消息处理异常: %r" % exc)
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self, hwnd):
        hmenu = _user32.CreatePopupMenu()
        _user32.AppendMenuW(hmenu, 0, 1, "开始框选")
        _user32.AppendMenuW(hmenu, 0, 2, "打开截图目录")
        _user32.AppendMenuW(hmenu, 0, 5, "设置…")
        _user32.AppendMenuW(hmenu, 0, 4, "打开日志目录")
        _user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        _user32.AppendMenuW(hmenu, 0, 3, "退出程序")
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        _user32.SetForegroundWindow(hwnd)
        _user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
        _user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        _user32.DestroyMenu(hmenu)

    def _fire(self, cb):
        if cb:
            try:
                cb()
            except Exception as exc:
                log("[tray] 回调异常: %r" % exc)

    # ---------- 外部调用 ----------
    def notify(self, title, text):
        """弹气泡通知。可在任意线程调用。"""
        if self._nid is None:
            return
        try:
            nid = self._nid
            nid.uFlags = NIF_INFO
            nid.szInfo = text[:255]
            nid.szInfoTitle = title[:63]
            nid.dwInfoFlags = NIIF_INFO
            _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass