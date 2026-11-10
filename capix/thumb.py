# -*- coding: utf-8 -*-
"""缩略图：RGB 等比 fit 缩放（最近邻，纯标准库）。

用于长图预览：把拼好的大图缩到预览窗口大小内（不放大），
输出大小只与预览窗口相关，成本恒定（O(输出像素)），与原长图高度无关。
"""


def scale_fit(w: int, h: int, rgb: bytes, max_w: int, max_h: int):
    """等比缩放到不超过 (max_w, max_h)；原图更小则原样返回。

    返回 (tw, th, rgb_bytes)。
    """
    if w <= 0 or h <= 0:
        raise ValueError("尺寸必须为正")
    if len(rgb) != w * h * 3:
        raise ValueError("像素数据长度不符")

    s = min(max_w / w, max_h / h, 1.0)
    tw = max(1, int(w * s))
    th = max(1, int(h * s))
    if tw == w and th == h:
        return w, h, rgb

    out = bytearray(tw * th * 3)
    for oy in range(th):
        sy = min(h - 1, int(oy * h / th))
        srow = sy * w * 3
        orow = oy * tw * 3
        for ox in range(tw):
            sx = min(w - 1, int(ox * w / tw))
            si = srow + sx * 3
            di = orow + ox * 3
            out[di] = rgb[si]
            out[di + 1] = rgb[si + 1]
            out[di + 2] = rgb[si + 2]
    return tw, th, bytes(out)