# CIUX Birthday Assistant — Version 2

**GM University · School of Computer Science and Technology**  
**Course:** UE24CS3540 — Conversational Interfaces and UX  
**Academic year:** 2026–27

Version 2 (V2) is a standalone continuation of Version 1. It keeps the same
Flask, Pandas, Excel, and browser interface, while separating language
understanding from data querying. V2 uses transparent rules; it does not use an
LLM, machine-learning model, vector database, RAG, or external API.

## Objective

V1 matched phrases directly to response rules. V2 first classifies each
question's **intent** (what the user wants) and extracts **entities** (values
such as a month, relationship, or person). A separate service then uses those
values to query the workbook.

## Architecture

```text
User Browser → Flask → Intent and Entity Parser → Query Service
            → Pandas → people.xlsx → Response
```

Every question is handled independently. V2 has no conversation memory or
context carry-over.

## Intents and entities

The rule-based parser in `nlu.py` selects one of these intents:

- `birthday_search` — find one person's birthday or filter birthdays.
- `count_birthdays` — count records matching the question.
- `upcoming_birthdays` — find birthdays tomorrow or in the next 30 days.
- `person_place` — look up a named person's place of stay.
- `unknown` — the question does not match a supported request.

It extracts these entities when present:

- `month`: a month number from 1 to 12.
- `relative_date`: `tomorrow`.
- `relative_month`: `next month`.
- `relationship`: a relationship value found in the workbook.
- `person_name` and `person_id`: a unique name or nickname match resolved
  against the workbook.

Matching uses word boundaries so a short word does not accidentally match
inside a longer word. Full names are preferred to nicknames. If a name or
nickname is ambiguous, no person ID is selected; the answer asks for more
identifying detail.

For example, with the supplied dataset:

```text
Question: Count nephew birthdays in September.
Intent: count_birthdays
Entities: {"relationship": "Nephew", "month": 9}
```

```text
Question: Where does Rahul Patil stay?
Intent: person_place
Entities: {"person_name": "Rahul Patil", "person_id": "<resolved from Excel>"}
```

The actual ID is resolved at runtime from `people.xlsx`; it is not embedded in
the parser.

## Main files

- `nlu.py` classifies a question and extracts dataset-backed entities.
- `service.py` filters the Pandas DataFrame, formats factual answers, and
  safely calculates birthday occurrences, including leap-day birthdays.
- `data_service.py` loads and validates the existing Excel workbook. It is
  copied from V1.
- `app.py` loads the workbook once, serves the page, connects NLU to the query
  service, and provides `/api/health` and `/api/chat`.
- `templates/index.html`, `static/chat.js`, and `static/style.css` provide the
  browser interface. The page shows the parsed intent and entities.
- `tests/test_nlu_service.py` tests the parser and service using small,
  synthetic in-memory data rather than the project workbook.

## Folder structure

```text
V2_Intent_Entity/
├── app.py
├── data_service.py
├── nlu.py
├── service.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── people.xlsx
├── templates/
│   └── index.html
├── static/
│   ├── chat.js
│   └── style.css
└── tests/
    └── test_nlu_service.py
```

The workbook is copied from V1 and is not changed by V2.

## Install and run in VS Code (Python 3.10)

Open the `V2_Intent_Entity` folder in VS Code, then open **Terminal → New
Terminal**. In PowerShell, create and activate a Python 3.10 environment:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, use the Python 3.10 environment directly:

```powershell
py -3.10 -m pip install -r requirements.txt
py -3.10 app.py
```

Open <http://127.0.0.1:5000> in a browser. If V1 is already running on port
5000, stop that app before starting V2, or stop V2 before restarting V1.

## Tests

Run tests from the V2 folder:

```powershell
py -3.10 -m pytest -q
```

The tests cover counts, individual birthday searches, upcoming birthdays,
locations, relationship and month extraction, tomorrow and next-month
expressions, person ID resolution, unknown input, empty results, ambiguous
person matches, and leap-day handling. Test records are synthetic and are not
read from the workbook.

## Questions to try

- `When is Rahul Patil's birthday?`
- `How many birthdays are there next month?`
- `Count nephew birthdays in September.`
- `Is there any birthday tomorrow?`
- `Show upcoming birthdays.`
- `Where does Rahul Patil stay?`

The **NLU Debug** panel displays the intent and entities found for each
question. Answers about birthdays and locations come from the Excel file.

## Limitations and future work

V2 processes each request without remembering earlier requests. For example,
after asking `Count nephew birthdays in September`, the follow-up `What about
October?` cannot be interpreted as another nephew count. The user must repeat
the full request, such as `Count nephew birthdays in October.` Carrying meaning
from one turn to the next requires dialogue state and context resolution, which
are reserved for V3.

The parser recognizes a bounded set of transparent patterns and does not
understand every paraphrase. Ambiguous person matches are not guessed.

## Difference between V1 and V2

- **V1:** directly matches phrases to deterministic rules and returns a rule
  trace.
- **V2:** first returns an intent and structured entities, then passes that
  parse to a separate Pandas query service. The browser displays the NLU
  result.

Both versions use Flask and the workbook as the factual source. V2 is kept in
its own folder so V1 remains unchanged.
