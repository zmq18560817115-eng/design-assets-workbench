"""真实视觉大模型接入（OpenAI 兼容 Chat Completions 接口）。

兼容 GPT Vision、Qwen-VL（DashScope 兼容模式）、以及大多数内网自建的
OpenAI 兼容视觉服务（vLLM / LMDeploy / Ollama 兼容层等）。

设计为「语义增强层」：像素能精确测量的东西（真实色板、页边距、栅格列数）
仍由 Pillow 负责；大模型负责它擅长的语义理解（画面内容、行业场景、风格细腻度、
信息层级、为什么优秀）。未配置或调用失败时，上层会自动退回启发式规则。
"""
from __future__ import annotations

import base64
import io
import json
import re

import httpx
from PIL import Image

from . import config
from .asset_categories import category_focus, category_label, normalize_category
from .layout_blueprint import MODULE_TYPE_ORDER


def _model_image_payload(
    image_bytes: bytes,
    mime: str,
    *,
    max_edge: int = 1600,
) -> tuple[bytes, str]:
    """Bound model payload size while retaining classification detail."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=84, optimize=True)
            prepared = output.getvalue()
        if prepared and len(prepared) < len(image_bytes):
            return prepared, "image/jpeg"
    except Exception:
        pass
    return image_bytes, mime or "image/png"

SYSTEM_PROMPT = (
    "你是资深视觉设计分析师，擅长把一张设计图拆解成结构化的设计知识。"
    "分析时以排版结构为第一优先级、视觉风格为第二优先级，色彩和实拍表现作为辅助维度。"
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
  "canvas_ratio": "宽:高，例如3:4",
  "orientation": "portrait|landscape|square",
  "reading_flow": "阅读动线",
  "focal_region": {{"x":0.1,"y":0.1,"width":0.8,"height":0.5}},
  "information_density": "low|medium|high",
  "text_image_ratio": 0.45,
  "blueprint_modules": [
    {{"id":"module-1","type":"main_title","label":"主标题","x":0.08,"y":0.06,
      "width":0.84,"height":0.12,"importance":1,"alignment":"center",
      "content_summary":"","confidence":0.88}}
  ],
  "layout_summary": "一句话说明版面结构",
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
  "prompt_zh": "可直接用于 AI 绘图的中文白板版式提示词（以排版结构为主、风格特征为辅）",
  "prompt_en": "对应的英文白板版式提示词"
}}

分析优先级：
1. 排版：网格、模块、页边距、留白、对齐、信息层级、阅读动线、标题与图片占比；
2. 风格：视觉语言、情绪、品牌调性和可复用的形式特征；
3. 色彩：主辅色角色、面积比例与对比关系；
4. 实拍图：仅在原图包含摄影内容时分析主体、构图、景别、光线、场景和材质。

排版蓝图规则（Prompt版本 layout-blueprint-v2）：
- 优先识别图片中真实存在的版面结构，不确定时降低 confidence，禁止虚构模块；
- 模块坐标和尺寸必须为 0～1 归一化数值且不能超出画布；
- 区分内容模块和 decoration/background，区分 product/person/scene image；
- blueprint_modules 的 type 只能取以下之一：{module_types}；不得使用其它任何值，输出严格 JSON。

生图提示词必须以“白板版式图/低保真布局白模”为目标：白色或浅灰画布，使用灰阶块、线框、占位图片框和占位文字表现结构，
清楚标注网格、模块、间距、留白和信息层级；不生成完整成品文案，不生成品牌 Logo，不追求成品摄影渲染。
风格与色彩只作为少量注释或点缀，用于辅助表达原图气质，核心必须是可复用、可编辑的版式骨架。

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


def analyze_image(
    image_bytes: bytes,
    mime: str,
    hints: dict,
    asset_category: str = "layout",
) -> dict:
    """调用视觉大模型，返回语义分析字典。失败会抛异常，由上层决定回退。"""
    parsed, _ = analyze_image_with_trace(
        image_bytes, mime, hints, asset_category=asset_category
    )
    return parsed


def analyze_image_with_trace(
    image_bytes: bytes,
    mime: str,
    hints: dict,
    asset_category: str = "layout",
    *,
    additional_instructions: str = "",
    timeout_seconds: float = 300,
    prompt_override: str = "",
    max_tokens: int | None = None,
) -> tuple[dict, str]:
    """Return parsed JSON and the unmodified provider text for calibration."""
    image_bytes, mime = _model_image_payload(image_bytes, mime)
    b64 = base64.b64encode(image_bytes).decode()
    data_uri = f"data:{mime or 'image/png'};base64,{b64}"

    asset_category = normalize_category(asset_category)
    if prompt_override.strip():
        user_text = prompt_override.strip()
    else:
        user_text = USER_TEMPLATE.format(
            palette="、".join(hints.get("palette", [])) or "（未知）",
            tone=hints.get("tone", ""),
            grid_columns=hints.get("grid_columns", ""),
            modules=hints.get("modules", ""),
            margins=hints.get("margins", ""),
            module_types=", ".join(MODULE_TYPE_ORDER),
        )
        user_text += (
            f"\n\n本素材归入「{category_label(asset_category)}」仓库。"
            f"{category_focus(asset_category)}"
            "其余维度仍需返回，但应简洁，并让 summary、critique、improvement、"
            "reusable_methods 与生图提示词优先服务于本仓库的拆解目标。"
        )
        few_shots = hints.get("layout_few_shots") or []
        if few_shots:
            user_text += (
                "\n\n以下仅是人工已确认的同品类排版结构证据。不得复制文案，"
                "不得把当前预测回写为新证据；请参考其模块位置与阅读关系：\n"
                + json.dumps(few_shots[:5], ensure_ascii=False)
            )
    if additional_instructions.strip():
        user_text += f"\n\n本次版本附加约束：\n{additional_instructions.strip()}"

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
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    headers = {
        "Authorization": f"Bearer {config.VISION_API_KEY}",
        "Content-Type": "application/json",
    }
    base = (config.VISION_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"

    with httpx.Client(
        trust_env=config.VISION_TRUST_ENV, timeout=timeout_seconds
    ) as client:
        resp = client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json(content), content


def suggest_asset_category(
    image_bytes: bytes,
    mime: str = "image/png",
    timeout_seconds: float = 300,
) -> dict:
    """Suggest one primary repository category without changing stored metadata."""
    image_bytes, mime = _model_image_payload(image_bytes, mime)
    b64 = base64.b64encode(image_bytes).decode()
    data_uri = f"data:{mime or 'image/png'};base64,{b64}"
    prompt = """
判断这张公司设计成品最适合进入哪个“主要学习仓库”。只能四选一：
- layout：主要学习信息层级、栅格、留白、对齐、图文占比或阅读动线。
- style：主要学习视觉语言、品牌气质、质感、图形元素组合或情绪氛围。
- color：主要学习稳定而有代表性的配色角色、面积比例、对比或色彩策略。
- photo：主要学习真实摄影中的场景、人物、产品摆放、光线、景别或材质表现。

请选择这张图对未来设计最有价值的一个主要学习目标，不要因为图片同时包含文字、颜色和照片就多选。
仅返回 JSON：
{"category":"layout|style|color|photo","confidence":0到100的整数,
"reason":"一句具体理由","signals":["2到4个可见判断依据"]}
"""
    payload = {
        "model": config.VISION_MODEL or "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "你是公司视觉素材库分类员，只输出严格 JSON。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {config.VISION_API_KEY}",
        "Content-Type": "application/json",
    }
    base = (config.VISION_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    with httpx.Client(
        trust_env=config.VISION_TRUST_ENV,
        timeout=timeout_seconds,
    ) as client:
        resp = client.post(
            f"{base}/chat/completions",
            json=payload,
            headers=headers,
        )
    resp.raise_for_status()
    result = _extract_json(resp.json()["choices"][0]["message"]["content"])
    raw_category = str(result.get("category") or "").strip()
    if raw_category not in {"layout", "style", "color", "photo"}:
        raise ValueError("模型未返回有效素材类别")
    category = normalize_category(raw_category)
    return {
        "category": category,
        "confidence": max(0, min(100, int(result.get("confidence") or 0))),
        "reason": str(result.get("reason") or "").strip(),
        "signals": [
            str(item).strip()
            for item in (result.get("signals") or [])
            if str(item).strip()
        ][:4],
    }
