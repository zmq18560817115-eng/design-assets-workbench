"""真实视觉大模型接入（OpenAI 兼容 Chat Completions 接口）。

兼容 GPT Vision、Qwen-VL（DashScope 兼容模式）、以及大多数内网自建的
OpenAI 兼容视觉服务（vLLM / LMDeploy / Ollama 兼容层等）。

设计为「语义增强层」：像素能精确测量的东西（真实色板、页边距、栅格列数）
仍由 Pillow 负责；大模型负责它擅长的语义理解（画面内容、行业场景、风格细腻度、
信息层级、为什么优秀）。未配置或调用失败时，上层会自动退回启发式规则。
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from . import config

SYSTEM_PROMPT = (
    "你是资深视觉设计分析师，擅长把一张设计图拆解成结构化的设计知识。"
    "请只输出一个 JSON 对象，不要输出多余文字或 markdown 代码块。"
)

# 期望模型返回的 JSON 结构（作为提示，也用于解析）
USER_TEMPLATE = """你是资深视觉设计分析师，请对这张设计图做**深度**拆解，返回严格 JSON（字段可空但需存在）。
要求：判断具体、避免空话；点评与建议要专业、可操作。

{{
  "image_type": "图片类型，如 海报/Banner/产品卡",
  "industry": "所属行业",
  "scene": "使用场景",
  "style_tags": ["风格标签，如 高级感/科技感/极简"],
  "mood_keywords": ["情绪关键词"],
  "brand_position": "品牌定位",
  "layout_type": "版式类型，如 中轴型/分栏型/网格型/留白型",
  "alignment": "对齐方式",
  "hierarchy": ["信息层级，从主到次"],
  "title_treatment": "标题处理方式",
  "font_tone": "字体调性建议",
  "why_good": ["这张图为什么优秀，2~4 条"],
  "reusable_methods": ["可复用的设计方法，2~4 条"],
  "target_audience": "目标受众画像",
  "applicable_scenes": ["还适用于哪些场景，2~4 个"],
  "color_roles": ["色彩角色与作用，如 主色#xx传达信任/点缀色#xx制造焦点"],
  "composition_principles": ["用到的构图/版式原理，如 三分法/视觉动线Z型/负空间聚焦"],
  "emotion_narrative": "画面传达的情绪与叙事（1~2 句）",
  "critique": ["专业点评，含优点与不足，2~4 条"],
  "improvement": ["具体可操作的提升建议，2~4 条"],
  "summary": "一句话总结",
  "prompt_zh": "可直接用于 AI 绘图的中文提示词（以版式为主、风格为辅）",
  "prompt_en": "对应英文提示词"
}}

重要：prompt_zh/prompt_en 必须与图片的**平台/媒介类型一致**——
若是 UI 界面就写界面设计提示词、网页就写网页设计、海报就写平面海报、插画就写插画；
**不要一律写成"电商产品图/商业摄影/8k 产品级"**，除非原图本身就是电商产品图。

供参考的客观测量（由程序从像素中精确算出，请结合分析、不要改写这些数值）：
- 主色板: {palette}
- 冷暖/亮度: {tone}
- 版式硬参数: 栅格 {grid_columns}，{modules}，{margins}
"""


def _extract_json(text: str) -> dict:
    """从模型返回中稳健地抽取 JSON。"""
    text = text.strip()
    # 去掉可能的 ```json ... ``` 包裹
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.S)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def analyze_image(image_bytes: bytes, mime: str, hints: dict) -> dict:
    """调用视觉大模型，返回语义分析字典。失败会抛异常，由上层决定回退。"""
    b64 = base64.b64encode(image_bytes).decode()
    data_uri = f"data:{mime or 'image/png'};base64,{b64}"

    user_text = USER_TEMPLATE.format(
        palette="、".join(hints.get("palette", [])) or "（未知）",
        tone=hints.get("tone", ""),
        grid_columns=hints.get("grid_columns", ""),
        modules=hints.get("modules", ""),
        margins=hints.get("margins", ""),
    )

    payload = {
        "model": config.VISION_MODEL or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {config.VISION_API_KEY}",
        "Content-Type": "application/json",
    }
    base = (config.VISION_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"

    with httpx.Client(trust_env=config.VISION_TRUST_ENV, timeout=300) as client:
        resp = client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(content)
