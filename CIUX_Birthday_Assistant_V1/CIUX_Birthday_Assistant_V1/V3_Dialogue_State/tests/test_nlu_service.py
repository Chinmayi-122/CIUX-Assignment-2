from datetime import date

import pandas as pd
import pytest

from nlu import parse
from service import execute


@pytest.fixture
def people():
    return pd.DataFrame(
        [
            {
                "Person_ID": "P001",
                "Name": "Ravi Kumar",
                "Nickname": "Ravi",
                "DOB": pd.Timestamp("1988-09-15"),
                "Place_of_Stay": "Bengaluru",
                "Relationship": "Nephew",
            },
            {
                "Person_ID": "P002",
                "Name": "Nikhil Hegde",
                "Nickname": "Nikhil",
                "DOB": pd.Timestamp("2000-09-22"),
                "Place_of_Stay": "Mysuru",
                "Relationship": "Nephew",
            },
            {
                "Person_ID": "P003",
                "Name": "Maya Iyer",
                "Nickname": "Maya",
                "DOB": pd.Timestamp("1992-11-15"),
                "Place_of_Stay": "Bengaluru",
                "Relationship": "Friend",
            },
            {
                "Person_ID": "P004",
                "Name": "Rahul Patil",
                "Nickname": "Rahul",
                "DOB": pd.Timestamp("2004-09-18"),
                "Place_of_Stay": "Pune",
                "Relationship": "Nephew",
            },
            {
                "Person_ID": "P005",
                "Name": "Rahul Patil",
                "Nickname": "Rahu",
                "DOB": pd.Timestamp("1995-02-28"),
                "Place_of_Stay": "Hyderabad",
                "Relationship": "Friend",
            },
            {
                "Person_ID": "P006",
                "Name": "Sam Lee",
                "Nickname": "Sam",
                "DOB": pd.Timestamp("1990-04-29"),
                "Place_of_Stay": "Chennai",
                "Relationship": "Friend",
            },
            {
                "Person_ID": "P007",
                "Name": "Sara Das",
                "Nickname": "Sam",
                "DOB": pd.Timestamp("1991-04-30"),
                "Place_of_Stay": "Delhi",
                "Relationship": "Friend",
            },
        ]
    )


def test_count_birthdays(people):
    parsed = parse("How many birthdays are there next month?", people)
    assert parsed["intent"] == "count_birthdays"
    assert execute(parsed, people, today=date(2026, 8, 20)) == (
        "I found 3 matching birthdays."
    )


def test_birthday_search(people):
    parsed = parse("When is Nikhil Hegde's birthday?", people)
    answer = execute(parsed, people)
    assert parsed["intent"] == "birthday_search"
    assert "Nikhil Hegde" in answer
    assert "22 September 2000" in answer


def test_upcoming_birthdays_sorted_within_thirty_days(people):
    parsed = parse("Show upcoming birthdays.", people)
    answer = execute(parsed, people, today=date(2026, 9, 10))
    assert parsed["intent"] == "upcoming_birthdays"
    assert answer.index("Ravi Kumar") < answer.index("Rahul Patil")
    assert answer.index("Rahul Patil") < answer.index("Nikhil Hegde")
    assert "Maya Iyer" not in answer


def test_person_location(people):
    parsed = parse("Where does Nikhil Hegde stay?", people)
    assert parsed["intent"] == "person_place"
    assert parsed["entities"]["person_id"] == "P002"
    assert execute(parsed, people) == "Nikhil Hegde stays in Mysuru."


def test_relationship_extraction(people):
    parsed = parse("List nephew birthdays.", people)
    assert parsed["entities"]["relationship"] == "Nephew"


def test_month_extraction(people):
    parsed = parse("Count birthdays in September.", people)
    assert parsed["entities"]["month"] == 9


def test_tomorrow_extraction_and_search(people):
    parsed = parse("Is there any birthday tomorrow?", people)
    answer = execute(parsed, people, today=date(2026, 9, 14))
    assert parsed["intent"] == "upcoming_birthdays"
    assert parsed["entities"]["relative_date"] == "tomorrow"
    assert "Ravi Kumar" in answer
    assert "Nikhil Hegde" not in answer


def test_next_month_extraction(people):
    parsed = parse("How many birthdays are there next month?", people)
    assert parsed["entities"]["relative_month"] == "next month"
    assert execute(parsed, people, today=date(2026, 1, 15)) == (
        "I found 1 matching birthdays."
    )


def test_person_name_and_id_resolution_prefers_full_name(people):
    parsed = parse("When is Nikhil Hegde's birthday?", people)
    assert parsed["entities"]["person_name"] == "Nikhil Hegde"
    assert parsed["entities"]["person_id"] == "P002"


def test_full_name_match_takes_precedence_over_nickname_matches(people):
    parsed = parse("When is Ravi Kumar's birthday, Sam?", people)
    assert parsed["entities"]["person_id"] == "P001"


def test_explicit_nickname_disambiguates_duplicate_full_name(people):
    parsed = parse("When is Rahul Patil's birthday, Rahu?", people)
    assert parsed["entities"]["person_id"] == "P005"


def test_unknown_question(people):
    parsed = parse("Tell me something poetic.", people)
    assert parsed["intent"] == "unknown"
    assert "rephrase" in execute(parsed, people).lower()


def test_empty_search_results(people):
    parsed = parse("Any birthdays in January?", people)
    answer = execute(parsed, people)
    assert "no matching birthdays" in answer.lower()


def test_ambiguous_full_name_does_not_choose_person(people):
    parsed = parse("When is Rahul Patil's birthday?", people)
    assert "person_id" not in parsed["entities"]
    assert parsed["ambiguity"] == ["person"]
    assert "multiple people" in execute(parsed, people).lower()


def test_ambiguous_nickname_does_not_choose_person(people):
    parsed = parse("Where does Sam stay?", people)
    assert "person_id" not in parsed["entities"]
    assert parsed["ambiguity"] == ["person"]


def test_february_29_upcoming_birthday_is_safe(people):
    leap_person = pd.DataFrame(
        [
            {
                "Person_ID": "P008",
                "Name": "Leap Day",
                "Nickname": "Leap",
                "DOB": pd.Timestamp("2000-02-29"),
                "Place_of_Stay": "Ooty",
                "Relationship": "Friend",
            }
        ]
    )
    parsed = parse("Show upcoming birthdays.", leap_person)
    answer = execute(parsed, leap_person, today=date(2025, 2, 27))
    assert "Leap Day" in answer
    assert "28 February 2025" in answer
