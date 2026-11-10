# -*- coding: utf-8 -*-
"""把 assets/source_icon.png 转为多尺寸 assets/icon.ico（构建期运行）。

优先使用用户提供的拼图图标（PNG 透明底）；
若不存在则回退旧版 source_icon.jpeg。
用法:  py build/make_icon.py
依赖:  Pillow（仅构建期，不进入 exe 运行时）
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PNG = os.path.join(BASE, "assets", "source_icon.png")
SRC_JPEG = os.path.join(BASE, "assets", "source_icon.jpeg")
OUT = os.path.join(BASE, "assets", "icon.ico")
PREVIEW = os.path.join(BASE, "assets", "icon_preview.png")

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    from PIL import Image
    src = SRC_PNG if os.path.exists(SRC_PNG) else SRC_JPEG
    img = Image.open(src).convert("RGBA")
    # 裁成正方形（居中），避免图标变形
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    img.save(OUT, format="ICO", sizes=SIZES)
    img.resize((256, 256), Image.LANCZOS).save(PREVIEW)
    print("源图标:", src)
    print("生成:", OUT, os.path.getsize(OUT), "bytes")
    print("预览:", PREVIEW)


if __name__ == "__main__":
    main()