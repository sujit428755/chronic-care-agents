# Known limitations and human escalation points

## Limitations
- Synthetic data only; the dataset is tiny and a fixed "today" (2026-10-07) is used.
- ER-502 test values (BP 160/100, glucose 300) are demo placeholders, not clinical thresholds. Real values must be set by clinicians.
- Request routing uses a model classifier with a keyword fallback; unusual phrasing can be routed to the wrong category. Medication and clinical-advice checks are keyword and pattern based and may miss unusual wording (they fail towards staff follow-up for the cases they do catch).
- Offline keyword retrieval is much weaker than Azure AI Search retrieval; offline results do not prove retrieval quality.
- Reminders in Hindi and Kannada depend on model translation quality and have not been reviewed by a native speaker. Offline templates are English only.
- Education answers are checked against the approved catalog (ID, version, program) but the answer text itself is only checked for forbidden language, not for full factual faithfulness.
- Contradiction detection covers same-type readings with the same timestamp and different values. It does not detect other kinds of inconsistency.
- No identity or login: the member ID is typed into the client. No real authentication is implemented.
- Minimal case context only: nothing is remembered between requests, so follow-up questions do not carry context.
- Staff review queue and audit log are local files, not a real case-management system.

## Human escalation points
| Trigger | Who is told | What the system does |
|---|---|---|
| ER-501 consent not active | Program staff | Stops, reads no data, member told to contact staff |
| ER-502 configured test value matched | Staff (urgent review) | Creates urgent staff-review record, no interpretation |
| ER-503 medication change request | Qualified clinician | Declines; clinician-referral record |
| ER-504 contradictory readings or source version conflict | Staff (human review) | Marks uncertainty, draws no conclusion |
| No approved article found | Program staff | States the gap, asks staff to follow up |
| Request for interpretation or medical advice | Program staff | Declines, routes to staff |
| Data tool or knowledge base unavailable | Member told to retry or contact staff | Clear message, nothing invented |

The system never determines emergency priority. It only tells the member to contact the care team or local emergency services if concerned.

## Added with the data, UI and Azure sync work

- Azure Blob Storage, AI Search indexing and the Foundry agent were not run against live resources (no endpoints were available). They were checked offline only.
- Uploaded files are checked for format and obvious personal data patterns, but this is a warning, not a guarantee. Use synthetic data only.
- The UI has no login. A real deployment needs authentication and role-based access (members must never see the staff view).
- Streamlit keeps data in files on disk. Two people saving at the same moment could overwrite each other (a backup is kept). A real system needs a database.
- Rule logic is fixed in code on purpose. Only rule values and word lists are editable in the UI.
- Reading a scanned PDF is not supported (no OCR).

## Added with the Foundry / Blob build

- **Not run against live Azure.** Agent registration, Blob upload, AI Search indexing and the knowledge base were tested only with mocks (`tests/test_azure_mock.py`). The first online run is the real test.
- **Foundry knowledge base is a preview feature** (api-version 2025-11-01-preview). Names, steps and behaviour may change - check docs. Knowledge sources and the knowledge base are created by hand in the portal; their exact names go into `.env`.
- **Knowledge-base citations** are file names mapped to the approved catalog; the version shown comes from the catalog, not from the file.
- **Agent replies are JSON parsed from text.** If a reply cannot be parsed or fails the guards (safety wording, number grounding, citation check), the safe template answer is used instead.
- **Draft/Retired removal in knowledge-base mode** depends on indexer deletion detection - check docs and test it once.
- **Switches** if something fails: `EDUCATION_RETRIEVAL=index`, `AGENT_RUNTIME=framework`, `AUTO_REGISTER_AGENTS=0`, `AUTO_UPLOAD=0`, `OFFLINE=1`.

- **Bigger data, same logic.** The tables hold 100+ rows each, but ER-501 to ER-504 are still the only rules; the extra escalation rows are routing variants (which staff queue). Test values for reading types not present in readings.csv are dormant. All thresholds are demo placeholders, not clinical values.
- **Offline retrieval is keyword based.** With 110 articles a loosely worded question can match an unrelated approved article (test T13 prompt was tightened for this). Online, Azure AI Search ranks better.
