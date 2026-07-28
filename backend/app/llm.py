"""文本推理 / 需求解读大模型客户端（OpenAI 兼容 Chat Completions）。

默认指向火山引擎方舟（Ark），也兼容任意 OpenAI 兼容文本服务。
用于：需求文本解读、把「设计视觉概论」的聚合数据写成成体系的设计方法论。
凭证只通过环境变量注入（见 config.LLM_*），不写入代码库。
"""
from __future__ import annotations

import json
import re

import httpx

from . import config


def chat(
    messages: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 1500,
    timeout: float = 300.0,
) -> str:
    """调用文本模型，返回回复正文。失败抛异常，由上层回退。

    timeout 默认放宽到 300s：长文本（如设计方法论）生成较慢，避免读超时。
    """
    base = (config.LLM_BASE_URL or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = httpx.post(f"{base}/chat/completions", json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_json(messages: list[dict], **kw) -> dict:
    """要求返回 JSON 的对话，稳健解析。"""
    text = chat(messages, **kw).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.S)
        if brace:
            text = brace.group(0)
    return json.loads(text)
