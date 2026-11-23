from __future__ import annotations

import calendar
import os
import re
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from data_service import load_people
from dialogue import enrich_with_context, resolve_clarification, update_state
from llm_nlu import ALLOWED_ENTITIES, ALLOWED_INTENTS, LLMNLUError, parse_with_llm
from nlu import parse as rule_parse
from service import execute, find_result_ids


load_dotenv()

app = Flask(__name__)
app.secret_key = (
    os.environ.get("FLASK_SECRET")
    or os.environ.get("FLASK_SECRET_KEY")
    or "v4-local-development-only-change-this-secret"
)
PEOPLE = load_people()
RELATIONSHIP_VALUES = {
    str(value).strip().casefold(): str(value).strip()
    for column in ("Relationship", "Relationship_Group")
    if column in PEOPLE.columns
    for value in PEOPLE[column].dropna().astype(str)
    if str(value).strip()
}
PLACE_VALUES = {
    str(value).strip().casefold(): str(value).strip()
    for value in PEOPLE["Place_of_Stay"].dropna().astype(str)
    if str(value).strip()
}
MONTH_VALUES = {
    name.casefold(): month
    for month, name in enumerate(calendar.month_name)
    if name
}
INTERNAL_ENTITY_FIELDS = ALLOWED_ENTITIES | {
    "person_id",
    "person_name",
}


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(
        r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)",
        text.casefold(),
    ) is not None


def _canonical_relationship(value: str) -> str | None:
    normalized = value.casefold().strip()
    if normalized in RELATIONSHIP_VALUES:
        return RELATIONSHIP_VALUES[normalized]
    if normalized.endswith("s") and normalized[:-1] in RELATIONSHIP_VALUES:
        return RELATIONSHIP_VALUES[normalized[:-1]]
    return None


def _person_candidates_from_text(message: str, people=PEOPLE):
    if "Name" not in people.columns:
        return people.iloc[0:0]
    full_matches = people[
        people["Name"].apply(
            lambda value: bool(value) and _contains_phrase(message, str(value))
        )
    ]
    if not full_matches.empty:
        return full_matches

    if "Nickname" not in people.columns:
        return people.iloc[0:0]
    nicknames = people[
        people["Nickname"].apply(
            lambda value: (
                bool(value)
                and len(str(value).strip()) >= 3
                and _contains_phrase(message, str(value).strip())
            )
        )
    ]
    return nicknames


def validate_and_ground(
    parsed: dict[str, Any],
    message: str,
    people=PEOPLE,
    *,
    trust_rule_person_id: bool = False,
) -> tuple[dict[str, Any], str, list[str]]:
    """Validate NLU output and resolve names only against workbook rows."""
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("intent"), str)
        or parsed["intent"] not in ALLOWED_INTENTS
    ):
        raise ValueError("NLU returned an invalid intent.")
    entities = parsed.get("entities")
    if not isinstance(entities, dict):
        raise ValueError("NLU entities must be an object.")
    if not set(entities).issubset(INTERNAL_ENTITY_FIELDS):
        raise ValueError("NLU returned unsupported entity fields.")

    normalized: dict[str, Any] = {"intent": parsed["intent"], "entities": {}}
    target_entities = normalized["entities"]

    month = entities.get("month")
    if month is not None:
        if isinstance(month, str) and month.casefold().strip() in MONTH_VALUES:
            month = MONTH_VALUES[month.casefold().strip()]
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError("NLU returned an invalid month.")
        target_entities["month"] = month

    relative_date = entities.get("relative_date")
    if relative_date is not None:
        if not isinstance(relative_date, str) or relative_date.casefold().strip() not in {
            "today",
            "tomorrow",
        }:
            raise ValueError("NLU returned an unsupported relative date.")
        target_entities["relative_date"] = relative_date.casefold().strip()

    relative_month = entities.get("relative_month")
    if relative_month is not None:
        if not isinstance(relative_month, str) or relative_month.casefold().strip() not in {
            "this month",
            "next month",
        }:
            raise ValueError("NLU returned an unsupported relative month.")
        target_entities["relative_month"] = relative_month.casefold().strip()

    for key in ("relationship", "place", "person_name"):
        value = entities.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or len(value.strip()) > 120:
            raise ValueError(f"NLU returned an invalid {key} value.")
        value = value.strip()
        if key == "relationship":
            canonical = _canonical_relationship(value)
            if canonical is None:
                raise ValueError("NLU returned a relationship not found in the workbook.")
            target_entities[key] = canonical
        elif key == "place":
            canonical_place = PLACE_VALUES.get(value.casefold())
            if canonical_place is None:
                raise ValueError("NLU returned a place not found in the workbook.")
            target_entities[key] = canonical_place
        else:
            target_entities[key] = value

    # Never trust a model-supplied ID. A rule-parser ID is also rechecked against
    # the loaded workbook before it can be used.
    candidate_rows = _person_candidates_from_text(message, people)
    proposed_name = target_entities.get("person_name")
    raw_person_id = entities.get("person_id") if trust_rule_person_id else None
    rule_person_rows = people.iloc[0:0]
    if raw_person_id:
        rule_person_rows = people[
            people["Person_ID"].astype(str).str.casefold()
            == str(raw_person_id).casefold()
        ]
        if not rule_person_rows.empty:
            rule_person = rule_person_rows.iloc[0]
            mentioned = _contains_phrase(message, str(rule_person["Name"]))
            nickname = str(rule_person.get("Nickname", "")).strip()
            mentioned = mentioned or bool(
                nickname and _contains_phrase(message, nickname)
            )
            if not mentioned:
                rule_person_rows = people.iloc[0:0]

    if proposed_name and not _contains_phrase(message, proposed_name):
        if not rule_person_rows.empty:
            candidate_rows = rule_person_rows
        elif len(candidate_rows) == 1:
            candidate = candidate_rows.iloc[0]
            grounded_name = str(candidate["Name"]).casefold()
            grounded_nickname = str(candidate.get("Nickname", "")).casefold()
            if proposed_name.casefold() not in {
                grounded_name,
                grounded_nickname,
            }:
                candidate_rows = people.iloc[0:0]
        elif candidate_rows.empty:
            candidate_rows = people.iloc[0:0]

    raw_person_id = entities.get("person_id") if trust_rule_person_id else None
    if raw_person_id:
        if not rule_person_rows.empty:
            candidate_rows = rule_person_rows

    candidate_ids = candidate_rows["Person_ID"].astype(str).tolist()
    grounding_status = "Validated; entities grounded against the workbook."
    if len(candidate_ids) == 1:
        person = candidate_rows.iloc[0]
        target_entities["person_id"] = str(person["Person_ID"])
        target_entities["person_name"] = str(person["Name"]).strip()
        grounding_status = "Validated; person resolved to a workbook Person_ID."
    elif len(candidate_ids) > 1:
        normalized["ambiguity"] = ["person"]
        grounding_status = "Person is ambiguous; clarification is required."
    elif proposed_name:
        grounding_status = "Person name not found in the workbook; no ID assigned."
    elif "person_id" in entities:
        grounding_status = "Untrusted Person_ID ignored; no workbook match was grounded."

    # Carry only recognized parser metadata; user-visible debug excludes candidate IDs.
    if parsed.get("context_used"):
        normalized["context_used"] = True
    return normalized, grounding_status, candidate_ids


def _is_reset_message(message: str) -> bool:
    normalized = re.sub(r"[.!?]+$", "", message.casefold().strip())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in {
        "reset",
        "reset conversation",
        "reset the conversation",
        "start over",
        "clear conversation",
    }


def _clear_conversation() -> dict[str, Any]:
    session.clear()
    return {"month": None, "relationship": None, "person_id": None, "person_name": None}


def _needs_relationship_clarification(message: str, parsed: dict[str, Any]) -> bool:
    entities = parsed.get("entities", {})
    if parsed.get("ambiguity") == ["person"]:
        return True
    if (
        parsed.get("intent") != "birthday_search"
        or not entities.get("relationship")
        or entities.get("person_id")
        or entities.get("month")
        or entities.get("relative_month")
    ):
        return False
    singular_request = re.search(
        r"\b(?:when\s+is|my\b.*\bbirthday|birthday\s+of)\b",
        message,
        re.IGNORECASE,
    )
    if not singular_request:
        return False
    result_ids = find_result_ids(parsed, PEOPLE)
    return result_ids is not None and len(result_ids) > 1


def _is_unresolved_person_question(message: str, parsed: dict[str, Any]) -> bool:
    entities = parsed.get("entities", {})
    if (
        parsed.get("intent") != "birthday_search"
        or entities.get("person_id")
        or entities.get("person_name")
        or entities.get("relationship")
    ):
        return False
    return bool(
        re.search(
            r"\b(?:when\s+is|whether|does)\s+.+?"
            r"(?:'s\s+birthday|has\s+(?:a\s+)?birthday|have\s+(?:a\s+)?birthday)\b",
            message,
            re.IGNORECASE,
        )
    )


def _select_nlu(
    message: str,
) -> tuple[dict[str, Any], str, str, str | None]:
    if os.environ.get("GROQ_API_KEY"):
        try:
            raw = parse_with_llm(message)
            normalized, status, candidate_ids = validate_and_ground(raw, message)
            return (
                {**normalized, "_candidate_ids": candidate_ids},
                "LLM NLU",
                status,
                None,
            )
        except Exception as exc:
            fallback_reason = (
                str(exc) if isinstance(exc, (LLMNLUError, ValueError))
                else "LLM request failed."
            )
    else:
        fallback_reason = "GROQ_API_KEY is not configured."

    raw = rule_parse(message, PEOPLE)
    normalized, status, candidate_ids = validate_and_ground(
        raw,
        message,
        trust_rule_person_id=True,
    )
    return (
        {**normalized, "_candidate_ids": candidate_ids},
        "Rule-based fallback",
        status,
        fallback_reason,
    )


@app.get("/")
def index():
    return render_template(
        "index.html",
        record_count=len(PEOPLE),
        dialogue_state=session.get("dialogue_state", {}),
    )


@app.post("/api/chat")
@app.post("/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    message = payload.get("message", "")
    if not isinstance(message, str):
        message = ""

    if _is_reset_message(message):
        dialogue_state = _clear_conversation()
        return jsonify(
            answer="Conversation reset. I won't reuse earlier context.",
            debug={
                "intent": "reset",
                "entities": {},
                "nlu_method": "Rule-based fallback",
                "grounding_status": "Session cleared.",
            },
            trace=["Conversation state cleared"],
            dialogue_state=dialogue_state,
        )

    state = session.get("dialogue_state", {})
    if not isinstance(state, dict):
        state = {}
    pending = state.get("pending_clarification")
    fallback_reason = None

    if pending:
        parsed, clarification_message = resolve_clarification(
            message, state, PEOPLE
        )
        nlu_method = "Rule-based fallback"
        grounding_status = "Name checked against pending workbook candidates."
        candidate_ids = pending.get("candidate_ids", [])
        if parsed is None:
            dialogue_state = state
            debug = {
                "intent": "clarification",
                "entities": {},
                "nlu_method": nlu_method,
                "grounding_status": grounding_status,
            }
            session["dialogue_state"] = dialogue_state
            return jsonify(
                answer=clarification_message or "Please tell me which person you mean.",
                debug=debug,
                trace=["Waiting for a person name to resolve the clarification"],
                dialogue_state=dialogue_state,
            )
        parsed["clarification_resolved"] = True
        state = dict(state)
        state.pop("pending_clarification", None)
    else:
        raw_parsed, nlu_method, grounding_status, fallback_reason = _select_nlu(
            message
        )
        candidate_ids = raw_parsed.pop("_candidate_ids", [])
        parsed = raw_parsed
        entities = parsed.get("entities") or {}

        if _is_unresolved_person_question(message, parsed):
            grounding_status = "Person name not found in the workbook; no query executed."
            answer = "I couldn't find that person in the spreadsheet. Please check the name and try again."
            dialogue_state = state
            debug = {
                **parsed,
                "nlu_method": nlu_method,
                "grounding_status": grounding_status,
            }
            if fallback_reason:
                debug["fallback_reason"] = fallback_reason
            session["dialogue_state"] = dialogue_state
            return jsonify(
                answer=answer,
                debug=debug,
                trace=["No query executed for an ungrounded person name"],
                dialogue_state=dialogue_state,
            )

        # A supplied but unmatched name must never fall through to a broad query.
        if (
            entities.get("person_name")
            and not entities.get("person_id")
            and not parsed.get("ambiguity")
        ):
            grounding_status = "Person name not found in the workbook; no query executed."
            answer = "I couldn't find that person in the spreadsheet. Please check the name and try again."
            dialogue_state = state
            debug = {
                **parsed,
                "nlu_method": nlu_method,
                "grounding_status": grounding_status,
            }
            session["dialogue_state"] = dialogue_state
            return jsonify(
                answer=answer,
                debug=debug,
                trace=["No query executed for an ungrounded person name"],
                dialogue_state=dialogue_state,
            )

        parsed = enrich_with_context(parsed, state)
        candidate_ids = parsed.get("_candidate_ids", candidate_ids)

    entities = parsed.get("entities") or {}
    relationship_clarification = _needs_relationship_clarification(message, parsed)
    person_ambiguity = parsed.get("ambiguity") == ["person"]
    if relationship_clarification or person_ambiguity:
        if not candidate_ids and entities.get("relationship"):
            candidate_ids = find_result_ids(parsed, PEOPLE) or []
        candidates = PEOPLE[
            PEOPLE["Person_ID"].astype(str).isin(
                {str(value) for value in candidate_ids}
            )
        ]
        if len(candidates) > 1:
            names = ", ".join(candidates["Name"].astype(str).tolist())
            if person_ambiguity:
                answer = (
                    "I found multiple people matching that name. "
                    f"Which one do you mean? Please reply with a name: {names}."
                )
            else:
                relationship = entities["relationship"]
                answer = (
                    "I found multiple people with that relationship. "
                    f"Which one do you mean? Please reply with a name: {names}."
                )
            state = update_state(parsed, state, candidate_ids)
            state["pending_clarification"] = {
                "relationship": entities.get("relationship"),
                "intent": parsed["intent"],
                "candidate_ids": [str(value) for value in candidate_ids],
            }
            dialogue_state = state
            grounding_status = "Multiple workbook candidates; waiting for clarification."
        else:
            answer = execute(parsed, PEOPLE)
            dialogue_state = update_state(
                parsed, state, find_result_ids(parsed, PEOPLE)
            )
            grounding_status = "Validated; query executed against workbook records."
    else:
        answer = execute(parsed, PEOPLE)
        dialogue_state = update_state(
            parsed, state, find_result_ids(parsed, PEOPLE)
        )
        dialogue_state.pop("pending_clarification", None)

    session["dialogue_state"] = dialogue_state
    debug = {
        "intent": parsed["intent"],
        "entities": parsed["entities"],
        "nlu_method": nlu_method,
        "grounding_status": grounding_status,
    }
    if fallback_reason:
        debug["fallback_reason"] = fallback_reason
    if parsed.get("ambiguity"):
        debug["ambiguity"] = parsed["ambiguity"]
    if parsed.get("context_used"):
        debug["context_used"] = True
    if parsed.get("clarification_resolved"):
        debug["clarification_resolved"] = True
    trace = [
        f"Detected intent: {parsed['intent']}",
        f"NLU method: {nlu_method}",
        f"Grounding: {grounding_status}",
    ]
    if fallback_reason:
        trace.append(f"Fallback reason: {fallback_reason}")
    if parsed.get("context_used"):
        trace.append("Applied saved month/relationship context")
    if parsed.get("clarification_resolved"):
        trace.append("Resolved the requested person from clarification candidates")
    return jsonify(
        answer=answer,
        debug=debug,
        trace=trace,
        dialogue_state=dialogue_state,
    )


@app.post("/reset")
def reset():
    dialogue_state = _clear_conversation()
    return jsonify(
        success=True,
        answer="Conversation reset.",
        dialogue_state=dialogue_state,
    )


@app.get("/api/health")
def health():
    return jsonify(status="ok", records=len(PEOPLE), version="V4")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
