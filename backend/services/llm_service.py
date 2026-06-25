import os
from functools import lru_cache
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from config import BASE_DIR


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL_NAME = "deepseek-chat"


if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


@lru_cache
def get_deepseek_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("缺少 openai 依赖，请先安装 backend/requirements.txt") from error

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 backend/.env 中配置")

    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
    )


def chat_json(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.1,
) -> str:
    client = get_deepseek_client()

    completion: Any = client.chat.completions.create(
        model=model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL_NAME),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )

    response_text = completion.choices[0].message.content

    if response_text is None:
        raise ValueError("模型返回内容为空")

    return response_text


def chat_text(
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.4,
) -> str:
    client = get_deepseek_client()

    completion: Any = client.chat.completions.create(
        model=model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL_NAME),
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        temperature=temperature,
    )

    response_text = completion.choices[0].message.content

    if response_text is None:
        raise ValueError("模型返回内容为空")

    return response_text
