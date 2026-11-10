# -*- coding: utf-8 -*-
"""Windows 窗口工具：DPI 感知 + 鼠标穿透（ctypes，无第三方依赖）。"""

import ctypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2


def enable_dpi_awareness():
    """开启进程 DPI 感知，使 tkinter 坐标与屏幕物理像素一致。"""
    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        _user32.SetProcessDPIAware()
    except Exception:
        pass


def _root_hwnd(hwnd):
    h = _user32.GetAncestor(hwnd, GA_ROOT)
    return h or hwnd


def _get_exstyle(hwnd):
    return _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)


def _set_exstyle(hwnd, ex):
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)


def make_click_through(tk_window):
    """让整个窗口鼠标穿透（点击落到下层窗口），但仍可见。

    用于常驻取景框：边框可见、内部鼠标穿透，便于点击下方桌面操作。
    """
    tk_window.update_idletasks()
    hwnd = int(tk_window.winfo_id())
    root = _root_hwnd(hwnd)
    ex = _get_exstyle(root)
    _set_exstyle(root, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
    return root


def make_tool_window(tk_window):
    """标记为工具窗口（不进入 Alt-Tab），可选。"""
    tk_window.update_idletasks()
    hwnd = int(tk_window.winfo_id())
    root = _root_hwnd(hwnd)
    ex = _get_exstyle(root)
    _set_exstyle(root, ex | WS_EX_TOOLWINDOW)
    return root