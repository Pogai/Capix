# -*- coding: utf-8 -*-
"""纯标准库 PNG 编码器。

支持 RGB（color type 2）与 RGBA（color type 6，8-bit）。
"""

import struct
import zlib

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def encode_rgb(width: int, height: int, rgb_bytes: bytes) -> bytes:
    """把 RGB 原始像素编码为 PNG bytes。

    rgb_bytes 顺序为 R,G,B 逐像素排列，总长应为 width*height*3。
    """
    return _encode(width, height, rgb_bytes, 3, 2)


def encode_rgba(width: int, height: int, rgba_bytes: bytes) -> bytes:
    """把 RGBA 原始像素编码为 PNG bytes（含 alpha）。"""
    return _encode(width, height, rgba_bytes, 4, 6)


def _encode(width: int, height: int, data: bytes, channels: int, color_type: int) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("尺寸必须为正")
    expected = width * height * channels
    if len(data) != expected:
        raise ValueError(
            "像素数据长度不符: 期望 %d, 实际 %d" % (expected, len(data))
        )

    # 每行前加一个 filter 字节(0 = None)，便于 zlib 压缩
    row_len = width * channels
    raw = bytearray(expected + height)
    src = memoryview(data)
    offset = 0
    for y in range(height):
        raw[offset] = 0  # filter type: None
        start = y * row_len
        raw[offset + 1: offset + 1 + row_len] = src[start:start + row_len]
        offset += 1 + row_len

    def _chunk(typ: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + typ
            + body
            + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)

    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )