"""视觉分析底座（对应技术方案「AI视觉分析服务」）。

- 若配置了真实视觉模型（VISION_PROVIDER=openai/qwen 且提供 API Key），
  则调用该模型返回结构化特征。
- 否则退回到基于 Pillow 的启发式分析器：从图片中提取主色板、亮度、
  对比度、宽高比等真实特征，供上层 Agent 生成拆解结果。

这样 Demo 既能离线跑通完整链路，又能一行环境变量切换到真实大模型。
"""
from __future__ import annotations

import colorsys
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image as PILImage
from PIL import ImageFilter


@dataclass
class ImageFeatures:
    """从图片中提取的底层视觉特征。"""

    width: int
    height: int
    aspect_ratio: float
    orientation: str          # portrait | landscape | square
    palette: list[str] = field(default_factory=list)   # 主色板（HEX）
    primary_hex: str = "#888888"
    brightness: float = 0.5   # 0~1
    contrast: float = 0.5     # 0~1
    saturation: float = 0.5   # 0~1
    warm: bool = False        # 冷暖倾向
    color_names: list[str] = field(default_factory=list)
    # —— 排版/文字相关特征（基于边缘密度估计）——
    complexity: float = 0.5   # 画面整体繁简度（边缘密度）0~1
    band_activity: tuple[float, float, float] = (0.0, 0.0, 0.0)  # 上/中/下三段活跃度
    col_activity: tuple[float, float, float] = (0.0, 0.0, 0.0)   # 左/中/右三列活跃度
    text_density: float = 0.0  # 文字/细节密度估计 0~1
    # —— 硬版式参数（基于行/列投影）——
    margins: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # 上/右/下/左 页边距(占比)
    row_blocks: int = 1       # 纵向内容模块数（被留白分隔的横向条带）
    col_groups: int = 1       # 栅格列数（被纵向留白分隔的列组）
    content_ratio: float = 1.0  # 内容区占画面比例
    content_bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)  # 内容框 上/左/下/右


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _name_color(rgb: tuple[int, int, int]) -> str:
    r, g, b = [c / 255 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.12:
        if v < 0.2:
            return "黑"
        if v > 0.85:
            return "白"
        return "灰"
    hue = h * 360
    if hue < 15 or hue >= 345:
        return "红"
    if hue < 45:
        return "橙"
    if hue < 70:
        return "黄"
    if hue < 160:
        return "绿"
    if hue < 200:
        return "青"
    if hue < 255:
        return "蓝"
    if hue < 290:
        return "紫"
    return "品红"


def _active_indices(profile: list[float], ratio: float = 0.16) -> list[int]:
    """返回投影中「有内容」的下标（活跃度超过峰值一定比例）。"""
    if not profile:
        return []
    peak = max(profile)
    if peak <= 0:
        return []
    thr = peak * ratio
    return [i for i, v in enumerate(profile) if v > thr]


def _count_groups(active: list[int], total: int, gap_frac: float = 0.04) -> int:
    """把连续的活跃下标聚成组，组间需有足够留白间隙。返回组数。"""
    if not active:
        return 0
    min_gap = max(2, int(total * gap_frac))
    groups = 1
    for prev, cur in zip(active, active[1:]):
        if cur - prev > min_gap:
            groups += 1
    return groups


def _group_bounds(active: list[int], total: int, gap_frac: float) -> list[tuple[float, float]]:
    """把连续活跃下标聚成组，返回每组的 (起, 止) 占比区间。"""
    if not active:
        return []
    min_gap = max(2, int(total * gap_frac))
    bounds: list[tuple[float, float]] = []
    start = prev = active[0]
    for cur in active[1:]:
        if cur - prev > min_gap:
            bounds.append((start / total, (prev + 1) / total))
            start = cur
        prev = cur
    bounds.append((start / total, (prev + 1) / total))
    return bounds


def analyze_layout_regions(image_path: str) -> dict:
    """返回用于绘制版式骨架的区域边界（均为 0~1 占比）：
    内容框 bbox(上,左,下,右)、纵向模块条带 row_bands、栅格列 col_bands。"""
    gray = PILImage.open(image_path).convert("L").resize((120, 120))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    W, H = edges.size
    ep = list(edges.getdata())
    row_prof = [sum(ep[y * W:(y + 1) * W]) for y in range(H)]
    col_prof = [sum(ep[y * W + x] for y in range(H)) for x in range(W)]
    ar = _active_indices(row_prof)
    ac = _active_indices(col_prof)
    row_bands = _group_bounds(ar, H, 0.05)
    col_bands = _group_bounds(ac, W, 0.06)
    if ar and ac:
        bbox = (ar[0] / H, ac[0] / W, (ar[-1] + 1) / H, (ac[-1] + 1) / W)
    else:
        bbox = (0.1, 0.1, 0.9, 0.9)
    return {"bbox": bbox, "row_bands": row_bands, "col_bands": col_bands}


def _layout_metrics(row_prof, col_prof, H, W):
    """从行/列边缘投影推断硬版式参数：页边距、模块数、栅格列数、内容占比、内容框。"""
    ar = _active_indices(row_prof)
    ac = _active_indices(col_prof)
    if not ar or not ac:
        # 近乎空白
        return (0.4, 0.4, 0.4, 0.4), 0, 0, 0.0, (0.4, 0.4, 0.6, 0.6)

    top = ar[0] / H
    bottom = (H - 1 - ar[-1]) / H
    left = ac[0] / W
    right = (W - 1 - ac[-1]) / W

    row_blocks = _count_groups(ar, H, gap_frac=0.05)
    col_groups = _count_groups(ac, W, gap_frac=0.06)

    content_h = (ar[-1] - ar[0] + 1) / H
    content_w = (ac[-1] - ac[0] + 1) / W
    content_ratio = round(content_h * content_w, 3)
    bbox = (round(top, 3), round(left, 3), round(1 - bottom, 3), round(1 - right, 3))
    margins = (round(top, 3), round(right, 3), round(bottom, 3), round(left, 3))
    return margins, row_blocks, col_groups, content_ratio, bbox


def extract_features(image_path: str) -> ImageFeatures:
    """使用 Pillow 提取真实图片特征。"""
    img = PILImage.open(image_path).convert("RGB")
    w, h = img.size
    ratio = round(w / h, 3) if h else 1.0
    if abs(ratio - 1) < 0.08:
        orientation = "square"
    elif ratio > 1:
        orientation = "landscape"
    else:
        orientation = "portrait"

    # 缩略后统计主色（量化到 16 色）
    small = img.resize((80, 80))
    quant = small.quantize(colors=8).convert("RGB")
    pixels = list(quant.getdata())
    counter = Counter(pixels)
    top = [c for c, _ in counter.most_common(5)]
    palette = [_rgb_to_hex(c) for c in top]
    color_names = []
    for c in top:
        n = _name_color(c)
        if n not in color_names:
            color_names.append(n)

    # 亮度 / 饱和度 / 冷暖
    hsv_vals = [colorsys.rgb_to_hsv(*[x / 255 for x in p]) for p in pixels]
    brightness = sum(v for _, _, v in hsv_vals) / len(hsv_vals)
    saturation = sum(s for _, s, _ in hsv_vals) / len(hsv_vals)
    vals = [v for _, _, v in hsv_vals]
    mean_v = brightness
    contrast = (sum((v - mean_v) ** 2 for v in vals) / len(vals)) ** 0.5

    warm_count = sum(1 for hh, ss, _ in hsv_vals if ss > 0.15 and (hh * 360 < 70 or hh * 360 >= 300))
    cool_count = sum(1 for hh, ss, _ in hsv_vals if ss > 0.15 and 160 <= hh * 360 < 300)
    warm = warm_count >= cool_count

    # —— 边缘密度分析：用于推断排版结构与文字/标题区域 ——
    gray = img.convert("L").resize((120, 120))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    # FIND_EDGES 会在图像四周留下 1~2px 亮边伪影，裁掉以免污染页边距/投影分析
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    W, H = edges.size
    ep = list(edges.getdata())
    overall = sum(ep) / len(ep) / 255.0
    # 三段（上/中/下）活跃度
    band = [0.0, 0.0, 0.0]
    for i in range(3):
        seg = ep[i * W * (H // 3):(i + 1) * W * (H // 3)]
        band[i] = round(sum(seg) / len(seg) / 255.0, 3)
    # 三列（左/中/右）活跃度
    col = [0.0, 0.0, 0.0]
    col_sum = [0, 0, 0]
    col_cnt = [0, 0, 0]
    for y in range(H):
        for x in range(W):
            c = 0 if x < W // 3 else (1 if x < 2 * W // 3 else 2)
            col_sum[c] += ep[y * W + x]
            col_cnt[c] += 1
    col = [round(col_sum[i] / col_cnt[i] / 255.0, 3) for i in range(3)]
    # 文字密度：高边缘像素占比
    text_density = round(sum(1 for v in ep if v > 60) / len(ep), 3)

    # —— 硬版式参数：行/列投影 ——
    row_prof = [sum(ep[y * W:(y + 1) * W]) for y in range(H)]
    col_prof = [sum(ep[y * W + x] for y in range(H)) for x in range(W)]
    margins, row_blocks, col_groups, content_ratio, content_bbox = _layout_metrics(
        row_prof, col_prof, H, W
    )

    return ImageFeatures(
        width=w,
        height=h,
        aspect_ratio=ratio,
        orientation=orientation,
        palette=palette,
        primary_hex=palette[0] if palette else "#888888",
        brightness=round(brightness, 3),
        contrast=round(min(contrast * 2.5, 1.0), 3),
        saturation=round(saturation, 3),
        warm=warm,
        color_names=color_names,
        complexity=round(min(overall * 2.5, 1.0), 3),
        band_activity=(band[0], band[1], band[2]),
        col_activity=(col[0], col[1], col[2]),
        text_density=text_density,
        margins=margins,
        row_blocks=row_blocks,
        col_groups=col_groups,
        content_ratio=content_ratio,
        content_bbox=content_bbox,
    )


def analyze(image_path: str) -> ImageFeatures:
    """提取底层客观视觉特征（色板、亮度、边缘投影、硬版式参数）。

    这一层始终由 Pillow 完成——像素能精确测量的东西（真实色板、页边距、
    栅格）比大模型更准。语义理解（若配置了视觉大模型）在 pipeline 层叠加。
    """
    return extract_features(image_path)
