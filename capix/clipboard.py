# -*- coding: utf-8 -*-
"""把图像写入 Windows 剪贴板（ctypes，无第三方依赖）。

同时写入两种格式，兼容绝大多数软件粘贴：
  - CF_DIB：标准位图（Word/画图/微信/QQ 等）
  - "PNG" 注册格式：浏览器/Chrome/部分编辑器优先使用
"""

import ctypes
from ctypes import wintypes

from . import png as _png

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_DIB = 8
GMEM_MOVEABLE = 0x0002

# 函数签名（64 位指针必须显式声明）
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_user32.RegisterClipboardFormatW.restype = wintypes.UINT

_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


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


def _build_dib(width: int, height: int, rgb: bytes) -> bytes:
    """构造 24bpp、自底向上、BGR、行按 4 字节对齐的 DIB。"""
    row_padded = ((width * 3 + 3) // 4) * 4
    img_size = row_padded * height
    buf = bytearray(img_size)

    for y in range(height):
        src = rgb[y * width * 3:(y + 1) * width * 3]
        row = bytearray(width * 3)
        row[0::3] = src[2::3]  # B
        row[1::3] = src[1::3]  # G
        row[2::3] = src[0::3]  # R
        dst = (height - 1 - y) * row_padded
        buf[dst:dst + width * 3] = row

    hdr = _BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    hdr.biWidth = width
    hdr.biHeight = height  # 正数 = 自底向上
    hdr.biPlanes = 1
    hdr.biBitCount = 24
    hdr.biCompression = 0
    hdr.biSizeImage = img_size
    return bytes(hdr) + bytes(buf)


def _alloc_copy(data: bytes):
    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        raise MemoryError("GlobalAlloc 失败")
    ptr = _kernel32.GlobalLock(h)
    if not ptr:
        _kernel32.GlobalFree(h)
        raise MemoryError("GlobalLock 失败")
    ctypes.memmove(ptr, data, len(data))
    _kernel32.GlobalUnlock(h)
    return h


def copy_image(width: int, height: int, rgb: bytes) -> None:
    """把 RGB 图像写入剪贴板（CF_DIB + PNG）。失败抛异常。"""
    dib = _build_dib(width, height, rgb)
    png_bytes = _png.encode_rgb(width, height, rgb)
    png_fmt = _user32.RegisterClipboardFormatW("PNG")

    if not _user32.OpenClipboard(None):
        raise OSError("打开剪贴板失败")
    try:
        _user32.EmptyClipboard()

        # CF_DIB
        h1 = _alloc_copy(dib)
        if not _user32.SetClipboardData(CF_DIB, h1):
            _kernel32.GlobalFree(h1)
            raise OSError("写入 CF_DIB 失败")

        # PNG（可选，失败不影响 DIB）
        if png_fmt:
            try:
                h2 = _alloc_copy(png_bytes)
                if not _user32.SetClipboardData(png_fmt, h2):
                    _kernel32.GlobalFree(h2)
            except Exception:
                pass
    finally:
        _user32.CloseClipboard()