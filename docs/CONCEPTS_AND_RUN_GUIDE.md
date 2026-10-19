# Concepts and Run Guide

Everything you need to run this project and explain it. Read Part 1 first, then Part 2 to run it, then Part 3 to prepare for questions.

---

# PART 1: Concepts (in simple language)

## 1. The big picture

A chronic-care program (diabetes, blood pressure, heart) has members who record readings and follow a care plan. Care coordinators cannot reply to everyone, so we build a team of small AI helpers ("agents"). Each helper does one narrow job. The helpers never diagnose, never change medicines and never judge a reading. When a rule says a human must look, they hand over to staff.

Every request produces two separate things:
1. **Member response**: plain language, with source IDs and a disclaimer.
2. **Coordinator packet**: for staff only. Readings, due tasks, sources, escalation reason, missing information.
Plus an **audit record** (what happened, with masked IDs).

## 2. Key terms

| Term | Meaning | Where in this project |
|---|---|---|
| **LLM / model** | The AI that writes text | The chat model you deploy in Foundry |
| **Agent** | An LLM with instructions (a role) and optionally tools | `src/agents/*.py` |
| **Multi-agent system** | Several agents with different jobs working together | 6 agents + orchestrator |
| **Orchestrator** | The coordinator that decides the order of steps | `src/orchestrator.py` |
| **Tool / function calling** | A Python function the agent is allowed to call to get real data | `src/tools/*.py` |
| **Least privilege** | Each agent gets only the tools it needs | Reading agent can only read readings, etc. |
| **RAG** (retrieval augmented generation) | The AI first searches your approved documents, then answers from what it found | Education RAG Agent |
| **Grounding** | Answer is based on retrieved sources, not on the model's memory | Citations like EDU-401 (v4) |
| **Embedding** | A list of numbers that captures the meaning of a text | `scripts/setup_search_index.py` |
| **Vector search** | Finds documents with similar meaning using embeddings | AI Search index field `content_vector` |
| **Hybrid + semantic search** | Keyword search + vector search + a re-ranker combined | `VECTOR_SEMANTIC_HYBRID` in `education_agent.py` |
| **Azure AI Search** | The service that stores and searches the indexed articles | 3 indexes |
| **Microsoft Foundry** | Azure's platform: deploy models, create agents, connect search | Your project endpoint |
| **Agent Framework** | Python library to build agents, tools and middleware | `agent_framework` package |
| **Structured output** | Forcing the model to return JSON that matches a schema | `src/models.py` (pydantic) |
| **Middleware** | Code that runs before/after every agent call (logging, safety, retry) | `src/middleware/` |
| **Guardrail** | A rule that blocks unsafe input or output | input guard, output guard |
| **Human in the loop** | A person must decide in some cases | Escalation rules ER-501 to ER-504 |
| **Audit trail** | A record of what the system did | `logs/audit.jsonl` |
| **PII masking** | Hiding identifiers in logs | `M-101` becomes `M-1**` |
| **Synthetic data** | Fake data made for demos; never real patients | `data/` |

## 3. The two ways of building agents

1. **Agent Framework** (`Agent(client, name, instructions, tools, middleware)`). The agent object lives in your Python code and calls the model. Used for Router, Reading Summary, Care Plan, Engagement and Escalation agents.
2. **Foundry project agents** (`AIProjectClient.agents.create_version(...)` with `PromptAgentDefinition`). The agent is registered inside Foundry and has a built-in Azure AI Search tool. Used for the Education RAG agent, because the design calls for configured agents and a knowledge source in Foundry.

Both use your deployed model. Their settings are in `.env` (two groups of variable names, exactly as in the reference demos).

## 4. The most important design idea

> **Code decides facts. Agents only word them.**

- Code computes: consent check, rule matches (ER-501 to ER-504), reading statistics, missing dates, due/overdue lists, which articles are allowed.
- The agent writes friendly wording from those facts.
- Before wording is shown, it is checked: no numbers that are not in the facts, no diagnosis or judging language, no medication advice, no "I am a doctor". If the check fails, a safe template is used instead.

Why: a safety rule must give the same answer every time. A model can vary or make mistakes. This is the answer to "why is your orchestrator not an LLM?"

## 5. The workflow (what happens for one request)

1. **Verify member and consent.** Not found: stop. Consent not Active: **ER-501**, stop, read no data.
2. **Input guard.** Prompt-injection phrases are blocked. A request to change medication is **ER-503**: decline, send to clinician.
3. **Classify the request.** Router agent returns one word (EDUCATION, READINGS, PLAN, MEDICATION, STAFF). If it fails, a keyword classifier is used. Requests asking "is my reading dangerous?" go to STAFF.
4. **Read the data window** (default last 7 days ending at the reference date 2026-10-07) and apply rules:
   - **ER-502**: a reading matches the configured test value: urgent staff-review record, no interpretation.
   - **ER-504**: two active readings contradict: mark uncertainty, request human review.
5. **Call the specialist agent(s)**:
   - Reading Summary Agent: count, range, trend description, **missing dates**, non-diagnostic label.
   - Care Plan Agent: due/overdue (status Due, Overdue) and upcoming (Open, Scheduled) tasks as recorded.
   - Engagement Agent: neutral reminder in the member's channel and language plus one check-in question.
   - Education RAG Agent: answer only from approved articles; cites ID and version. No article, or article not for the member's program, or version mismatch: knowledge gap or ER-504.
   - Escalation Agent: writes the staff note for rules already matched by code.
6. **Build outputs**: member response, coordinator packet, audit record. Staff-queue entry if escalated.
7. **Store minimum**: message text is not stored; nothing is remembered between requests.

## 6. The six agents

| Agent | Job | Tools it may use | Cannot do |
|---|---|---|---|
| Care Orchestrator | Runs the workflow | Member/consent tool, rules code | (It is code, not an LLM) |
| Reading Summary | Describe readings, list missing dates | `get_reading_facts` (active readings only) | See care plan or articles |
| Care Plan | Report tasks as recorded | `get_care_plan_tasks`, `get_care_plan_guidance` | See readings |
| Education RAG | Answer general questions from approved articles | Azure AI Search (education + FAQ indexes) | See readings or plans |
| Engagement | Draft reminder + check-in question | none (gets due tasks, channel, language) | See any data |
| Escalation | Word the staff note | `get_escalation_rules`, `check_rules_for_member` | Add or remove rule matches |
| (Router) | Classify request | none | See any data |

## 7. The four escalation rules

| Rule | Trigger | Action | How it is detected |
|---|---|---|---|
| ER-501 | Consent not Active | Stop, direct to staff | `consent_status != "Active"` |
| ER-502 | Reading matches configured test value | Urgent staff review, do not interpret | Values in `data/high_risk_values.csv` (placeholders: BP 160/100, glucose 300) |
| ER-503 | User asks to change medication | Decline, direct to clinician | Action word AND medication word in the message (words are in the rules file) |
| ER-504 | Source or reading is contradictory | Mark uncertainty, human review | Same type + same timestamp + different value; or article version conflict |

The ER-502 values are **placeholders so the rule can be demonstrated, not clinical thresholds**. Say this clearly in your report.

## 8. RAG in this project

- Articles live in `knowledge/` in three folders: `education/`, `faq/`, `careplan_guidance/`.
- `setup_search_index.py` creates **three separate indexes** (requirement) and uploads each article with its embedding.
- The Education agent searches the education and FAQ indexes (top 3, hybrid + semantic). It is told never to answer from its own knowledge and to answer exactly `NO_APPROVED_ARTICLE` when nothing fits.
- After the agent answers, code checks every cited ID against `data/articles_catalog.csv`: the article must exist, must be for "All programs" or the member's program, and the version must match. This is how "restrict answers to approved content versions" is enforced.
- Knowledge gap (T6): member is told no approved article was found, staff follow-up is created.

## 9. Safety, privacy and audit

- Disclaimer shown at client start and in every member response.
- Never diagnose, predict, judge, change medicines, or claim to be a clinician (output guard).
- Prompt-injection phrases blocked (input guard) at orchestrator level and as agent middleware.
- Corrected readings: the old value is marked `superseded`, never shown in active summaries; staff only see "R-206 replaced by R-207".
- Audit record has: consent check, agents called, rule IDs, source versions, disposition. It has **no message text and no reading values**, and member IDs are masked.
- All log output is passed through a masking filter.
- Tool failure: a clear message ("could not retrieve...") and nothing invented. Retry middleware tries again first.

## 10. Middleware (reference patterns)

| Middleware | Pattern | Purpose |
|---|---|---|
| `logging_middleware` | `middleware_demo.py` | Log agent name and time, never content |
| `input_guard_middleware` | `middleware_demo.py` (content safety) | Block injection phrases |
| `RetryMiddleware` | `error_handling_retries.py` | Retry a failed agent call |
| `SafeToolMiddleware` | `error_handling_retries.py` | Retry a failed tool, then return a safe message |

---

# PART 2: How to run

## A. Quick check without Azure (5 minutes)

Windows (VS Code terminal):

```powershell
cd chronic-care-agents
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python client/app.py --offline
python tests/run_tests.py --offline
```

Mac/Linux: same, but activate with `source .venv/bin/activate`.

In the client, try:
- `What are home readings and why should I record them?`
- `/member M-102` then `Summarize my blood pressure readings for the past 7 days.`
- `/member M-103` then `Show me my glucose readings.`
- `/member M-101` then `Can I increase my insulin dose?`

Commands: `/member M-101`, `/view member|staff|both`, `/help`, `/quit`.

Offline mode uses the same workflow and safety rules, but the wording is templates and retrieval is a simple keyword search.

## B. Run it online with Foundry (all six agents, Blob Storage, two retrieval modes)

**Step 1: Azure resources (in the Azure / Foundry portals)**
1. Create (or open) a Foundry project. Copy the **project endpoint**.
2. Deploy a **chat model**. Note the **deployment name**.
3. Deploy an **embedding model** (for example text-embedding-3-small). Note its name.
4. Create an **Azure AI Search** service and **connect it to the project** (Connected resources). Note the connection name and the search endpoint (`https://<name>.search.windows.net`).
5. Create a **Storage account** (Blob). Copy its **connection string** (Access keys), or its account URL if you use `az login`.
6. *Only for knowledge-base mode (Step 8):* in the Foundry / AI Search portal create **knowledge sources** on the Blob container `chronic-care-data` and a **knowledge base** that uses them. Portal screens and preview features change often: check docs. Suggested layout: three knowledge sources pointing at the folders `knowledge/education`, `knowledge/faq`, `knowledge/careplan_guidance` (indexed separately). Put the **education and FAQ** sources into the knowledge base used by the Education agent; leave care-plan guidance out (least privilege).

**Step 2: `.env`**

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

| Variable | What to put |
|---|---|
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME` | Needed only for `AGENT_RUNTIME=framework` |
| `FOUNDRY_PROJECT_ENDPOINT`, `MODEL_DEPLOYMENT_NAME` | Project endpoint, chat deployment name (all six agents use this) |
| `TEXT_EMBEDDING_MODEL_NAME` | Embedding deployment (index mode) |
| `SEARCH_SERVICE_ENDPOINT`, `AI_SEARCH_CONNECTION_NAME` | Search endpoint and the project connection name |
| `SEARCH_API_KEY` | Optional. Empty = use `az login` |
| `AZURE_STORAGE_CONNECTION_STRING` (or `AZURE_STORAGE_ACCOUNT_URL`) | Blob Storage |
| `KNOWLEDGE_BASE_NAME`, `KNOWLEDGE_INDEXERS` | Only for knowledge-base mode |
| `OFFLINE` | `0` |

Never share or commit `.env`.

**Step 3: Sign in**: `az login`

**Step 4: Upload the data and documents to Blob Storage**

```bash
python scripts/sync_to_azure.py --push        # tables + approved documents
```

Or open the UI > Azure Sync > Upload to Blob. From now on every save in the Data Manager uploads automatically (`AUTO_UPLOAD=1`).

**Step 5: Make the search side current (index mode)**

```bash
python scripts/setup_search_index.py --dry-run     # local check
python scripts/sync_to_azure.py --index            # builds the 3 indexes from APPROVED documents
```

**Step 6: Create the six agents in Foundry**

```bash
python scripts/create_agents.py                    # registers missing / changed agents
python scripts/create_agents.py --list
python scripts/create_agents.py --test "What is a home reading?"
```

This also happens automatically when you start the UI, the client or the test runner (`AUTO_REGISTER_AGENTS=1`). Open the Foundry portal > Agents to see: `care-orchestrator-agent`, `reading-summary-agent`, `care-plan-agent`, `education-rag-agent`, `engagement-agent`, `escalation-agent`.

**Step 7: Use the app and generate the evidence**

```bash
streamlit run app/streamlit_app.py       # or: python client/app.py
python tests/run_tests.py                # ONLINE evidence: the reference run
```

The evidence file records the agent runtime and the retrieval mode it used.

**Step 8 (optional): switch the Education agent to the knowledge base**

Set `EDUCATION_RETRIEVAL=knowledge_base`, `KNOWLEDGE_BASE_NAME=<name>` (and optionally `KNOWLEDGE_INDEXERS=<indexer names>`) in `.env`, then `python scripts/create_agents.py --only education`.

### If something goes wrong: how to switch

| Problem | Switch (in `.env`, then restart) |
|---|---|
| Knowledge base mode gives no or wrong answers | `EDUCATION_RETRIEVAL=index`, then `python scripts/create_agents.py --only education` |
| Foundry agent calls fail or wording always looks like a template | `AGENT_RUNTIME=framework` (specialists run in Python with the old tools; only the Education agent stays in Foundry). Needs the `AZURE_OPENAI_*` values |
| Registration fails at start-up | `AUTO_REGISTER_AGENTS=0`, fix `.env`, then run `python scripts/create_agents.py` and read the error |
| Blob upload fails or is slow during a demo | `AUTO_UPLOAD=0` (saves stay local; upload later from Azure Sync) |
| Nothing from Azure works (network, quota, no time) | `OFFLINE=1` (or the sidebar toggle). Same rules, template wording |
| A Draft or Retired document still appears in answers | Upload again (it is removed from `knowledge/` in Blob), then refresh the search side. In knowledge-base mode the indexer needs deletion detection (check docs) |

Every switch is a setting. No code change is needed.

**Step 9: Diagram**: `docs/architecture_diagram.png` is included. Regenerate with `python docs/make_diagram.py`.

## C. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `Missing settings in .env: ...` | Fill the listed variables, or run with `--offline` |
| `FOUNDRY_PROJECT_ENDPOINT is not set` | Education agent needs the Foundry settings (online mode only) |
| Authentication or 401/403 errors | Run `az login`; make sure your account has access to the Foundry project and, if you use `az login` for Search, a data role on the search service (for example Search Index Data Contributor) |
| `No Foundry connection named ...` | `AI_SEARCH_CONNECTION_NAME` must equal the connection's name in the project |
| Education answers say "could not find an approved article" for everything | Indexes empty or wrong names: rerun `setup_search_index.py`; check `SEARCH_INDEX_*` match; the agent only attaches education + FAQ indexes |
| Embedding dimension error | Set `EMBEDDING_DIMENSIONS` (text-embedding-3-large is 3072) and recreate the index |
| Agent wording always looks like a template | The wording check rejected the model's text; see `audit_notes` in the staff view or `logs/audit.jsonl` (`*_wording_rejected`) and adjust the instructions in `src/prompts.py` |
| Router sends a request to the wrong place | Add a clearer example to `ROUTER_INSTRUCTIONS` or a keyword in `router_agent.py` |
| Tests differ between offline and online | Expected: online wording and retrieval differ. Use the online run as reference |

## D. Where to change things

| I want to... | Edit |
|---|---|
| Change agent behaviour or tone | `src/prompts.py` |
| Change ER-502 test values or ER-503 words | UI: Data Manager > Edit rules (files: `data/high_risk_values.csv`, `data/medication_words.csv`) |
| Add members, readings, tasks | UI: Data Manager > Add / convert data (files: `data/*.csv`) |
| Add or edit an article | UI: Data Manager > Add / convert data, or Knowledge Base > edit (files: `knowledge/<folder>/ID.md` + `data/articles_catalog.csv`) |
| Regenerate the synthetic data | `python scripts/generate_synthetic_data.py` (overwrites `data/*.csv`) |
| Change "today" | `REFERENCE_DATE` in `.env` |
| Add a test | `tests/test_cases.json` |
| Simulate a tool failure | set `SIMULATE_TOOL_FAILURE=readings` (used by T10) |

## E. Folder map

```
config.py                 settings from .env
data/                     synthetic dataset + rules + article catalog
knowledge/                approved articles (education, faq, careplan_guidance)
src/models.py             pydantic models (agent outputs, member response, packet, audit)
app/                      Streamlit hospital UI (streamlit_app.py, theme.py, views/)
src/ingest/               upload readers, column mapping, validation, document conversion
src/azure_integration/    Blob Storage, AI Search, connection checks
src/schemas.py            the canonical table schemas
src/knowledge.py          catalog helpers + offline keyword retrieval
src/tools/                member, reading, care plan, rules tools
src/agents/               router, reading, careplan, engagement, escalation, education, base factory
src/middleware/           input guard, output guard, audit + masking, retry/safe tools
src/prompts.py            all agent instructions
src/orchestrator.py       the workflow
client/app.py             interactive client
scripts/                  generate data, sync to Azure, create indexes, register Foundry agent
tests/                    test cases + runner
docs/                     diagram, limitations, demo script, evidence, this guide
```

---

# PART 3: Preparing for questions (interview / demo)

**Q: Why not let one big agent do everything?**
Separate agents have narrow instructions and narrow tools. That lowers the chance of unsafe behaviour (least privilege) and makes each part easy to test and explain.

**Q: Why is the orchestrator code and not an LLM?**
Consent and escalation rules must be exact and repeatable. Code gives the same answer every time and can be tested. Agents are used where language is needed.

**Q: How do you stop the model inventing numbers?**
Facts come from tools and code. The model's wording is rejected if it contains a number that is not in the facts (`numbers_are_grounded`) or if it breaks a forbidden-language rule (`check_text`). A template is used instead.

**Q: How is RAG grounded and how do you handle missing evidence?**
The agent must search first, cite article ID and version, and answer `NO_APPROVED_ARTICLE` if nothing fits. Code then checks the citations against the approved catalog and the member's program. No valid citation means a knowledge gap and staff follow-up.

**Q: What if the article version in the answer is different from the approved version?**
That is a contradictory source: ER-504, uncertainty is marked and a human reviews.

**Q: How do you handle a corrected reading?**
The old reading is marked `superseded` and excluded everywhere in active summaries. Staff only see that R-206 was replaced by R-207.

**Q: Where are the human checkpoints?**
Consent renewal (staff), ER-502 urgent review (staff), medication questions (clinician), contradictions (staff review), knowledge gaps (staff follow-up), clinical-advice questions (staff). See the orange band in the diagram.

**Q: How is privacy protected?**
Synthetic data only. Message text and reading values are not written to the audit log. Member IDs are masked in the audit log and in all log output. Only the staff queue holds the full (synthetic) ID. Nothing is remembered between requests.

**Q: What are the limitations?**
See `docs/known_limitations.md`: placeholder thresholds, keyword/pattern based checks, weak offline retrieval, unreviewed Hindi/Kannada wording, no real authentication.

**Q: What would you do next (stretch goals)?**
An evaluator that checks every health claim for a source ID, opt-out for reminders, a second program with its own knowledge and rules.

## One-minute explanation you can say aloud

"A member asks a question. Our orchestrator, written as code, first checks consent. Then it classifies the request and runs the configured escalation rules. Specialist agents then write the answer: one summarises readings without judging them, one lists care-plan tasks, one drafts reminders, and one answers education questions only from approved articles using RAG in Foundry. The system returns two outputs, a plain-language member response with sources and a coordinator packet for staff, and writes a masked audit record. If a rule matches, it never interprets: it hands over to a human."

---

# PART 4: Data, upload, Azure and the UI (data, upload, Azure and the UI)

## 1. CSV or JSON? Decision

**CSV for tables, Markdown for documents.**

| Why CSV for members, readings, tasks, rule values, catalog | Why not JSON |
|---|---|
| Every record has the same flat columns, which is exactly what a table is | JSON suits nested data; this data has no nesting |
| Opens in Excel, so clinicians and coordinators can check and edit it | Needs a developer or a JSON editor |
| Easy to validate column by column and to merge (append / update / replace) | Harder to merge safely |
| Small and diff-friendly in version history; uploads to Blob Storage as-is | Larger and noisier |

Articles, FAQs and guidance are text, so they stay **Markdown** files with a small front-matter block (ID, title, program, version). That is also what Azure AI Search indexes.

## 2. One format for everything (the "add anything from the UI" idea)

Yes, it is a good choice, **with governance**. Data Manager > Add / convert data accepts CSV, JSON, Excel (tables) and Word, PDF, text, Markdown (documents) and converts them into the two canonical formats:

1. The file is read and only **previewed**.
2. Columns are matched automatically (synonyms such as `Programme` to `program`) and you can correct them.
3. Values are cleaned (letter case, dates) and **every row is validated** against `src/schemas.py`. Bad rows are listed and skipped, never saved.
4. Warnings: possible personal data (email, phone, ID numbers), orphan member IDs, wording the safety guard rejects.
5. You choose append, update or replace. A **backup** is made automatically; History lets you **roll back**.
6. Documents start as **Draft**. Only **Approved** documents (with an approver name) are indexed and cited. Editing creates a new version and keeps the old one.

Rule **logic** stays in code (tested). The UI edits only rule **values and words** (ER-502 numbers, ER-503 word lists, rule wording). Letting a UI change safety logic would be unsafe.

## 3. Pipeline with Azure

```
Data Manager (CSV + Markdown)  ->  Azure Blob Storage  ->  Azure AI Search (3 indexes)  ->  Foundry Education agent
```

* Blob container `chronic-care-data` holds `data/*.csv` and `knowledge/**/*.md`.
* Sign-in: `AZURE_STORAGE_CONNECTION_STRING` (key string), or `AZURE_STORAGE_ACCOUNT_URL` plus `az login`.
* Only **Approved** documents are placed under `knowledge/` in Blob. Drafts and retired ones go to `knowledge-unapproved/` and are removed from `knowledge/` on the next upload.
* UI: **Azure Sync** page (test connections, the six agents, compare, upload, download, refresh the search side). Command line: `python scripts/sync_to_azure.py --push --index` (also `--status`, `--pull`, `--watch`).
* `AUTO_UPLOAD=1` (default) uploads after every save in the UI; `AUTO_SYNC=1` also refreshes the search side.
* The search side only ever sees Approved documents, and citations are checked against the catalog, so the agent cannot cite a Draft or Retired one.
* Not verified here: no Azure endpoints were available. The code was checked offline (imports, dry run, logic). Test it once with your `.env`.

## 4. Run the UI

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py          # works offline with no .env
```

Pages: Ward Overview, Care Assistant (Member View / Staff View / Audit), Staff Review Queue, Data Manager, Knowledge Base, Azure Sync, Tests & Evidence, About & Safety. The toggle in the sidebar switches Offline / Online.

## 5. The bigger synthetic data

`python scripts/generate_synthetic_data.py` (seeded, repeatable): 250 members, about 5,573 readings, 657 tasks, 110 articles, 106 escalation rows (4 rules + routing variants), 104 ER-502 test values, 184 ER-503 words. The original seed records are kept unchanged so tests T1 to T14 behave the same. The new members include expired, pending and revoked consent, readings that match ER-502, contradictory readings, corrected readings, missing days and overdue tasks.

## 6. More tests

`python tests/test_ingest.py` (21 checks on data integrity, rule editing, upload, rollback, document approval; runs on a temporary copy) `python tests/test_data_scale.py` (22 checks on the bigger tables and rule logic), and `python tests/run_tests.py --offline` (14 scenarios).
