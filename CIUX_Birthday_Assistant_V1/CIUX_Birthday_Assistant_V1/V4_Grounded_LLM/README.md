# CIUX Birthday Assistant — Version 4

**LLM-Assisted NLU with Grounded Structured Queries**  
**GM University · UE24CS3540 — Conversational Interfaces and UX · 2026–27**

V4 is a separate copy of V3. It uses the Groq Chat Completions API to interpret
natural-language questions as structured intent and entity JSON. The language
model is only an NLU parser: it never supplies birthday, location, or other
factual answers. All such facts are looked up from the copied
`data/people.xlsx` workbook with Pandas.

## V3 versus V4

- **V3** uses deterministic phrase/rule parsing for each message.
- **V4** tries the configured LLM to understand paraphrases, validates its
  structured output, and grounds names, relationships, and places against the
  workbook.
- If no API key is configured or a request/response is invalid, V4 uses the
  V3 rule parser. The debug panel reports which parser was used.
- V4 keeps V3's Flask session dialogue state, context carry-over, clarification,
  person resolution, reset button, and workbook-backed query service.

## What the LLM does

`llm_nlu.py` sends the message to Groq's Chat Completions API using the model in
`GROQ_MODEL` (default: `llama-3.3-70b-versatile`) and JSON output formatting. It asks for
only these intents:

- `birthday_search`
- `count_birthdays`
- `upcoming_birthdays`
- `person_place`
- `unknown`

The allowed extracted fields are `person_name`, `relationship`, `month`,
`relative_date`, `relative_month`, and `place`. The model is instructed not to
answer the question or invent facts. Invalid JSON, unsupported fields, invalid
intent values, malformed entities, connection failures, and timeouts cause
rule-based fallback.

## Grounding and validation

Before a query is executed, V4:

1. Validates the intent and entity structure.
2. Checks months and relative date values.
3. Accepts relationship/category and place values only when they exist in the
   workbook (including the workbook's `Relationship_Group` categories).
4. Matches a mentioned name or nickname to workbook rows and obtains its
   `Person_ID` from the workbook.
5. Ignores any `Person_ID` supplied by an LLM. A unique grounded match is
   required before using a person's record.
6. Asks for clarification when the person or a singular relationship query is
   ambiguous; it never chooses a candidate arbitrarily.
7. Does not execute a name-specific search if the name was not found.

Birthday and place facts in responses come from `people.xlsx`. No birthday or
location is accepted from model output.

## Dialogue state

V4 retains V3's session-based month and relationship context. For example:

```text
User: Any nephew birthdays in September?
User: What about October?
```

V4 applies the new October entity and carries forward Nephew. If a relationship
query has multiple matches, V4 asks which person is intended, then resolves
the reply only against those workbook candidates. **Reset Conversation** calls
`POST /reset` and clears the session. The `/api/chat`, `/chat`, `/reset`, `/`,
and `/api/health` routes are available.

## Install in VS Code (Python 3.10)

Open the `V4_Grounded_LLM` folder in VS Code. In the integrated PowerShell
terminal:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your API key and, optionally, model name:

```dotenv
GROQ_API_KEY=your-key-here
GROQ_MODEL=llama-3.3-70b-versatile
FLASK_SECRET=replace-with-a-private-random-secret
```

Never paste an API key into source code, browser JavaScript, or a chat message.
The `.env` file is ignored by Git; `.env.example` contains placeholders only.
Keep the Flask secret private as well. If no Groq key is set, the app still
runs with the rule-based fallback.

Start the app:

```powershell
python app.py
```

Open <http://127.0.0.1:5000>. If another version is using port 5000, stop that
server before starting V4.

To configure the API key only for the current PowerShell session instead of
using `.env`:

```powershell
$env:GROQ_API_KEY = "your-key-here"
$env:GROQ_MODEL = "llama-3.3-70b-versatile"
$env:FLASK_SECRET = "replace-with-a-private-random-secret"
python app.py
```

Do not include real credentials in screenshots, logs, or committed files.

## Test

Run all tests from the V4 folder:

```powershell
py -3.10 -m pytest -q
```

The tests mock all LLM responses. They do not need an API key, contact Groq,
or consume API credits. They cover JSON parsing and rejection, intent/entity
validation, person grounding and ambiguity, API failure fallback, missing-key
fallback, the V3 dialogue context/reset flows, and inherited V3 tests.

## Checkpoint questions

Try these questions in the browser:

1. `Do I need to wish any nephew during September?`
2. `Are there people from my sibling family celebrating next month?`
3. `I was wondering whether Rahul has a birthday coming soon.`
4. `Any nephew birthdays in September?` followed by `What about October?`
5. `When is my nephew's birthday?` and then select a name from the prompt.
6. Try an unknown question and a name not present in the workbook.

The debug panel shows detected intent, entities, NLU method (LLM NLU or
Rule-based fallback), grounding status, and saved dialogue state. Answers are
displayed as plain text.

## Security and limitations

- Do not commit `.env` or expose API keys in the browser.
- The default Flask secret is for local development only. Set a private
  `FLASK_SECRET` before deployment.
- LLM responses are untrusted input and are validated before use.
- If a key is absent or the LLM service fails, only the deterministic fallback
  is available; paraphrase understanding may be more limited.
- The project uses no embeddings, vector database, RAG, voice, or V5 features.
