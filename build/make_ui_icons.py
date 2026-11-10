# -*- coding: utf-8 -*-
"""构建期生成高质量工具条图标（Pillow 超采样抗锯齿）。

浅色工具栏（白底 + 深色图标）：
- 输出 assets/ui/{camera,copy,gear,close,move}_{normal,white,off}.png
  · normal : 深灰 #3A414A（浅色条上直接用，不透明）
  · white  : 白（备用高对比态）
  · off    : 浅灰（禁用）
- arrow_{n,s,e,w,ne,nw,se,sw}.png：白色开口箭头手柄（压在蓝边框线上）
- dot.png：硬边圆点手柄（备选皮肤，无 alpha）

所有素材直接按显示尺寸渲染（16 倍超采样 -> LANCZOS 缩回，不做 subsample）。
"""

import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "assets", "ui")
os.makedirs(OUT, exist_ok=True)

SIZE = 32          # 工具条图标显示尺寸（直接绘制，不缩放无混色）
SS = 4             # 图标超采样倍数（32*4=128 内部画布，仅为了 antialias）
W = SIZE * SS
K = W / 44.0

DOT_BLUE = (51, 136, 255)        # #3388ff
WHITE = (255, 255, 255)

# 浅色工具栏上的图标配色：实心主色蓝，不再镂空
_DARK = (51, 111, 230)           # 主色蓝 #336FE6（实心填充，交互感强）
COLORS = {
    "normal": _DARK,                     # 常态：主色蓝实心
    "white": (255, 255, 255),            # 白（备用）
    "off": (203, 208, 216),              # 禁用浅灰
}


_CANVAS_BG = (255, 255, 255)


def _canvas(pix, bg=None):
    """画布背景纯白：工具栏图标不需要透明，按钮底就是白色，
    彻底避免色键抠除/抗锯齿混色造成的黑边与碎片。"""
    im = Image.new("RGB", (pix, pix), bg or _CANVAS_BG)
    return im, ImageDraw.Draw(im)


def _s(v):
    return int(round(v * K))


def draw_camera(col):
    """实心相机：机身圆角块 + 镜头白孔 + 顶部取景器凸起。"""
    im, d = _canvas(W)
    # 取景器凸起
    d.rounded_rectangle([_s(15), _s(8), _s(29), _s(15)], radius=_s(2.5),
                        fill=col)
    # 机身（实心圆角块）
    d.rounded_rectangle([_s(5), _s(12.5), _s(39), _s(34)], radius=_s(6),
                        fill=col)
    # 镜头（白心圆，双层描同心圆更精致）
    cx, cy = _s(22), _s(23.2)
    r1 = _s(7.6)
    d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1],
              fill=(255, 255, 255))
    r2 = _s(3.4)
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=col)
    return im


def draw_copy(col):
    """实心复制：后层实心块 + 前层实心块（白边留缝区分前后）。"""
    im, d = _canvas(W)
    # 后层（左上，实心）
    d.rounded_rectangle([_s(8), _s(8), _s(28), _s(28)], radius=_s(4),
                        fill=col)
    # 前层（右下）：先挖白边留缝，再实心填充
    box = [_s(16), _s(16), _s(36), _s(36)]
    gap = _s(2)
    white = (255, 255, 255) if col != (255, 255, 255) else (1, 2, 3)
    d.rounded_rectangle([box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap],
                        radius=_s(5), fill=white)
    d.rounded_rectangle(box, radius=_s(4), fill=col)
    return im


def draw_gear(col):
    """实心齿轮：外齿环 + 白心孔。"""
    import math
    im, d = _canvas(W)
    cx = cy = _s(22)
    # 齿：粗实心块
    for k in range(8):
        a = math.radians(k * 45 + 22.5)
        x1 = cx + _s(10.2) * math.cos(a)
        y1 = cy + _s(10.2) * math.sin(a)
        x2 = cx + _s(15.6) * math.cos(a)
        y2 = cy + _s(15.6) * math.sin(a)
        d.line([x1, y1, x2, y2], fill=col, width=int(_s(6.0)))
    # 主体实心圆盘
    r = _s(11.8)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    # 白心孔
    r2 = _s(4.4)
    white = (255, 255, 255) if col != (255, 255, 255) else (1, 2, 3)
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=white)
    return im


def draw_close(col):
    """实心关闭：粗圆头叉丝。"""
    im, d = _canvas(W)
    lw = int(_s(5.2))
    d.line([_s(14), _s(14), _s(30), _s(30)], fill=col, width=lw)
    d.line([_s(30), _s(14), _s(14), _s(30)], fill=col, width=lw)
    # 四端圆头
    for (ex, ey) in ((14, 14), (30, 14), (14, 30), (30, 30)):
        r = int(_s(2.6))
        d.ellipse([_s(ex) - r, _s(ey) - r, _s(ex) + r, _s(ey) + r], fill=col)
    return im


def draw_move(col):
    """实心四向移动箭头（移动取景框模式的开关按钮）。"""
    im, d = _canvas(W)
    lw = int(_s(4.6))
    c = _s(22)
    d.line([c, _s(12), c, _s(32)], fill=col, width=lw)
    d.line([_s(12), c, _s(32), c], fill=col, width=lw)
    # 中心圆盘（增强实心感）
    r0 = _s(4.2)
    d.ellipse([c - r0, c - r0, c + r0, c + r0], fill=col)
    ah, aw = _s(5.2), _s(4.0)
    for (dx, dy) in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        tipx, tipy = c + dx * _s(14), c + dy * _s(14)
        p1 = (tipx - dy * aw, tipy - dx * aw)
        p2 = (tipx + dy * aw, tipy + dx * aw)
        base = (tipx - dx * ah, tipy - dy * ah)
        d.polygon([p1, p2, base], fill=col)
    return im


def draw_arrow(direction):
    """白色开口箭头手柄（V 形，顶点指向 direction）。

    样式：粗白线开口箭头约 14x10px，压在边框线上。
    单边：一个 V，尖朝外（拖拽方向）。
    角  ：双 V，沿对角各一个，整体朝角点方向。
    显示尺寸 24x24；直接按角度数学绘制线段（不用图像旋转，避免混色）。
    """
    import math
    size = 24
    w = size * SS
    k = w / 24.0

    def s(v):
        return int(round(v * k))

    im = Image.new("RGB", (w, w), (1, 2, 3))
    d = ImageDraw.Draw(im)
    lw = max(2, s(3.2))
    arm = s(6.2)           # 半臂长
    c = w / 2.0

    def v_shape(cx, cy, angle):
        """在 (cx,cy) 画 V：顶点朝 angle（度，0=上，顺时针）。
        两臂几何角度 = 顶点角 ± 135°（即臂从顶点向后张开 45°）。"""
        a = math.radians(angle)
        r_head = arm * math.cos(math.radians(18))   # 顶点略前伸，形成箭头感
        hx = cx + r_head * math.sin(a)
        hy = cy - r_head * math.cos(a)
        for sign in (-1, 1):
            t = a + sign * math.radians(135)
            ex = cx + arm * math.sin(t)
            ey = cy - arm * math.cos(t)
            d.line([cx, cy, ex, ey], fill=WHITE, width=lw)
        # 顶点小圆头，保证两臂连接平滑
        r = lw / 2.0
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)

    if direction in ("n", "s", "e", "w"):
        ang = {"n": 0, "e": 90, "s": 180, "w": 270}[direction]
        v_shape(c, c, ang)
    else:
        # 角：双 V，一个指向主方向，一个次方向，中心稍向角点偏移
        main_ang = {"ne": 45, "se": 135, "sw": 225, "nw": 315}[direction]
        off = s(4.4)
        dx = off * math.sin(math.radians(main_ang))
        dy = -off * math.cos(math.radians(main_ang))
        # 双箭头：0° 与 90° 的组合按象限拆分
        a1 = {"ne": (0, 90), "se": (180, 90), "sw": (180, 270), "nw": (0, 270)}[direction]
        v_shape(c + dx, c + dy, a1[0])
        v_shape(c + dx, c + dy, a1[1])

    # 缩小后做色键二值化：LANCZOS 在白线边缘产生的半透明/混色像素
    # 在色键窗口上会呈现为"断续黑边"，必须回归纯白或纯色键两态。
    small = im.resize((size, size), Image.LANCZOS)
    spx = small.load()
    for yy in range(size):
        for xx in range(size):
            r, g, b = spx[xx, yy]
            dist = min(abs(r - 255), abs(g - 255), abs(b - 255))
            spx[xx, yy] = WHITE if dist < 150 else (1, 2, 3)
    return small


def draw_dot():
    """圆点手柄（备选皮肤）：硬边三层圆 + 色键背景（无 alpha）。"""
    import math
    key = (1, 2, 3)
    size = 28
    blue = DOT_BLUE
    im = Image.new("RGB", (size, size), key)
    px = im.load()
    c = size / 2.0
    r_out, r_white, r_core = 10.75, 8.5, 5.75
    for y in range(size):
        for x in range(size):
            dd = math.hypot(x + 0.5 - c, y + 0.5 - c)
            if dd <= r_core:
                px[x, y] = blue
            elif dd <= r_white:
                px[x, y] = (255, 255, 255)
            elif dd <= r_out:
                px[x, y] = blue
    return im


ICONS = {
    "camera": draw_camera,
    "copy": draw_copy,
    "gear": draw_gear,
    "close": draw_close,
    "move": draw_move,
}

ARROWS = ["n", "s", "e", "w", "ne", "nw", "se", "sw"]


def main():
    for name, fn in ICONS.items():
        for state, col in COLORS.items():
            # 全部白底实色：normal=主色蓝、white=白图(备用)、off=浅灰
            im = fn(col).resize((SIZE, SIZE), Image.LANCZOS)
            p = os.path.join(OUT, "%s_%s.png" % (name, state))
            im.save(p)
            print("saved", p, os.path.getsize(p))
    # 箭头手柄（直接按显示尺寸 24）
    for d_ in ARROWS:
        im = draw_arrow(d_)
        p = os.path.join(OUT, "arrow_%s.png" % d_)
        im.save(p)
        print("saved", p, os.path.getsize(p))
    # 圆点手柄（备选皮肤）
    draw_dot().save(os.path.join(OUT, "dot.png"))
    print("saved", os.path.join(OUT, "dot.png"))
    # 预览合图（白底一行图标）
    sheet = Image.new("RGB", (SIZE * 5 + 60, SIZE + 24 + 48), (255, 255, 255))
    for c, name in enumerate(ICONS.keys()):
        im = Image.open(os.path.join(OUT, "%s_normal.png" % name)).convert("RGB")
        x, y = 10 + c * (SIZE + 10), 10
        sheet.paste((217, 219, 224), [x - 4, y - 4, x + SIZE + 4, y + SIZE + 4])
        sheet.paste(im, (x, y))
    for c, d_ in enumerate(ARROWS):
        im = Image.open(os.path.join(OUT, "arrow_%s.png" % d_)).convert("RGB")
        x, y = 10 + c * 32, SIZE + 24
        sheet.paste(im, (x, y))
    p = os.path.join(BASE, ".temp", "ui_sheet.png")
    sheet.save(p)
    print("sheet:", p)


def _render_icon(fn, col, base):
    """以指定背景色渲染图标函数 fn（fn 内部自带 _canvas 调用，
    故通过临时替换默认背景的方式实现）。"""
    global _CANVAS_BG
    _CANVAS_BG = base
    im = fn(col)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


if __name__ == "__main__":
    main()