# Technical Approach: Inquiry-to-Discovery Brief

## 1. Goal and boundaries

The proof of concept accepts one client inquiry and returns a validated **internal draft** containing
candidate requirements, evidence, constraints, missing information, discovery questions, potential
contradictions, assumptions to confirm, and a provisional technical blueprint.

It is a discovery aid, not a client-facing proposal or source of truth. It does not choose a final
architecture, invent costs or delivery dates, contact a lead, or approve its own output. A human must
compare candidate facts and quotes with the original inquiry before sharing the draft.

## 2. Architecture

```text
Streamlit text input
        |
        v
Local input validation and length limits
        |
        v
Versioned prompt + small public Cynbit service catalog
        |
        v
Groq chat completion (strict JSON Schema first)
        |                         |
        | strict output error     | accepted response
        v                         v
One best-effort JSON retry --> Parse/normalize known safe shapes
                                  |
                                  v
                         Local Pydantic validation
                                  |
                    +-------------+-------------+
                    | invalid                   | valid
                    v                           v
             bounded repair loop       draft_unreviewed report
                                                |
                                                v
                                 Human review in Streamlit
```

Core logic lives in `app/`; `streamlit_app.py` is a thin interface. The protocol in
`app/llm_client.py` keeps provider-specific requests separate from the analysis pipeline and allows
the unit tests to use a fake client.

## 3. Model choice

The existing project config selects Groq and `openai/gpt-oss-20b`; the prompt requests low reasoning
effort, a JSON Schema response, temperature `0.1`, and a configured output limit. This retains the
project's existing work and avoids adding a model framework. The selected model is a configuration
choice for this prototype, not a claim that it is the best or cheapest model for Cynbit.

The model is appropriate for a PoC because its response is structured and locally validated. A
production choice would require a representative, approved evaluation set comparing output quality,
latency, availability, data terms, and cost across candidate models. No such benchmark has been run.

## 4. Data flow

1. The user enters an inquiry in Streamlit. The UI warns that the text is sent to Groq and should not
   contain sensitive data without authorization.
2. `clean_inquiry` strips control characters, normalizes whitespace, and enforces the configured
   minimum and maximum character limits **before** an API call.
3. The prompt adds the public Cynbit catalog from `data/cynbit_catalog.json`. The catalog has 15
   short entries and official public page links. It is intentionally embedded directly; no vector
   store or retrieval service is justified for this small static corpus.
4. The inquiry is marked as untrusted data in a delimited block. Tag-closing strings are neutralized;
   the model has no tools and cannot trigger external actions.
5. Groq returns JSON. The app applies only narrow, visible normalizations:
   - Promote a nested `blueprint` only when the root has no blueprint.
   - For stated requirements with evidence that is a verbatim inquiry substring, replace the text
     with that evidence.
   - Build the executive summary locally from the validated business-problem quote rather than
     trusting a free-form model summary.
   - Reframe unqualified entries in the assumptions list as confirmation questions and record the
     adjustment for the reviewer.
6. Pydantic validates structure, allowed enums, required fields, exact source-quote presence,
   question-to-gap links, distinct quoted conflict statements, known public catalog offerings, and
   provisional/potential labels.
   The pipeline removes a stated requirement that repeats a stated timeline/user-scale/budget
   constraint and records that correction in `normalization_notes`; the schema rejects it if it
   reaches validation unchanged.
7. Invalid content receives a repair prompt with validation errors. The application allows at most
   three total attempts, two by default. After that it raises an error and does not return the
   malformed draft.
8. The validated report is held in Streamlit session state for display/download. No SQLite or other
   application persistence is used; application logs do not include inquiry text.

## 5. Prompt and output contract

`app/prompts.py` keeps prompt text versioned (`v9`). It directs the model to:

- distinguish stated requirements from `Potential:` inferences;
- copy stated evidence and objectives as short exact inquiry quotes;
- mark inferred business domains and missing-information rationales as `Potential:`;
- leave unstated constraints empty and identify missing scope details;
- link every discovery question to an exact missing-information topic;
- return only possible contradictions as two distinct quoted statements and label the explanation
  `Potential:`;
- phrase assumptions as questions to confirm;
- prefix architecture, technology suggestions, and phase descriptions as `Provisional:`;
- avoid claims about manual/slow/error-prone existing workflows unless stated by the client;
- ignore instructions embedded in inquiry data and return the expected JSON object.

Pydantic models in `app/schemas.py` use `extra="forbid"` so unexpected keys do not silently pass.
The model cannot set approval status; `AnalysisReport` defaults to `draft_unreviewed`.

### Evidence is not semantic verification

Local validation checks whether exact quote text appears in the inquiry and whether a stated
requirement's text equals that quote. This blocks paraphrase-based additions and unsupported quotes,
and a cross-field check catches some common constraint/requirement category errors. A matching quote
can still be negative, hypothetical, or unrelated to the model's interpretation.
Contradiction and missing-information judgments are also model proposals, not deterministic facts.
The UI labels them for review and the report does **not** claim semantic entailment is verified.

The recommended next step for higher assurance is a reviewer rubric and benchmark, not an untested
claim that a second model call can prove correctness. Human approval remains mandatory.

## 6. Strict structured-output compatibility

The client uses `to_strict_json_schema` to convert the Pydantic schema to the provider's strict
subset: every object is closed, all properties are required, and optional values remain nullable.
Pydantic validation runs afterward because provider strict mode does not enforce all local limits or
business rules.

`LLM_STRICT_SCHEMA=true` sends a strict request. If Groq returns a recognized response-format/schema
rejection or `json_validate_failed`, the client retries that request **once** with `strict=false`.
The fallback is limited to those recognized 400 errors; unrelated 400s fail as request errors.
After a fallback, that client instance uses best-effort mode for later calls. The pipeline still
validates locally in either mode.

The local tests verify the transformed schema, strict request construction, a targeted fallback, and
that unrelated/provider best-effort errors do not trigger a fallback. These tests do not establish
current provider compatibility. The smoke-test section of the README calls for a live API check;
the strict-mode limitation must be reported separately from successful best-effort output. A
provider-side `json_validate_failed` response does not, by itself, prove whether the cause was model
generation or schema compatibility.

## 7. Evaluation plan

### Checks implemented in the PoC

- Unit tests use fake clients; they require no key and make no network calls.
- Regression tests cover malformed JSON, unsupported quotes, invalid output shape, wrong nesting,
  bounded retries, and provider error handling.
- Schema tests cover constraints and the `draft_unreviewed` status.
- A smoke-test script performs one real Groq call with a synthetic inquiry when explicitly run.

### Proposed human-reviewed evaluation

Before any pilot, obtain approval for a small, representative, anonymized inquiry set. Two reviewers
should label:

1. whether each stated requirement and constraint is both accurately quoted and semantically
   supported (including negation);
2. whether each inference is reasonable and clearly labeled;
3. whether missing-information topics are actually missing;
4. whether questions map to their gaps and are useful;
5. whether each potential contradiction is real;
6. whether provisional architecture and risks are sensible without asserting unknown facts.

Report precision, coverage, error categories, inter-reviewer disagreement, malformed-response rate,
repair/fallback rate, latency, and reviewer effort. Establish a baseline before claiming business
value. The desired threshold for presenting a candidate as a fact is zero unsupported items in the
reviewed sample; if this is not met, narrow the output rather than relaxing the check.

## 8. Security and privacy

- Keep Groq credentials in `.env`, ignored by Git; never hardcode or log secrets.
- Minimize inquiry data and do not enter sensitive/confidential information without authorization.
- The application has no database, analytics tracker, or inquiry-text logging.
- Validate all model output locally; no tools, shell access, email, CRM writes, or client replies.
- Prompt delimiters are not a complete prompt-injection defense. Keep the model's authority
  restricted to a draft, and test hostile input.
- Verify provider retention, training, regional processing, and contractual terms before handling
  real client data. This PoC does not establish those terms.
- Treat the UI and downloaded JSON as internal draft material until a human checks it.
- Use NIST AI RMF's Govern/Map/Measure/Manage concepts and OWASP GenAI application guidance as
  references for risk assessment; they are guidance, not a certification.

## 9. Execution plan

1. Confirm domain/source ownership and obtain permission for any real inquiry samples.
2. Agree on a reviewer rubric, data retention rules, and a small set of representative test cases.
3. Run offline tests and one controlled API smoke test; document strict fallback behavior and errors.
4. Have reviewers compare draft output to original text, correct errors, and record usefulness/effort.
5. Revise prompts and validations based on labeled failures; repeat evaluation before considering a
   CRM integration or production use.
6. Only after quality, privacy, and operational review, decide whether to deploy and how to retain or
   delete data. No production deployment is part of this assessment.

The steps describe an order of work, not delivery dates or effort estimates.

## 10. Limitations

- One configured provider/model; no cross-model benchmark or SLA evaluation.
- Semantic correctness, sentiment, contradiction detection, and the usefulness of questions require
  human assessment.
- The static public catalog may become stale and does not represent internal expertise or service
  availability.
- No authentication, multi-user access control, durable audit trail, approval database, CRM
  integration, or production hosting.
- No measured time savings, lead-conversion improvement, accuracy percentage, or ROI.
- Provider data handling and local deployment security require separate review.
