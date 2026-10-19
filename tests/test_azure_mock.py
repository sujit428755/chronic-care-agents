"""Checks for the Azure-facing code WITHOUT any Azure account (fake Foundry and fake Blob container).

    python tests/test_azure_mock.py

They prove the logic (six agents, both retrieval modes, approved-only Blob layout, fallbacks).
They do NOT prove that your real Azure resources are set up correctly: that needs the online run.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402

tmp = Path(tempfile.mkdtemp())
shutil.copytree(config.DATA_DIR, tmp / "data")
shutil.copytree(config.KNOWLEDGE_DIR, tmp / "knowledge")
config.ROOT, config.DATA_DIR, config.KNOWLEDGE_DIR, config.LOG_DIR = tmp, tmp / "data", tmp / "knowledge", tmp / "logs"

from src.agents import education_agent, foundry_runtime, registry  # noqa: E402
from src.azure_integration import blob  # noqa: E402
from src.ingest import documents  # noqa: E402
from src.orchestrator import CareOrchestrator  # noqa: E402

foundry_runtime.STATE_FILE = config.LOG_DIR / "foundry_agents.json"
blob.SYNC_FILE = config.LOG_DIR / "sync_state.json"
passed = 0


def check(name, cond):
    global passed
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        sys.exit(1)
    passed += 1


# ---------------------------------------------------------------- 1. registering six agents
created = []


class FakeAgents:
    def create_version(self, agent_name, definition):
        created.append((agent_name, definition))
        return SimpleNamespace(name=agent_name, version=str(len([c for c in created if c[0] == agent_name])), id="id-" + agent_name)


class FakeProject:
    agents = FakeAgents()

    class connections:  # noqa: N801
        @staticmethod
        def list():
            return [SimpleNamespace(name="search-conn", id="conn-id")]


foundry_runtime._project_client = lambda: FakeProject()
education_agent._project_client = lambda: FakeProject()
config.MODEL_DEPLOYMENT_NAME, config.AI_SEARCH_CONNECTION_NAME = "gpt-test", "search-conn"
config.SEARCH_SERVICE_ENDPOINT, config.KNOWLEDGE_BASE_NAME = "https://s.search.windows.net", "kb-chronic"
config.SEARCH_SERVICE_PROJECT_CONNECTION_NAME = "search-conn"

config.EDUCATION_RETRIEVAL = "index"
res = foundry_runtime.register_all()
check("six agents are registered with the documented names", sorted(c[0] for c in created) == sorted(config.FOUNDRY_AGENT_NAMES.values()) and len(created) == 6)
edu_def = next(d for n, d in created if n == "education-rag-agent")
check("index mode: Education agent uses the AI Search tool", type(edu_def.tools[0]).__name__ == "AzureAISearchTool")
check("structured agents have no tools and are told facts come in the message",
      all(not getattr(d, "tools", None) and "FACTS (JSON)" in d.instructions for n, d in created if n in ("reading-summary-agent", "care-plan-agent", "escalation-agent", "engagement-agent")))
n_before = len(created)
foundry_runtime.register_all()
check("second run registers nothing (definitions unchanged)", len(created) == n_before)

config.EDUCATION_RETRIEVAL = "knowledge_base"
foundry_runtime.register_all()
new = created[n_before:]
check("switching to knowledge_base re-registers ONLY the Education agent", [n for n, _ in new] == ["education-rag-agent"])
tool = new[0][1].tools[0]
check("knowledge_base mode: MCP tool points at the knowledge base endpoint",
      type(tool).__name__ == "MCPTool" and "/knowledgebases/kb-chronic/mcp" in tool.server_url and tool.allowed_tools == ["knowledge_base_retrieve"])
check("knowledge_base mode: instructions ask for document IDs", "file name without the extension" in new[0][1].instructions)
config.KNOWLEDGE_BASE_NAME = ""
try:
    education_agent.build_tool()
    check("knowledge_base mode without KNOWLEDGE_BASE_NAME gives a clear error", False)
except RuntimeError as exc:
    check("knowledge_base mode without KNOWLEDGE_BASE_NAME gives a clear error", "KNOWLEDGE_BASE_NAME" in str(exc))
config.KNOWLEDGE_BASE_NAME = "kb-chronic"
config.EDUCATION_RETRIEVAL = "index"

# ---------------------------------------------------------------- 2. the workflow runs through Foundry agents
calls = []


def fake_call(key, prompt):
    calls.append((key, prompt))
    if key == "orchestrator":
        return "READINGS"
    if key == "reading":
        return json.dumps({"narrative": "Between 2026-10-01 and 2026-10-07 there are 3 recorded glucose readings (R-201, R-202, R-207). "
                           "No entry was recorded on: 2026-10-02, 2026-10-05, 2026-10-06, 2026-10-07. Descriptive summary only, not a diagnosis."})
    if key == "escalation":
        return "```json\n" + json.dumps({"reason_text": "ER-502 matched."}) + "\n```"
    return "{}"


foundry_runtime._call_sync = fake_call
config.set_offline(False)
config.AGENT_RUNTIME = "foundry"
orch = CareOrchestrator(offline=False)
r = asyncio.run(orch.handle("M-101", "Summarize my glucose readings for the last 7 days."))
keys = [k for k, _ in calls]
check("router and reading agents were called through Foundry", "orchestrator" in keys and "reading" in keys)
check("facts were sent inside the message", any(k == "reading" and "FACTS (JSON)" in p and "R-207" in p for k, p in calls))
check("grounded Foundry wording is used", "3 recorded glucose readings" in r.member_response.text)

def bad_reading(key, prompt):
    if key == "reading":
        return json.dumps({"narrative": "Your glucose is dangerous. Values were 999."})
    return fake_call(key, prompt)

foundry_runtime._call_sync = bad_reading
r = asyncio.run(orch.handle("M-101", "Summarize my glucose readings for the last 7 days."))
check("unsafe / ungrounded Foundry wording is replaced by the template", "dangerous" not in r.member_response.text and "999" not in r.member_response.text)
check("the rejection is recorded in the audit notes", any("reading_agent_wording_rejected" in n for n in r.audit.notes))

def boom(key, prompt):
    raise RuntimeError("Foundry down")

foundry_runtime._call_sync = boom
r = asyncio.run(orch.handle("M-101", "Summarize my glucose readings for the last 7 days."))
check("Foundry outage still gives a safe template answer", r.audit.disposition == "answered" and "R-201" in r.member_response.text)

# ---------------------------------------------------------------- 3. citations from knowledge-base mode
info = education_agent.interpret("Home readings help. Sources: EDU-401.md, FAQ-702.md", "Diabetes Support")
check("file-name citations map to catalog versions", {s.source_id for s in info["sources"]} == {"EDU-401", "FAQ-702"} and not info["gap"])
documents.save_document(title="Draft only", text="Secret draft text", doc_type="education", program="All programs", status="Draft")
draft_id = documents.next_article_id("education")
latest = sorted(p.stem for p in (config.KNOWLEDGE_DIR / "education").glob("EDU-*.md"))[-1]
info = education_agent.interpret(f"Something. Sources: {latest}.md", "Diabetes Support")
check("a Draft document can never be cited", info["gap"] and latest in info["rejected"])

# ---------------------------------------------------------------- 4. Blob layout (fake container)
class FakeContainer:
    def __init__(self):
        self.store = {}

    def list_blobs(self, name_starts_with=None):
        return [SimpleNamespace(name=n, size=len(v[0]), content_settings=SimpleNamespace(content_md5=v[1])) for n, v in self.store.items()]

    def upload_blob(self, name, data, overwrite=True, content_settings=None):
        self.store[name] = (data, bytes(content_settings.content_md5))

    def delete_blob(self, name):
        del self.store[name]


fake = FakeContainer()
blob.container_client = lambda: fake
files = blob.local_files()
check("Approved documents go under knowledge/, the Draft under knowledge-unapproved/",
      f"knowledge/education/EDU-401.md" in files and f"knowledge-unapproved/education/{latest}.md" in files and f"knowledge/education/{latest}.md" not in files)
r1 = blob.push()
check("first push uploads everything", r1["uploaded"] == len(files) and r1["removed"] == 0)
check("second push uploads nothing", blob.push()["uploaded"] == 0)
documents.set_status("EDU-405", "Retired")
r3 = blob.push()
check("retiring a document moves it out of knowledge/ in Blob", "knowledge/education/EDU-405.md" not in fake.store
      and "knowledge-unapproved/education/EDU-405.md" in fake.store and r3["removed"] == 1)
check("sync state records the upload", blob.read_sync_state()["upload"]["ok"] and blob.read_sync_state()["pending"] is False)
documents.set_status("EDU-405", "Approved", "QA")
blob.push()
check("approving it again brings it back", "knowledge/education/EDU-405.md" in fake.store)

print(f"\n{passed} checks passed")
