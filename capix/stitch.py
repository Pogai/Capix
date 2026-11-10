# -*- coding: utf-8 -*-
"""多张 RGB 图像纵向拼接为长图（纯标准库）。

会话中若调整过取景框，各图宽高会不一致：
- 拼接宽度取**最大宽度**，每张图左对齐原样放入，右侧不足处填浅色底；
- 这样任何一张都不会被裁掉内容（旧版按最小宽度裁剪，宽图会只剩左侧一条）。
"""

_BG = (245, 246, 248)   # 宽度不足处的底色（浅灰）


def stitch_vertical(images, bg=_BG):
    """把 [(w, h, rgb), ...] 按顺序纵向拼接，宽度取最大值。

    返回 (width, total_height, rgb_bytes)；空列表返回 None。
    """
    if not images:
        return None

    width = max(w for (w, _h, _rgb) in images)
    total_h = sum(h for (_w, h, _rgb) in images)
    row_bg = bytes(bg) * width
    out = bytearray(row_bg * total_h)

    stride = width * 3
    dst = 0
    for (w, h, rgb) in images:
        row_bytes = w * 3
        for y in range(h):
            src_off = y * w * 3
            out[dst:dst + row_bytes] = rgb[src_off:src_off + row_bytes]
            dst += stride

    return width, total_h, bytes(out)