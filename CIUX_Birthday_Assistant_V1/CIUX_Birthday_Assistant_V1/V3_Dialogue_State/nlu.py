from __future__ import annotations

import calendar
import re
from typing import Any

import pandas as pd


MONTHS = {
    name.casefold(): month
    for month, name in enumerate(calendar.month_name)
    if name
}
COUNT_PATTERN = re.compile(r"\b(?:how many|count|number of|total)\b")
LOCATION_PATTERN = re.compile(r"\b(?:where|stay|stays|live|lives|location|place)\b")
UPCOMING_PATTERN = re.compile(
    r"\b(?:tomorrow|upcoming)\b|"
    r"\b(?:next|coming)\s+(?:7|30)\s+days\b"
)
BIRTHDAY_PATTERN = re.compile(r"\b(?:birthdays?|birth date|born)\b")


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(
        r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)",
        text.casefold(),
    ) is not None


def _relationship_terms(people: pd.DataFrame) -> list[tuple[str, str]]:
    terms: dict[str, str] = {}
    if "Relationship" not in people.columns:
        return []

    for value in people["Relationship"].dropna().astype(str):
        label = value.strip()
        if not label:
            continue
        terms[label.casefold()] = label
        if not label.casefold().endswith("s"):
            plural = label + "s"
            terms[plural.casefold()] = label

    return sorted(terms.items(), key=lambda item: len(item[0]), reverse=True)


def _matching_people(people: pd.DataFrame, text: str, column: str) -> set[Any]:
    if column not in people.columns:
        return set()
    matches: set[Any] = set()
    for index, value in people[column].items():
        if pd.isna(value):
            continue
        phrase = str(value).strip()
        if len(phrase) >= 3 and _contains_phrase(text, phrase):
            matches.add(index)
    return matches


def _person_entities(people: pd.DataFrame, text: str) -> tuple[dict[str, Any], bool]:
    if "Name" not in people.columns:
        return {}, False

    full_name_matches = _matching_people(people, text, "Name")
    nickname_matches = _matching_people(people, text, "Nickname")
    candidate_matches = full_name_matches or nickname_matches

    if len(full_name_matches) > 1:
        remaining_text = text
        for index in full_name_matches:
            name = str(people.loc[index, "Name"]).strip()
            remaining_text = re.sub(
                r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                " ",
                remaining_text,
                flags=re.IGNORECASE,
            )
        explicit_nicknames = _matching_people(
            people, remaining_text, "Nickname"
        )
        disambiguated = full_name_matches.intersection(explicit_nicknames)
        if len(disambiguated) == 1:
            candidate_matches = disambiguated
        else:
            return {}, True
    elif full_name_matches:
        candidate_matches = full_name_matches

    if len(candidate_matches) != 1:
        return {}, len(candidate_matches) > 1

    index = next(iter(candidate_matches))
    person = people.loc[index]
    return {
        "person_id": str(person["Person_ID"]) if "Person_ID" in people.columns else "",
        "person_name": str(person["Name"]).strip(),
    }, False


def parse(question: str, people: pd.DataFrame) -> dict[str, Any]:
    """Classify a single question and extract values grounded in the dataset."""
    text = re.sub(r"\s+", " ", question.casefold().strip()) if isinstance(question, str) else ""
    entities: dict[str, Any] = {}

    for month_name, month_number in MONTHS.items():
        if _contains_phrase(text, month_name):
            entities["month"] = month_number
            break

    if _contains_phrase(text, "tomorrow"):
        entities["relative_date"] = "tomorrow"
    if _contains_phrase(text, "next month"):
        entities["relative_month"] = "next month"

    for term, label in _relationship_terms(people):
        if _contains_phrase(text, term):
            entities["relationship"] = label
            break

    person_entities, person_is_ambiguous = _person_entities(people, text)
    entities.update(person_entities)

    if LOCATION_PATTERN.search(text):
        intent = "person_place"
    elif COUNT_PATTERN.search(text):
        intent = "count_birthdays"
    elif UPCOMING_PATTERN.search(text):
        intent = "upcoming_birthdays"
    elif BIRTHDAY_PATTERN.search(text):
        intent = "birthday_search"
    else:
        intent = "unknown"

    parsed: dict[str, Any] = {"intent": intent, "entities": entities}
    if person_is_ambiguous:
        parsed["ambiguity"] = ["person"]
    return parsed
