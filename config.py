"""Central configuration. Secrets are never hard-coded: they come from the .env file."""
import os
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # offline mode still works without python-dotenv
    load_dotenv = None

ROOT = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = ROOT / "knowledge"
LOG_DIR = ROOT / "logs"
DOCS_DIR = ROOT / "docs"

# ---- Agent Framework (specialist agents) - same variable names as the reference demos ----
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# ---- Foundry project (Education RAG agent) - same names as the reference agent_v2.py ----
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
MODEL_DEPLOYMENT_NAME = os.getenv("MODEL_DEPLOYMENT_NAME")
TEXT_EMBEDDING_MODEL_NAME = os.getenv("TEXT_EMBEDDING_MODEL_NAME")

# ---- Azure AI Search ----
SEARCH_SERVICE_ENDPOINT = os.getenv("SEARCH_SERVICE_ENDPOINT")
# vector_semantic_hybrid (default) | semantic | simple.  Use "semantic" if the agent's search tool complains about vectors.
SEARCH_QUERY_TYPE = (os.getenv("SEARCH_QUERY_TYPE") or "vector_semantic_hybrid").strip().lower()
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")  # optional; empty = use `az login`
AI_SEARCH_CONNECTION_NAME = os.getenv("AI_SEARCH_CONNECTION_NAME")
SEARCH_INDEX_EDU = os.getenv("SEARCH_INDEX_EDU", "edu-articles")
SEARCH_INDEX_FAQ = os.getenv("SEARCH_INDEX_FAQ", "program-faqs")
SEARCH_INDEX_CAREPLAN = os.getenv("SEARCH_INDEX_CAREPLAN", "careplan-guidance")

EDUCATION_AGENT_NAME = "education-rag-agent"

# ---- The six Foundry agents (names shown in the Foundry portal; see the agent table) ----
FOUNDRY_AGENT_NAMES = {
    "orchestrator": "care-orchestrator-agent",     # LLM part of the Care Orchestrator: classifies / routes the request
    "reading": "reading-summary-agent",
    "careplan": "care-plan-agent",
    "education": EDUCATION_AGENT_NAME,
    "engagement": "engagement-agent",
    "escalation": "escalation-agent",
}

# ---- SWITCHES (change these in .env if something goes wrong) ----
# AGENT_RUNTIME     foundry   = all six agents are Foundry agents, called by name (default when online)
#                   framework = specialist agents run in Python with Microsoft Agent Framework; only Education is in Foundry
AGENT_RUNTIME = os.getenv("AGENT_RUNTIME", "foundry").strip().lower()
# EDUCATION_RETRIEVAL  index          = Azure AI Search tool over the edu + FAQ indexes (default, most robust)
#                      knowledge_base = Foundry knowledge base (built on Blob Storage) through an MCP tool
EDUCATION_RETRIEVAL = os.getenv("EDUCATION_RETRIEVAL", "index").strip().lower()
KNOWLEDGE_BASE_NAME = os.getenv("KNOWLEDGE_BASE_NAME", "")
SEARCH_SERVICE_PROJECT_CONNECTION_NAME = os.getenv("SEARCH_SERVICE_PROJECT_CONNECTION_NAME") or AI_SEARCH_CONNECTION_NAME or ""
KNOWLEDGE_BASE_API_VERSION = os.getenv("KNOWLEDGE_BASE_API_VERSION", "2025-11-01-preview")
# Comma-separated names of the indexers created by your knowledge sources (run after every upload). Check the portal.
KNOWLEDGE_INDEXERS = [x.strip() for x in os.getenv("KNOWLEDGE_INDEXERS", "").split(",") if x.strip()]
# Register / update the six agents in Foundry automatically when the app or client starts (online only)
AUTO_REGISTER_AGENTS = os.getenv("AUTO_REGISTER_AGENTS", "1").strip().lower() in ("1", "true", "yes")

# ---- Application behaviour ----
# "Today" for the synthetic dataset. Fixed so the demo and the test evidence are repeatable.
REFERENCE_DATE = date.fromisoformat(os.getenv("REFERENCE_DATE", "2026-10-07"))
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 31

# OFFLINE=1 runs the whole workflow without calling any model or Azure service.
# The safety logic is identical; only the wording is template-based.
OFFLINE = os.getenv("OFFLINE", "0") == "1"


def foundry_agents_enabled() -> bool:
    """True when the six agents should be called as Foundry agents."""
    return (not OFFLINE) and AGENT_RUNTIME == "foundry"


def set_offline(flag: bool) -> None:
    global OFFLINE
    OFFLINE = bool(flag)


DISCLAIMER = (
    "Educational use only. This assistant is not a clinician. It does not diagnose, "
    "change treatment or give personalised medical advice. Your care team makes all clinical decisions."
)

# ---- Azure Blob Storage (data + documents are uploaded here, then indexed into Azure AI Search) ----
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")      # e.g. https://<account>.blob.core.windows.net (uses az login)
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "chronic-care-data")
# AUTO_UPLOAD: every save in the UI is uploaded to Blob Storage at once (when Blob is configured). 0 = manual upload only.
AUTO_UPLOAD = os.getenv("AUTO_UPLOAD", "1").strip().lower() in ("1", "true", "yes")
# AUTO_SYNC: after the upload, also rebuild the search indexes (index mode) or run the knowledge-source indexers (knowledge_base mode)
AUTO_SYNC = os.getenv("AUTO_SYNC", "0").strip().lower() in ("1", "true", "yes")
# PULL_ON_START: download the latest files from Blob when the app starts (shared copy for the whole team)
PULL_ON_START = os.getenv("PULL_ON_START", "0").strip().lower() in ("1", "true", "yes")
BLOB_APPROVED_PREFIX = "knowledge"                 # only Approved documents live here (this is what the knowledge sources read)
BLOB_UNAPPROVED_PREFIX = "knowledge-unapproved"    # Draft and Retired documents, never searched

# ---- Upload limits for the Data Manager ----
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_UPLOAD_EXTENSIONS = (".csv", ".json", ".xlsx", ".txt", ".md", ".docx", ".pdf")
