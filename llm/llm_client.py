import os
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency installed by requirements.
    def load_dotenv() -> None:
        return None


load_dotenv()


def _build_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed. Run `pip install -r requirements.txt`.") from exc

    return OpenAI(
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        timeout=45,
    )


def call_llm(messages: list[dict], temperature: float = 0.2) -> str:
    """Call the configured OpenRouter chat model and return plain text content."""
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("Missing OPENROUTER_API_KEY in environment.")
    if not os.getenv("MODEL_NAME"):
        raise ValueError("Missing MODEL_NAME in environment.")

    try:
        response = _build_client().chat.completions.create(
            model=os.getenv("MODEL_NAME"),
            messages=messages,
            temperature=temperature,
        )
    except TimeoutError as exc:
        raise RuntimeError("OpenRouter API timeout.") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenRouter API failure: {exc}") from exc

    try:
        content = response.choices[0].message.content
    except Exception as exc:
        raise ValueError("Invalid response from LLM provider.") from exc

    if not content:
        raise ValueError("LLM returned empty response.")

    return content
