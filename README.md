# Chronic Care Engagement and Follow-up: multi-agent prototype

**Built by Sujit** · [GitHub](https://github.com/sujit428755) · MIT License

**Start here: `docs/CONCEPTS_AND_RUN_GUIDE.md`** (all concepts, step-by-step run, troubleshooting, interview questions).

Synthetic data only. Not for clinical use. The system never diagnoses, never changes treatment and never judges a reading.

## What is in the box

| Folder | Purpose |
|---|---|
| `data/` | Synthetic CSV tables: members (250), readings (~5,570), care plan tasks (657), rules (106), rule values (104), medication words (184), article catalog (110) (+ `_versions/` backups) |
| `knowledge/` | Approved articles for RAG, in 3 separate groups: `education/`, `faq/`, `careplan_guidance/` |
| `src/tools/` | Plain Python tools, one set per agent (least privilege) |
| `src/agents/` | Router, Reading Summary, Care Plan, Engagement, Escalation (Agent Framework) and Education RAG (Foundry) |
| `src/middleware/` | Input guard, output guard, audit log with masked IDs, retry / safe-tool failure |
| `src/orchestrator.py` | Care Orchestrator: fixed workflow, safety rules in code |
| `client/app.py` | Command-line client with Member View and Staff View |
| `app/` | **Streamlit hospital-style UI** (`streamlit run app/streamlit_app.py`) |
| `src/ingest/` | Upload any CSV / JSON / Excel / Word / PDF / text and convert it to the canonical CSV or Markdown, with validation and rollback |
| `src/azure_integration/` | Blob Storage upload, AI Search indexing, connection tests |
| `scripts/` | `create_agents.py` (all six Foundry agents), `sync_to_azure.py`, `setup_search_index.py`, `generate_synthetic_data.py`, `create_education_agent.py` |
| `tests/` | 14 test scenarios (T1 to T6 core scenarios plus 8 extra) and the runner |
| `docs/` | Architecture diagram, known limitations, demo script, test evidence (generated) |

## Try it right now, without Azure

```bash
pip install -r requirements.txt
python client/app.py --offline
streamlit run app/streamlit_app.py      # the hospital UI
python tests/test_ingest.py
python tests/test_azure_mock.py          # fake Foundry + fake Blob, no account needed
python tests/run_tests.py --offline
```

Offline mode runs the same workflow and the same safety rules. Only the wording is template based.

## Run it for real (Foundry): see section B of `docs/CONCEPTS_AND_RUN_GUIDE.md`

Short version: Blob upload, six agents created in Foundry, Education retrieval by search index OR Foundry knowledge base (switch in `.env`, with a table of what to change when something goes wrong).

1. In Azure / Foundry: project, chat model, embedding model, AI Search connected to the project, a Storage account.
2. `cp .env.example .env` and fill it in. Never share `.env`. Then `az login`.
3. `python scripts/sync_to_azure.py --push --index` uploads data and approved documents to Blob Storage and builds the search indexes.
4. `python scripts/create_agents.py` creates all six agents in Foundry (also done automatically at start-up).
5. `streamlit run app/streamlit_app.py` (or `python client/app.py`).
6. `python tests/run_tests.py`. This rewrites `docs/test_evidence.md` from the ONLINE run.

**Switches if something goes wrong** (all in `.env`): `EDUCATION_RETRIEVAL=index|knowledge_base`, `AGENT_RUNTIME=foundry|framework`, `AUTO_UPLOAD=0|1`, `OFFLINE=1`. Details in the guide, section B.

## Design in one paragraph

Facts (consent, rule matches, reading statistics, missing dates, task lists) are computed by code. Agents only write the wording, and that wording is rejected and replaced by a template if it contains a number that is not in the facts, any diagnosis or judgement of a reading, medication advice or a claim to be a clinician. Each agent can use only its own tools. The orchestrator produces two separate outputs (member response and coordinator packet) plus an audit record that contains no message text and masks member IDs.

## Things you must decide or check (marked in the code)

- **ER-502 test values** live in `data/high_risk_values.csv` and are editable in the UI (blood pressure 160/100, glucose 300). They are demo placeholders chosen to make the rule demonstrable. They are not clinical thresholds. Real values must come from a domain expert.
- **"Today"** is fixed at 2026-10-07 (`REFERENCE_DATE`) so demos and tests repeat exactly.
- **Endpoint format**: `AZURE_OPENAI_ENDPOINT` is passed as `base_url`, as in the Agent Framework samples. Use the endpoint format shown in your Foundry project.
- `EMBEDDING_DIMENSIONS` defaults to 1536. Set it if your embedding model differs.
- The care-plan guidance index is created for the "indexed separately" requirement. The Care Plan agent reads the same guidance files locally through a tool; the Education agent is deliberately not attached to that index.

## Added synthetic records (same schema as the seed data)

Member M-105, readings R-206 to R-209 and FAQ and guidance articles FAQ-701, FAQ-702, CPG-801, CPG-802. They exist only to test corrections (R-206 replaced by R-207), contradictions (R-208 vs R-209) and the separate FAQ / guidance indexes. Each is labelled in the data.

## Test evidence and what was not verified

`docs/test_evidence.md` and `docs/test_results.json` in this repository come from the **OFFLINE dry run** (templates, no Azure calls): 14 of 14 scenarios pass, and the ingest and mock-Azure checks pass as well. They prove the workflow and the safety rules, not live model behaviour.

The Foundry parts (agent registration, AI Search retrieval, live model wording) need your own Azure resources, so they are not covered by the committed evidence. The SDK imports, agent construction, middleware and failure fallbacks were checked against the installed packages. Once your endpoints are in `.env`, run `python tests/run_tests.py` to regenerate the evidence from the ONLINE run.

---

Built by [Sujit](https://github.com/sujit428755). Licensed under MIT.
