# CIUX Birthday Assistant — Version 5

**Voice Conversational Interface**  
**GM University · UE24CS3540 — Conversational Interfaces and UX · 2026–27**

V5 adds browser speech recognition and speech synthesis to the V4 interface.
Typed and recognized questions use the same `/api/chat` endpoint, NLU,
dialogue state, workbook grounding, and response logic. The backend and data
layer are unchanged. Answers remain visible as text, whether or not speech
output is enabled.

## V4 reflection

Before continuing, write one limitation you personally observed in V4:

> My observation: ______________________________________________

For example, V4 requires typing, so it is less convenient when a user needs
hands-free interaction. Replace this example with your own observation.

## Voice controls

- **Speak** starts microphone recognition using `SpeechRecognition` or
  `webkitSpeechRecognition`, with the `en-IN` language setting. Recognized
  text is sent through the same chat flow as typed text.
- The listening status is shown on screen. Recognition errors, unsupported
  browsers, and denied microphone access leave typing available.
- **Read responses aloud** uses `SpeechSynthesisUtterance`. It is off by
  default; every assistant response is still displayed as text.
- The NLU debug panel continues to show how the transcript or typed question
  was interpreted. Check the visible user message first to distinguish an
  ASR transcription error from an NLU error.

Speech recognition support and behavior depend on the browser and its speech
service. Microphone access generally requires HTTPS or localhost. Review your
browser's microphone and speech-service privacy settings.

## Run locally on Windows

Open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your Groq API key to `.env` only if you want LLM-assisted parsing. V4's
rule-based fallback works without a key. Never commit `.env` or share API keys.

Run V5 on port 5005 (so it can run alongside V1–V4):

```powershell
python -c "from app import app; app.run(host='127.0.0.1', port=5005, debug=False)"
```

Open <http://127.0.0.1:5005>.

The V5 page identifies itself as V5. The inherited `/api/health` response still
reports V4 because `app.py` is intentionally unchanged.

## Checkpoint tests

For each spoken question, compare the visible transcript with what you said
before judging the NLU result. Record the two error types separately.

| Spoken test | ASR transcript / mistake | NLU result / mistake |
|---|---|---|
| Any birthdays tomorrow? | | |
| A person name from the workbook | | |
| A place name, such as Bengaluru | | |
| A date or month, such as October | | |
| A relationship, such as nephew | | |
| Follow-up by voice: What about October? | | |

Also turn **Read responses aloud** off and confirm that the text conversation
still works normally.

## Learning reminder

- V4 uses an LLM to interpret language, then validates and queries structured
  data.
- The spreadsheet remains the source of birthday and location facts; the LLM
  does not invent DOB values.
- V5 changes the interaction channel, not the source of truth.

## Reflection

- Was an incorrect result caused by ASR, NLU, dialogue context, or data logic?
- How should the interface indicate that it is listening?
- Should every response be spoken aloud? Why or why not?
