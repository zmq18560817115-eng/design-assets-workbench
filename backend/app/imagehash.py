"""感知哈希（dHash）用于近重复图片检测。

dHash：缩放到 9x8 灰度，比较相邻像素得到 64 位哈希。无需 numpy，
对缩放/轻微改动稳健；用汉明距离判断相似度（越小越像）。
"""
from __future__ import annotations

from PIL import Image as PILImage

HASH_SIZE = 8
# 汉明距离 <= 该阈值视为近重复
DUP_THRESHOLD = 5


def dhash(image_path: str, size: int = HASH_SIZE) -> str:
    img = PILImage.open(image_path).convert("L").resize((size + 1, size))
    px = list(img.getdata())
    w = size + 1
    val = 0
    for r in range(size):
        for c in range(size):
            left = px[r * w + c]
            right = px[r * w + c + 1]
            val = (val << 1) | (1 if left > right else 0)
    return f"{val:0{size * size // 4}x}"


def hamming(h1: str, h2: str) -> int:
    if not h1 or not h2 or len(h1) != len(h2):
        return 999
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def is_duplicate(h1: str, h2: str, threshold: int = DUP_THRESHOLD) -> bool:
    return hamming(h1, h2) <= threshold
