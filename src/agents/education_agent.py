"""Education RAG Agent.

ONLINE : a Foundry prompt agent ("education-rag-agent"). Retrieval is either the Azure AI Search tool over the education + FAQ
         indexes (EDUCATION_RETRIEVAL=index, pattern of agent_v2.py) or a Foundry knowledge base on Blob Storage through an MCP
         tool (EDUCATION_RETRIEVAL=knowledge_base, pattern of foundry_demo.py). Registered by scripts/create_agents.py, then called by name.
OFFLINE: a small local keyword retriever over the same markdown files (for testing without Azure).

Least privilege: this agent can search approved articles only. It cannot read readings or care plans.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import config
from src.knowledge import get_article_meta, is_applicable, search_local
from src.models import SourceRef
from src.prompts import EDUCATION_INSTRUCTIONS

CITE_RE = re.compile(r"\b((?:EDU|FAQ|CPG)-\d{3})\b(?:\s*[\(,]?\s*(?:version\s*)?(v\d+))?", re.IGNORECASE)
GAP_SENTINEL = "NO_APPROVED_ARTICLE"


# ----------------------------------------------------------------------------
# Foundry (online)
# ----------------------------------------------------------------------------
def _project_client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if not config.FOUNDRY_PROJECT_ENDPOINT:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set in .env (or run with OFFLINE=1).")
    return AIProjectClient(endpoint=config.FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential())


def _search_connection_id(project_client) -> str:
    for connection in project_client.connections.list():
        if connection.name == config.AI_SEARCH_CONNECTION_NAME:
            return connection.id
    raise RuntimeError(f"No Foundry connection named '{config.AI_SEARCH_CONNECTION_NAME}' (AI_SEARCH_CONNECTION_NAME).")


def build_tool(project_client=None):
    """The retrieval tool for the Education agent. Two modes, chosen by EDUCATION_RETRIEVAL in .env:

    index           Azure AI Search tool over the education + FAQ indexes   (pattern of the reference agent_v2.py)
    knowledge_base  Foundry knowledge base (built on Blob Storage) via MCP  (pattern of the reference foundry_demo.py)

    The care-plan guidance index / folder is NOT attached in either mode (least privilege).
    """
    if config.EDUCATION_RETRIEVAL == "knowledge_base":
        from azure.ai.projects.models import MCPTool

        missing = [n for n, v in {"KNOWLEDGE_BASE_NAME": config.KNOWLEDGE_BASE_NAME, "SEARCH_SERVICE_ENDPOINT": config.SEARCH_SERVICE_ENDPOINT,
                                  "SEARCH_SERVICE_PROJECT_CONNECTION_NAME (or AI_SEARCH_CONNECTION_NAME)": config.SEARCH_SERVICE_PROJECT_CONNECTION_NAME}.items() if not v]
        if missing:
            raise RuntimeError("Knowledge-base mode needs these in .env: " + ", ".join(missing) + ". Or set EDUCATION_RETRIEVAL=index.")
        mcp_endpoint = (f"{config.SEARCH_SERVICE_ENDPOINT.rstrip('/')}/knowledgebases/{config.KNOWLEDGE_BASE_NAME}/mcp"
                        f"?api-version={config.KNOWLEDGE_BASE_API_VERSION}")
        return MCPTool(
            server_label=config.KNOWLEDGE_BASE_NAME,
            server_url=mcp_endpoint,
            require_approval="never",
            allowed_tools=["knowledge_base_retrieve"],
            project_connection_id=config.SEARCH_SERVICE_PROJECT_CONNECTION_NAME,   # same as the reference foundry_demo.py
        )

    from azure.ai.projects.models import AISearchIndexResource, AzureAISearchQueryType, AzureAISearchTool, AzureAISearchToolResource

    _QUERY_TYPES = {"vector_semantic_hybrid": AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID, "semantic": AzureAISearchQueryType.SEMANTIC,
                    "simple": AzureAISearchQueryType.SIMPLE}
    connection_id = _search_connection_id(project_client or _project_client())
    indexes = [
        AISearchIndexResource(project_connection_id=connection_id, index_name=name,
                              query_type=_QUERY_TYPES.get(config.SEARCH_QUERY_TYPE, AzureAISearchQueryType.VECTOR_SEMANTIC_HYBRID), top_k=3)
        for name in (config.SEARCH_INDEX_EDU, config.SEARCH_INDEX_FAQ)
    ]
    return AzureAISearchTool(azure_ai_search=AzureAISearchToolResource(indexes=indexes))


def register_agent():
    """Create (a new version of) the Education RAG agent in Foundry, in the retrieval mode set in .env."""
    from azure.ai.projects.models import PromptAgentDefinition
    from src.agents.registry import education_instructions

    project_client = _project_client()
    return project_client.agents.create_version(
        agent_name=config.EDUCATION_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=config.MODEL_DEPLOYMENT_NAME,
            instructions=education_instructions(),
            tools=[build_tool(project_client)],
        ),
    )


def _ask_foundry_sync(question: str, program: str) -> str:
    project_client = _project_client()
    openai_client = project_client.get_openai_client()
    conversation = openai_client.conversations.create()  # new conversation every time: nothing is kept between requests
    prompt = f"Member's program: {program}\nQuestion: {question}"
    response = openai_client.responses.create(
        tool_choice="required",
        conversation=conversation.id,
        input=prompt,
        extra_body={"agent_reference": {"name": config.EDUCATION_AGENT_NAME, "type": "agent_reference"}},
    )
    return response.output_text or ""


# ----------------------------------------------------------------------------
# Offline retriever
# ----------------------------------------------------------------------------
def _ask_local(question: str, program: str) -> str:
    hits = search_local(question, ("education", "faq"), program=program)
    if not hits:
        return GAP_SENTINEL
    top = hits[0]
    lines = []
    for ln in top["content"].splitlines():
        s = ln.strip()
        if not s or s.startswith(("Article ID:", "#")):
            continue
        lines.append(s.lstrip("-* ").strip())
    excerpt = ""
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(lines)):
        if len(excerpt) + len(sentence) > 500:
            break
        excerpt += (" " if excerpt else "") + sentence
    return f"From the approved article \"{top['title']}\": {excerpt}\nSources: {top['article_id']} ({top['version']})"


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
async def ask(question: str, program: str, offline: bool) -> str:
    if offline:
        return _ask_local(question, program)
    return await asyncio.to_thread(_ask_foundry_sync, question, program)


def interpret(text: str, program: str) -> dict:
    """Validate an education answer against the approved catalog.

    Returns: answer (text without the Sources line), sources (valid, applicable, current catalog versions),
             gap (True if no usable approved source), version_conflicts (for ER-504), rejected (ids not usable).
    """
    if GAP_SENTINEL in text:
        return {"answer": "", "sources": [], "gap": True, "version_conflicts": [], "rejected": []}

    cited: dict[str, Optional[str]] = {}
    for m in CITE_RE.finditer(text):
        art_id, ver = m.group(1).upper(), (m.group(2).lower() if m.group(2) else None)
        if art_id not in cited or (cited[art_id] is None and ver):
            cited[art_id] = ver

    sources, conflicts, rejected = [], [], []
    for art_id, ver in cited.items():
        meta = get_article_meta(art_id)
        if meta is None or not is_applicable(meta, program):
            rejected.append(art_id)
            continue
        if ver and ver != meta["version"]:
            conflicts.append({"article_id": art_id, "cited_version": ver, "approved_version": meta["version"]})
        sources.append(SourceRef(source_id=art_id, version=meta["version"]))

    answer = "\n".join(ln for ln in text.splitlines() if not ln.strip().lower().startswith("sources:")).strip()
    return {
        "answer": answer,
        "sources": sources,
        # If ANY cited article is unknown or not allowed for this member's program, the whole answer is withheld.
        "gap": (not sources) or bool(rejected),
        "version_conflicts": conflicts,
        "rejected": rejected,
    }
