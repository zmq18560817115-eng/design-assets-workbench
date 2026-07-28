"""版式骨架可视化：在原图上叠加检测到的页边距框、模块条带、栅格列线。"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from . import vision_provider

INDIGO = (129, 140, 248)   # 内容框 / 页边距
GREEN = (52, 211, 153)     # 纵向模块
AMBER = (251, 191, 36)     # 栅格列


def render_overlay(image_path: str) -> bytes:
    """返回叠加了版式骨架的 PNG 字节。"""
    base = Image.open(image_path).convert("RGBA")
    W, H = base.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    r = vision_provider.analyze_layout_regions(image_path)
    top, left, bottom, right = r["bbox"]
    lw = max(2, W // 320)

    # 栅格列（琥珀色竖条）
    for s, e in r["col_bands"]:
        d.rectangle(
            (s * W, top * H, e * W, bottom * H),
            outline=AMBER + (150,),
            width=max(1, lw - 1),
        )

    # 纵向模块（绿色横条）
    for s, e in r["row_bands"]:
        d.rectangle(
            (left * W, s * H, right * W, e * H),
            outline=GREEN + (200,),
            width=max(1, lw - 1),
        )

    # 内容框 / 页边距（靛蓝色粗框）
    d.rectangle(
        (left * W, top * H, right * W, bottom * H),
        outline=INDIGO + (255,),
        width=lw,
    )
    # 页边距引导：内容框到画面四边的虚线
    _dashed_h(d, top * H, 0, W, INDIGO + (120,))
    _dashed_h(d, bottom * H, 0, W, INDIGO + (120,))
    _dashed_v(d, left * W, 0, H, INDIGO + (120,))
    _dashed_v(d, right * W, 0, H, INDIGO + (120,))

    out = Image.alpha_composite(base, layer).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _dashed_h(d, y, x0, x1, color, dash=12, gap=8):
    x = x0
    while x < x1:
        d.line((x, y, min(x + dash, x1), y), fill=color, width=1)
        x += dash + gap


def _dashed_v(d, x, y0, y1, color, dash=12, gap=8):
    y = y0
    while y < y1:
        d.line((x, y, x, min(y + dash, y1)), fill=color, width=1)
        y += dash + gap
