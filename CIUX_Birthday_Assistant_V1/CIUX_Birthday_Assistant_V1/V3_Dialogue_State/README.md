# CIUX Birthday Assistant — Version 3

**GM University · School of Computer Science and Technology**  
**Course:** UE24CS3540 — Conversational Interfaces and UX  
**Academic year:** 2026–27

V3 is a standalone copy of V2 with dialogue state. It remembers relevant
details during a browser conversation, carries context into short follow-up
questions, and asks the user to identify a person when a relationship query
matches multiple people. The original workbook remains the factual source.
V3 uses transparent rules and Flask sessions; it does not use an LLM, machine
learning, embeddings, vector databases, or RAG.

## V2 and V3

- **V2** handled each message independently. For example, it could not connect
  `What about October?` to an earlier nephew-birthday question.
- **V3** remembers the last birthday intent, month, relationship, person, and
  result IDs in a Flask session. When a follow-up provides only a new month or
  relationship, V3 can reuse the omitted value from the active context.
- Both versions use the same intent/entity parser, Pandas query service,
  copied frontend design, and workbook data. V3 adds `dialogue.py`, session
  handling, clarification, and conversation reset.

## Dialogue state and context carry-over

`dialogue.py` contains:

- `enrich_with_context(parsed, state)`: on a recognizable follow-up, fills a
  missing month or relationship from the previous query. A value provided in
  the current question always wins.
- `update_state(parsed, state, last_result_ids=None)`: remembers the latest
  month, relationship, person ID/name, intent, and result IDs.
- `resolve_clarification(...)`: uses the existing NLU parser against only the
  people who were offered as choices. It never picks a person outside that
  candidate set.

Example:

```text
User: Any nephew birthdays in September?
User: What about October?
```

V3 reuses `Nephew`, updates the month to October, and lists the matching
workbook records. The Dialogue State panel displays the remembered values.
State is scoped to the browser's Flask session; it is not shared between
different users' sessions.

## Ambiguity and clarification

For a singular request such as `When is my nephew's birthday?`, the service
checks the workbook relationship and candidate IDs. If several nephews match,
V3 asks which one the user means and records those IDs as a pending
clarification. The user's reply is parsed against that candidate subset. If
the name does not identify exactly one candidate, V3 explains that and asks
again instead of guessing. A successful response uses the selected Person_ID
to retrieve the factual birthday from the workbook.

## Resetting a conversation

Click **Reset Conversation** to send `POST /reset`. The endpoint clears the
Flask session, including pending clarification and saved context, then the
browser clears its visible conversation. A reset can also be requested by
typing `Reset the conversation.` in the chat.

## Project architecture

```text
User Browser → Flask session → NLU parser → Dialogue context
             → Query service → Pandas → people.xlsx → Response
```

## Files and folders

```text
V3_Dialogue_State/
├── app.py
├── data_service.py
├── nlu.py
├── service.py
├── dialogue.py
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
    ├── test_nlu_service.py
    └── test_dialogue.py
```

- `app.py` loads the workbook once, serves the page and API, stores state in
  Flask's signed session cookie, and handles `/reset`.
- `nlu.py` is the V2 rule-based intent/entity parser.
- `dialogue.py` enriches follow-ups, stores context, and resolves
  clarification candidates.
- `service.py` queries and formats results from the Pandas DataFrame.
- `data_service.py` validates and loads the copied V2 workbook.
- `templates/` and `static/` contain the V2 design with V3 debug and reset
  controls.
- `tests/` includes the V2 parser/service tests and V3 dialogue/API tests.

## Install and run in VS Code (Python 3.10)

Open the `V3_Dialogue_State` folder in VS Code and select Python 3.10. In the
integrated PowerShell terminal:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, run with the Python 3.10 launcher:

```powershell
py -3.10 -m pip install -r requirements.txt
py -3.10 app.py
```

For local development, Flask uses a fallback secret key. Before exposing the
app beyond the local machine, set a private `FLASK_SECRET_KEY` environment
variable. Do not commit the production key.

Open <http://127.0.0.1:5000>. If another version is already using port 5000,
stop that server before starting V3.

## Run the tests

From the V3 folder:

```powershell
py -3.10 -m pytest -q
```

The tests cover V2 behavior, month/relationship carry-over, replacing a
remembered value with a new one, name matching, ambiguity and clarification,
resetting the session, and requests to the home, health, chat, and reset
routes. Context tests use small DataFrames where possible; clarification tests
use the existing fictional workbook and derive the expected birthday from it.

## Try these conversations

### Carry the relationship to a new month

```text
User: Any nephew birthdays in September?
User: What about October?
```

V3 retains the `Nephew` relationship, changes the month to October, and
returns the matching workbook records.

### Clarify a relationship with multiple people

```text
User: When is my nephew's birthday?
User: Nikhil
```

V3 first asks which nephew is intended. It then resolves `Nikhil` against
those candidates and returns a birthday only if the match is unique. If it is
not unique, V3 asks for a full or otherwise unambiguous name.

### Carry the month to a new relationship

```text
User: Birthdays in September.
User: What about nieces?
```

V3 retains September and changes the relationship to niece.

### Reset context

```text
User: Reset the conversation.
User: What about October?
```

The second request must not reuse context from before the reset. Because it
does not identify a birthday request on its own, V3 responds that it cannot
understand it rather than silently carrying forward the old relationship.

## Limitations

V3 carries context only for supported follow-ups that contain a recognizable
month or relationship. It is not a general language model. Session context is
temporary and is cleared by Reset Conversation or when the browser session
ends. V3 does not implement V4/V5 features.
