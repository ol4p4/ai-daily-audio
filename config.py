"""
AI Daily Briefing - 配置模块
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    env.update(os.environ)
    return env


ENV = load_env()


class Config:
    SMTP_SERVER = ENV.get("SMTP_SERVER", "smtp.office365.com")
    SMTP_PORT = int(ENV.get("SMTP_PORT", "587"))
    EMAIL_USER = ENV.get("EMAIL_USER", "")
    EMAIL_PASSWORD = ENV.get("EMAIL_PASSWORD", "")
    EMAIL_TO = ENV.get("EMAIL_TO", "") or ENV.get("EMAIL_USER", "")
    EMAIL_FROM = ENV.get("EMAIL_FROM", "") or ENV.get("EMAIL_USER", "")

    TTS_VOICE = ENV.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
    TTS_RATE = ENV.get("TTS_RATE", "+0%")

    _RAW_SOURCES = ENV.get("NEWS_SOURCES", "")
    NEWS_SOURCES = [s.strip() for s in _RAW_SOURCES.splitlines() if s.strip() and not s.strip().startswith("#")]

    MAX_NEWS_PER_DAY = int(ENV.get("MAX_NEWS_PER_DAY", "15"))
    MAX_AUDIO_DURATION_MINUTES = int(ENV.get("MAX_AUDIO_DURATION_MINUTES", "5"))

    OPENAI_API_KEY = ENV.get("OPENAI_API_KEY", "")
    LLM_API_BASE = ENV.get("LLM_API_BASE", "https://integrate.api.nvidia.com/v1")
    LLM_MODEL = ENV.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b")
