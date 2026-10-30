# Cynbit Inquiry-to-Discovery Brief

A small Python demo that turns a client inquiry into a structured discovery draft. It highlights
candidate requirements and their evidence, missing information, questions, possible contradictions,
and a preliminary technical blueprint.

The output is an **unreviewed draft**, not a proposal or a client commitment. A person must check it
against the original inquiry before using or sharing it.

## What is in this project?

- `streamlit_app.py` — the web interface.
- `app/` — input checks, prompts, Groq client, and Pydantic output models.
- `data/cynbit_catalog.json` — the public service and product names used in the prompt.
- `tests/` — tests that run without an API key.
- `docs/AI_OPPORTUNITY_REPORT.md` — comparison of AI opportunities for the assessment.
- `docs/TECHNICAL_APPROACH.md` — how the proof of concept works and its limitations.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A Groq API key to generate drafts in the app

## Set up on Windows

Open PowerShell in the project folder. Install `uv` first if it is not already installed, then run:

```powershell
uv sync
Copy-Item .env.example .env
```

Open `.env` and set `LLM_API_KEY` to your own Groq API key. Keep the key private: `.env` is ignored
by Git. The tests do not need a key.

## Environment variables

The example settings are in `.env.example`. Only `LLM_API_KEY` is needed to call Groq; the other
settings are optional.

| Variable | Purpose | Default |
| --- | --- | --- |
| `LLM_API_KEY` | Groq API key | Not set |
| `LLM_MODEL` | Groq model name | `openai/gpt-oss-20b` |
| `LLM_STRICT_SCHEMA` | Request strict structured output before the supported fallback | `true` |
| `LLM_REASONING_EFFORT` | Reasoning effort for supported GPT-OSS models | `low` |
| `LLM_MAX_OUTPUT_TOKENS` | Maximum output tokens | `4000` |
| `LLM_TIMEOUT_SECONDS` | Request timeout | `60` |
| `LLM_MAX_RETRIES` | Groq SDK retries for transient errors | `2` |
| `LOG_LEVEL` | Application log level | `INFO` |

## Run the app

```powershell
uv run streamlit run streamlit_app.py
```

Open the local address printed in the terminal. The pre-filled inquiry is synthetic. Text submitted
to the app is sent to Groq; do not enter sensitive or confidential information unless you have
permission to share it. The app does not save inquiries to a database.

## Run the tests

```powershell
uv run pytest -v
```

These tests use a fake language-model client, so they do not make network calls and do not require
an API key.

To make a separate live check of your API key and model, you can optionally run:

```powershell
uv run python -m scripts.smoke_test
```

This sends the synthetic sample inquiry to Groq and may use API quota. A passing test suite does
not mean the live API is available.

## Important limitations

- A matching quote shows that text occurs in the inquiry; it does not prove that the quote supports
  the model's interpretation.
- Inferences, risks, and recommendations are draft suggestions, not confirmed client facts.
- Groq's strict structured-output support is not guaranteed. The app has a targeted best-effort
  fallback and still validates results locally.
- No output is automatically approved or sent to a client.

## Assessment checklist

- [ ] Run the tests and inspect the app locally.
- [ ] Review the [AI opportunity report](docs/AI_OPPORTUNITY_REPORT.md) and
  [technical approach](docs/TECHNICAL_APPROACH.md).
- [ ] Add the repository URL and setup notes to the candidate portal.
- [ ] Review the repository for private information before making it public.

Nothing has been pushed or deployed.
