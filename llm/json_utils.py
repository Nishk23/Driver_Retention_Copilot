import json
import re
from typing import Any

from agents.prompts import JSON_REPAIR_PROMPT
from llm.llm_client import call_llm


def _strip_fences(raw_text: str) -> str:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_object(raw_text: str) -> str:
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty LLM output.")

    text = _strip_fences(raw_text)
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            _, end = decoder.raw_decode(text[idx:])
            return text[idx : idx + end]
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid JSON object found in LLM output.")


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _schema_validate(data: Any, schema_model: Any) -> dict:
    if schema_model is None:
        return data
    model = schema_model.model_validate(data)
    return model.model_dump()


def repair_json_with_llm(raw_text: str, expected_schema: str) -> dict:
    repaired = call_llm(
        [
            {"role": "system", "content": JSON_REPAIR_PROMPT},
            {
                "role": "user",
                "content": (
                    "Your previous response was invalid JSON. Return only valid JSON matching this schema. "
                    "No prose. No markdown.\n\n"
                    f"Schema:\n{expected_schema}\n\nInvalid response:\n{raw_text}"
                ),
            },
        ],
        temperature=0.0,
    )
    return json.loads(extract_json_object(repaired))


def parse_json_response(raw_text: str, schema_model=None) -> dict:
    expected_schema = (
        schema_model.model_json_schema() if schema_model is not None else "A valid JSON object."
    )
    try:
        text = extract_json_object(raw_text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = json.loads(_remove_trailing_commas(text))
        return _schema_validate(parsed, schema_model)
    except Exception as first_error:
        try:
            repaired = repair_json_with_llm(raw_text, json.dumps(expected_schema, indent=2))
            return _schema_validate(repaired, schema_model)
        except Exception as repair_error:
            return {
                "status": "needs_review",
                "error": "Unable to parse or repair LLM JSON response.",
                "parse_error": str(first_error),
                "repair_error": str(repair_error),
                "raw_text": raw_text,
            }
