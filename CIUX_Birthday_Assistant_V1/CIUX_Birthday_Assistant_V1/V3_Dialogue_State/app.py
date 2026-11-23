import os
import re

from flask import Flask, jsonify, render_template, request, session

from data_service import load_people
from nlu import parse
from dialogue import enrich_with_context, resolve_clarification, update_state
from service import execute, find_result_ids

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "v3-local-development-only-change-this-secret",
)
PEOPLE = load_people()


@app.get("/")
def index():
    return render_template(
        "index.html",
        record_count=len(PEOPLE),
        dialogue_state=session.get("dialogue_state", {}),
    )


def _is_reset_message(message):
    normalized = re.sub(r"[.!?]+$", "", message.casefold().strip())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in {
        "reset",
        "reset conversation",
        "reset the conversation",
        "start over",
        "clear conversation",
    }


def _clear_conversation():
    session.clear()
    return {"month": None, "relationship": None, "person_id": None, "person_name": None}


def _needs_relationship_clarification(message, parsed, people):
    if (
        parsed.get("intent") != "birthday_search"
        or not parsed.get("entities", {}).get("relationship")
        or parsed.get("entities", {}).get("person_id")
        or parsed.get("entities", {}).get("month")
        or not re.search(r"\bwhen\s+is\b", message, re.IGNORECASE)
    ):
        return False
    result_ids = find_result_ids(parsed, people)
    return result_ids is not None and len(result_ids) > 1


@app.post("/api/chat")
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
            debug={"intent": "reset", "entities": {}},
            trace=["Conversation state cleared"],
            dialogue_state=dialogue_state,
        )

    state = session.get("dialogue_state", {})
    if not isinstance(state, dict):
        state = {}
    parsed = parse(message, PEOPLE)
    pending = state.get("pending_clarification")

    if pending:
        resolved, clarification_message = resolve_clarification(message, state, PEOPLE)
        if resolved is None:
            answer = clarification_message or "Please tell me which person you mean."
            dialogue_state = state
            debug = parsed
            session["dialogue_state"] = dialogue_state
            return jsonify(
                answer=answer,
                debug=debug,
                trace=["Waiting for a person name to resolve the clarification"],
                dialogue_state=dialogue_state,
            )
        parsed = resolved
        state = dict(state)
        state.pop("pending_clarification", None)
    else:
        parsed = enrich_with_context(parsed, state)

    if _needs_relationship_clarification(message, parsed, PEOPLE):
        candidate_ids = find_result_ids(parsed, PEOPLE) or []
        candidates = PEOPLE[
            PEOPLE["Person_ID"].astype(str).isin(candidate_ids)
        ]
        relationship = parsed["entities"]["relationship"]
        names = ", ".join(candidates["Name"].astype(str).tolist())
        answer = (
            "I found multiple people with that relationship. "
            f"Which one do you mean? Please reply with a name: {names}."
        )
        state = update_state(parsed, state, candidate_ids)
        state["pending_clarification"] = {
            "relationship": relationship,
            "intent": parsed["intent"],
            "candidate_ids": candidate_ids,
        }
        dialogue_state = state
    else:
        answer = execute(parsed, PEOPLE)
        result_ids = find_result_ids(parsed, PEOPLE)
        dialogue_state = update_state(parsed, state, result_ids)
        dialogue_state.pop("pending_clarification", None)

    session["dialogue_state"] = dialogue_state
    trace = [
        f"Detected intent: {parsed['intent']}",
        f"Extracted entities: {parsed['entities']}",
    ]
    if parsed.get("context_used"):
        trace.append("Applied saved month/relationship context")
    if parsed.get("clarification_resolved"):
        trace.append("Resolved the requested person from the clarification candidates")
    return jsonify(
        answer=answer,
        debug=parsed,
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
    return jsonify(status="ok", records=len(PEOPLE), version="V3")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
