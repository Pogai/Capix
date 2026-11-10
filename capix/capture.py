# -*- coding: utf-8 -*-
"""Windows 屏幕区域捕获（ctypes 调 GDI，无第三方依赖）。

核心流程：
  GetDC(屏幕) -> CreateCompatibleDC/Bitmap -> BitBlt(SRCCOPY)
  -> GetDIBits(32bpp BGRA, top-down) -> 转 RGB
"""

import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000  # 连分层窗口一起捕获（微信等）
SRCCOPY_CAPTUREBLT = SRCCOPY | CAPTUREBLT
BI_RGB = 0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.BitBlt.restype = wintypes.BOOL
_gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteDC.restype = wintypes.BOOL
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_gdi32.GetDIBits.restype = ctypes.c_int
_gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
]


def _bgra_to_rgb(data: bytes, w: int, h: int) -> bytes:
    """32bpp BGRA(实际 A 通常为 0) 转 24bpp RGB，忽略 alpha。"""
    n = w * h
    out = bytearray(n * 3)
    dp = 0
    sp = 0
    for _ in range(n):
        out[dp] = data[sp + 2]      # R
        out[dp + 1] = data[sp + 1]  # G
        out[dp + 2] = data[sp]      # B
        dp += 3
        sp += 4
    return bytes(out)


def capture_rgb(x: int, y: int, w: int, h: int) -> bytes:
    """捕获屏幕指定矩形区域，返回 RGB 原始像素（宽*高*3）。

    坐标基于虚拟屏幕主屏左上角 (0,0)。x/y 可为负（多屏扩展屏场景，
    这里按传入值交给 GDI，若区域落在屏幕外则捕获失败并抛异常）。
    """
    if w <= 0 or h <= 0:
        raise ValueError("区域宽高必须为正: w=%d h=%d" % (w, h))

    hdc_screen = _user32.GetDC(None)
    if not hdc_screen:
        raise OSError("GetDC 失败")
    try:
        hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            raise OSError("CreateCompatibleDC 失败")
        try:
            h_bmp = _gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            if not h_bmp:
                raise OSError("CreateCompatibleBitmap 失败")
            try:
                _gdi32.SelectObject(hdc_mem, h_bmp)
                if not _gdi32.BitBlt(
                    hdc_mem, 0, 0, w, h, hdc_screen, int(x), int(y), SRCCOPY_CAPTUREBLT
                ):
                    raise OSError("BitBlt 失败")

                bmi = _BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = w
                bmi.bmiHeader.biHeight = -h  # top-down
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = BI_RGB

                size = w * h * 4
                buf = ctypes.create_string_buffer(size)
                got = _gdi32.GetDIBits(
                    hdc_mem, h_bmp, 0, h, buf, ctypes.byref(bmi), 0
                )
                if got == 0:
                    raise OSError("GetDIBits 失败")
                return _bgra_to_rgb(bytes(buf.raw[:size]), w, h)
            finally:
                _gdi32.DeleteObject(h_bmp)
        finally:
            _gdi32.DeleteDC(hdc_mem)
    finally:
        _user32.ReleaseDC(None, hdc_screen)