# Cynbit Inquiry → Discovery Brief Assistant (work in progress)

Prototype for the Cynbit AI/ML Engineer Intern assessment: turns a free-text client inquiry into
structured requirements, missing-information flags, discovery questions and a draft blueprint,
with mandatory human review.

> Status: Stage 2 complete (Groq client, prompt, pipeline). UI, guardrails, review flow and
> evaluation come next. Full README is written in the final stage.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env   -> then put your Groq key in .env
pytest -v                   # no API key needed: tests use fakes
python -m scripts.smoke_test   # ONE real Groq call (needs LLM_API_KEY)
```
