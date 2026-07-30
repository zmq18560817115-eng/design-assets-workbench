"""应用配置。

通过环境变量控制视觉模型服务的接入方式。未配置任何真实模型时，
系统会自动退回到基于 Pillow 的启发式视觉分析器，保证 Demo 可以离线运行。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent

# Local development reads secrets from the repository-level .env file.
# Existing process environment variables keep precedence in deployments.
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

# 上传图片存储目录
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 数据库（Demo 默认使用 SQLite；生产可切换 PostgreSQL / Supabase）
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'design_assets.db'}")

# 视觉模型服务配置（可选，OpenAI 兼容接口）
#   VISION_PROVIDER: mock（默认，离线启发式）| openai | qwen | volcengine（火山引擎/豆包）| 任意自定义名
#   VISION_API_KEY / VISION_BASE_URL / VISION_MODEL: 对应服务的凭证与地址
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "mock").lower()
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
_VISION_BASE_DEFAULTS = {
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}
VISION_BASE_URL = os.getenv(
    "VISION_BASE_URL", _VISION_BASE_DEFAULTS.get(VISION_PROVIDER, "")
)
VISION_MODEL = os.getenv("VISION_MODEL", "")
VISION_TRUST_ENV = os.getenv("VISION_TRUST_ENV", "false").lower() in {
    "1",
    "true",
    "yes",
}


def vlm_enabled() -> bool:
    """是否启用真实视觉大模型：非 mock 的 provider 且配置了 API Key。

    只要是 OpenAI 兼容接口（GPT Vision / Qwen-VL / 火山引擎豆包 / 内网自建），
    设好 provider 名 + Key + Base URL + Model 即可启用。
    """
    return (
        VISION_PROVIDER not in ("", "mock")
        and bool(VISION_API_KEY)
        and bool(VISION_BASE_URL)
        and bool(VISION_MODEL)
    )


def vision_missing_config() -> list[str]:
    """Return configuration fields still required by the selected provider."""
    if VISION_PROVIDER in ("", "mock"):
        return ["VISION_PROVIDER"]
    missing = []
    if not VISION_API_KEY:
        missing.append("VISION_API_KEY")
    if not VISION_BASE_URL:
        missing.append("VISION_BASE_URL")
    if not VISION_MODEL:
        missing.append("VISION_MODEL")
    return missing


# 文本推理 / 需求解读大模型（可选，OpenAI 兼容；如火山引擎方舟）
#   用于：需求文本解读、把概论聚合数据写成设计方法论
#   LLM_API_KEY / LLM_MODEL 必填即启用；Base URL 默认火山方舟
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
LLM_MODEL = os.getenv("LLM_MODEL", "")  # 火山填「接入点ID ep-xxxx」或模型名


def llm_enabled() -> bool:
    """是否启用文本推理模型：配置了 API Key 与模型/接入点。"""
    return bool(LLM_API_KEY and LLM_MODEL)

# 允许的前端跨域来源
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

# 批量拆解并发数（每个 worker 独立调模型；SQLite 建议 2~4）
try:
    BATCH_CONCURRENCY = max(1, int(os.getenv("BATCH_CONCURRENCY", "3")))
except ValueError:
    BATCH_CONCURRENCY = 3

# Task 5 capability remains off until a real acceptance dataset passes every gate.
ENABLE_LAYOUT_DIRECTIONS = os.getenv(
    "ENABLE_LAYOUT_DIRECTIONS", "false"
).lower() in {"1", "true", "yes"}
