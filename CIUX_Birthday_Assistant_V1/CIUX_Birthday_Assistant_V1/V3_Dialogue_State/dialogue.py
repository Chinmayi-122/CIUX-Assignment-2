from __future__ import annotations

from typing import Any

import pandas as pd

from nlu import parse


CONTEXT_INTENTS = {"birthday_search", "count_birthdays", "upcoming_birthdays"}


def enrich_with_context(
    parsed: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Fill omitted month or relationship values on a recognizable follow-up."""
    enriched = dict(parsed)
    entities = dict(parsed.get("entities") or {})
    context_values = {
        "month": state.get("month"),
        "relationship": state.get("relationship"),
    }

    has_new_context_entity = any(entities.get(key) for key in context_values)
    previous_intent = state.get("last_intent")
    if (
        parsed.get("intent") == "unknown"
        and has_new_context_entity
        and previous_intent in CONTEXT_INTENTS
    ):
        for key, value in context_values.items():
            if key not in entities and value is not None:
                entities[key] = value
        enriched["intent"] = previous_intent
        enriched["context_used"] = True

    enriched["entities"] = entities
    return enriched


def update_state(
    parsed: dict[str, Any],
    state: dict[str, Any],
    last_result_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a new dialogue state with the latest known entities and results."""
    updated = dict(state)
    entities = parsed.get("entities") or {}

    for key in ("month", "relationship", "person_id", "person_name"):
        if key in entities:
            updated[key] = entities[key]

    if parsed.get("intent") in CONTEXT_INTENTS:
        updated["last_intent"] = parsed["intent"]
    if last_result_ids is not None:
        updated["last_result_ids"] = [str(person_id) for person_id in last_result_ids]
    return updated


def resolve_clarification(
    message: str,
    state: dict[str, Any],
    people: pd.DataFrame,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve a pending relationship question against only its candidate rows."""
    pending = state.get("pending_clarification")
    if not isinstance(pending, dict):
        return None, None

    candidate_ids = {str(value) for value in pending.get("candidate_ids", [])}
    if not candidate_ids or "Person_ID" not in people.columns:
        return None, "I couldn't find any people to choose from. Please ask the question again."

    candidates = people[
        people["Person_ID"].astype(str).isin(candidate_ids)
    ]
    candidate_parse = parse(message, candidates)
    entities = candidate_parse.get("entities") or {}
    person_id = entities.get("person_id")

    if person_id and str(person_id) in candidate_ids:
        resolved_entities = dict(entities)
        resolved_entities["relationship"] = pending["relationship"]
        return {
            "intent": pending.get("intent", "birthday_search"),
            "entities": resolved_entities,
            "clarification_resolved": True,
        }, None

    relationship = pending.get("relationship", "person")
    names = ", ".join(candidates["Name"].astype(str).tolist())
    if candidate_parse.get("ambiguity"):
        return None, (
            f"I found multiple matching {relationship.lower()}s. "
            f"Please use a full name. Options: {names}."
        )
    return None, (
        f"I couldn't match that name among the {relationship.lower()}s. "
        f"Please reply with a name from: {names}."
    )
