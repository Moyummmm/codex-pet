"""检测 Codex 当前使用的模型提供方(ChatGPT / DeepSeek / 其他)。

读取 ~/.codex/config.toml:顶层 model_provider 指向 model_providers 中的
一项;base_url 或 name 含 "deepseek" 即判定为 DeepSeek 模式。API key
兼容两种存放方式:experimental_bearer_token 字段(直接写在配置里)或
env_key 指定的环境变量。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass


@dataclass
class Provider:
    kind: str              # "chatgpt" | "deepseek" | "other"
    name: str | None = None
    model: str | None = None
    origin: str = ""       # DeepSeek 余额 API 的 origin(如 https://api.deepseek.com)
    api_key: str = ""      # Bearer token(仅在 deepseek 模式下使用)


def _codex_config_path() -> str:
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    return os.path.join(home, "config.toml")


def detect_provider() -> Provider:
    path = _codex_config_path()
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return Provider(kind="chatgpt")

    model = cfg.get("model")
    active = cfg.get("model_provider")
    if not active:
        return Provider(kind="chatgpt", model=model)

    p = (cfg.get("model_providers") or {}).get(active)
    if not isinstance(p, dict):
        return Provider(kind="chatgpt", model=model)

    base_url = str(p.get("base_url") or "")
    name = str(p.get("name") or "")
    if "deepseek" not in (base_url + name).lower():
        # 其他自定义提供方:仍显示 ChatGPT 账户配额
        return Provider(kind="codex", name=name or active, model=model)

    # DeepSeek:余额接口挂在站点根路径下(去掉 /v1 之类的路径部分)
    origin = base_url or "https://api.deepseek.com"
    if "://" in origin:
        origin = origin.split("://", 1)[0] + "://" + origin.split("://", 1)[1].split("/", 1)[0]
    origin = origin.rstrip("/")

    api_key = str(p.get("experimental_bearer_token") or "")
    if not api_key:
        env_key = p.get("env_key")
        if env_key:
            api_key = os.environ.get(str(env_key), "")
    return Provider(kind="deepseek", name=name or "deepseek", model=model,
                    origin=origin, api_key=api_key)
