from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv


ALLOWED_INTENTS = {
    "birthday_search",
    "count_birthdays",
    "upcoming_birthdays",
    "person_place",
    "unknown",
}
ALLOWED_ENTITIES = {
    "person_name",
    "relationship",
    "month",
    "relative_date",
    "relative_month",
    "place",
}
SYSTEM_INSTRUCTION = (
    "You are an NLU parser for a birthday assistant. Return JSON only with "
    "keys intent and entities. Allowed intents: birthday_search, "
    "count_birthdays, upcoming_birthdays, person_place, unknown. Allowed "
    "entities: person_name, relationship, month, relative_date, "
    "relative_month, place. Never answer the user's factual question; only "
    "parse it. Never invent people or facts. Use null for entities that are "
    "not present. month must be an integer from 1 to 12. relative_date may "
    "only be today or tomorrow. relative_month may only be this month or "
    "next month. Only extract names, relationships, and places mentioned by "
    "the user."
)
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMNLUError(ValueError):
    """Raised when an LLM request or structured response cannot be used."""


def _validate_response(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict) or set(parsed) != {"intent", "entities"}:
        raise LLMNLUError("The LLM response must contain only intent and entities.")

    intent = parsed["intent"]
    entities = parsed["entities"]
    if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
        raise LLMNLUError("The LLM returned an invalid intent.")
    if not isinstance(entities, dict):
        raise LLMNLUError("The LLM entities value must be a JSON object.")
    if not set(entities).issubset(ALLOWED_ENTITIES):
        raise LLMNLUError("The LLM returned an unsupported entity field.")

    for key, value in entities.items():
        if value is None:
            continue
        if key == "month":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 12
            ):
                raise LLMNLUError("The LLM returned an invalid month.")
        elif not isinstance(value, str) or len(value.strip()) > 120:
            raise LLMNLUError(f"The LLM returned an invalid {key} value.")
        elif key == "relative_date" and value.casefold().strip() not in {
            "today",
            "tomorrow",
        }:
            raise LLMNLUError("The LLM returned an unsupported relative date.")
        elif key == "relative_month" and value.casefold().strip() not in {
            "this month",
            "next month",
        }:
            raise LLMNLUError("The LLM returned an unsupported relative month.")

    return {
        "intent": intent,
        "entities": {
            key: value.strip() if isinstance(value, str) else value
            for key, value in entities.items()
            if value is not None
        },
    }


def parse_with_llm(message: str, client: Any = None) -> dict[str, Any]:
    """Parse a question into validated JSON using the Groq chat API."""
    load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key and client is None:
        raise LLMNLUError("GROQ_API_KEY is not configured.")
    if not isinstance(message, str) or not message.strip():
        raise LLMNLUError("The message is empty.")

    try:
        if client is None:
            from groq import Groq

            client = Groq(api_key=api_key, timeout=15.0)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": message},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise LLMNLUError("The Groq NLU request failed.") from exc

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise LLMNLUError("The Groq response had an unexpected format.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMNLUError("The Groq response did not contain JSON text.")
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LLMNLUError("The Groq response was not valid JSON.") from exc
    return _validate_response(parsed)
