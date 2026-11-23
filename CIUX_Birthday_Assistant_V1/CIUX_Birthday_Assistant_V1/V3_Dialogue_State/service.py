from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _birthday_in_year(birthday: date, year: int) -> date:
    try:
        return date(year, birthday.month, birthday.day)
    except ValueError:
        if birthday.month == 2 and birthday.day == 29:
            return date(year, 2, 28)
        raise


def _next_birthday(birthday: date, today: date) -> date:
    occurrence = _birthday_in_year(birthday, today.year)
    if occurrence < today:
        occurrence = _birthday_in_year(birthday, today.year + 1)
    return occurrence


def format_rows(rows: pd.DataFrame) -> str:
    """Format matching spreadsheet rows as readable birthday lines."""
    if rows.empty:
        return "No matching birthdays were found."

    lines = []
    for _, row in rows.iterrows():
        birthday = _as_date(row["DOB"])
        relationship = str(row.get("Relationship", "")).strip()
        suffix = f" ({relationship})" if relationship else ""
        lines.append(
            f"• {row['Name']} — {birthday.strftime('%d %B %Y')}{suffix}"
        )
    return "\n".join(lines)


def _filter_relationship_and_month(
    people: pd.DataFrame,
    entities: dict[str, Any],
    today: date,
) -> pd.DataFrame:
    rows = people
    relationship = entities.get("relationship")
    if relationship:
        rows = rows[
            rows["Relationship"].astype(str).str.casefold()
            == str(relationship).casefold()
        ]

    month = entities.get("month")
    if entities.get("relative_month") == "next month":
        month = (today.month % 12) + 1
    if month:
        rows = rows[pd.to_datetime(rows["DOB"]).dt.month == int(month)]
    return rows.copy()


def find_result_ids(
    parsed: dict[str, Any],
    people: pd.DataFrame,
    today: date | None = None,
) -> list[str] | None:
    """Return workbook IDs corresponding to the parsed query, when applicable."""
    intent = parsed.get("intent")
    entities = parsed.get("entities") or {}
    if intent not in {"birthday_search", "count_birthdays", "upcoming_birthdays", "person_place"}:
        return None

    today = today or date.today()
    rows = _filter_relationship_and_month(people, entities, today)
    person_id = entities.get("person_id")
    if person_id is not None and "Person_ID" in people.columns:
        rows = people[
            people["Person_ID"].astype(str).str.casefold()
            == str(person_id).casefold()
        ]
    elif entities.get("relative_date") == "tomorrow":
        rows = _on_date(rows, today + timedelta(days=1))
    elif intent == "upcoming_birthdays":
        rows = _upcoming(rows, today)

    if "Person_ID" not in rows.columns:
        return None
    return rows["Person_ID"].astype(str).tolist()


def _on_date(rows: pd.DataFrame, target: date) -> pd.DataFrame:
    matching_indices = []
    for index, row in rows.iterrows():
        birthday = _as_date(row["DOB"])
        if _birthday_in_year(birthday, target.year) == target:
            matching_indices.append(index)
    return rows.loc[matching_indices].copy()


def _upcoming(rows: pd.DataFrame, today: date, days: int = 30) -> pd.DataFrame:
    end = today + timedelta(days=days)
    upcoming = rows.copy()
    upcoming["_next_birthday"] = [
        _next_birthday(_as_date(value), today)
        for value in upcoming["DOB"]
    ]
    upcoming = upcoming[
        (upcoming["_next_birthday"] >= today)
        & (upcoming["_next_birthday"] <= end)
    ]
    return upcoming.sort_values(
        ["_next_birthday", "Name"], kind="stable"
    )


def _format_upcoming(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "No matching birthdays were found in the next 30 days."

    lines = []
    for _, row in rows.iterrows():
        occurrence = _as_date(row["_next_birthday"])
        relationship = str(row.get("Relationship", "")).strip()
        suffix = f" ({relationship})" if relationship else ""
        lines.append(
            f"• {row['Name']} — {occurrence.strftime('%d %B %Y')}{suffix}"
        )
    return "\n".join(lines)


def execute(
    parsed: dict[str, Any],
    people: pd.DataFrame,
    today: date | None = None,
) -> str:
    """Query the Excel-backed DataFrame and return a user-facing answer."""
    today = today or date.today()
    intent = parsed.get("intent", "unknown")
    entities = parsed.get("entities") or {}
    rows = _filter_relationship_and_month(people, entities, today)

    if intent == "unknown":
        return "I couldn't understand that question. Please rephrase it as a birthday, count, upcoming-birthday, or person-location question."

    if intent == "person_place":
        if "person" in parsed.get("ambiguity", []):
            return "I found multiple people matching that name. Please include a unique nickname or another identifying detail."
        person_id = entities.get("person_id")
        if not person_id:
            return "Please include the person's name so I can look up their location."
        matches = people[
            people["Person_ID"].astype(str).str.casefold()
            == str(person_id).casefold()
        ]
        if matches.empty:
            return "I couldn't find that person in the spreadsheet."
        person = matches.iloc[0]
        return f"{person['Name']} stays in {person['Place_of_Stay']}."

    if intent == "count_birthdays":
        if entities.get("relative_date") == "tomorrow":
            rows = _on_date(rows, today + timedelta(days=1))
        return f"I found {len(rows)} matching birthdays."

    if intent == "upcoming_birthdays":
        if entities.get("relative_date") == "tomorrow":
            rows = _on_date(rows, today + timedelta(days=1))
            if rows.empty:
                return "No matching birthdays were found tomorrow."
            return "Birthdays tomorrow:\n" + format_rows(rows)

        upcoming = _upcoming(rows, today)
        if upcoming.empty:
            return "No matching birthdays were found in the next 30 days."
        return "Upcoming birthdays in the next 30 days:\n" + _format_upcoming(upcoming)

    if intent == "birthday_search":
        if "person" in parsed.get("ambiguity", []):
            return "I found multiple people matching that name. Please include a unique nickname or another identifying detail."

        person_id = entities.get("person_id")
        if person_id:
            matches = people[
                people["Person_ID"].astype(str).str.casefold()
                == str(person_id).casefold()
            ]
            if matches.empty:
                return "I couldn't find that person in the spreadsheet."
            person = matches.iloc[0]
            birthday = _as_date(person["DOB"])
            return (
                f"{person['Name']}'s birthday is "
                f"{birthday.strftime('%d %B %Y')}."
            )

        if entities.get("relative_date") == "tomorrow":
            rows = _on_date(rows, today + timedelta(days=1))
        if rows.empty:
            if entities.get("month") or entities.get("relative_month"):
                return "No matching birthdays were found for that time period."
            if entities.get("relationship"):
                return (
                    "No matching birthdays were found for "
                    f"{entities['relationship']}."
                )
            return "Please include a person's name, relationship, or month."

        if len(rows) == 1:
            person = rows.iloc[0]
            birthday = _as_date(person["DOB"])
            return (
                f"{person['Name']}'s birthday is "
                f"{birthday.strftime('%d %B %Y')}."
            )
        return "Matching birthdays:\n" + format_rows(rows)

    return "I couldn't understand that question. Please rephrase it."
