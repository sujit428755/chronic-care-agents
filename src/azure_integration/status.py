"""Connection checks for the Azure Sync page. Never returns or logs a secret value, only whether it is set."""
from __future__ import annotations

import config


def settings_overview() -> list[dict]:
    def row(label, value, secret=False, hint=""):
        return {"setting": label, "state": "set" if value else "missing", "hint": hint}
    return [
        row("AZURE_OPENAI_ENDPOINT / API_KEY / DEPLOYMENT", config.AZURE_OPENAI_ENDPOINT and config.AZURE_OPENAI_API_KEY and config.AZURE_OPENAI_DEPLOYMENT_NAME, hint="Agent Framework specialist agents"),
        row("FOUNDRY_PROJECT_ENDPOINT + MODEL_DEPLOYMENT_NAME", config.FOUNDRY_PROJECT_ENDPOINT and config.MODEL_DEPLOYMENT_NAME, hint="Education RAG agent in Foundry"),
        row("TEXT_EMBEDDING_MODEL_NAME", config.TEXT_EMBEDDING_MODEL_NAME, hint="Embeddings for the vector index"),
        row("SEARCH_SERVICE_ENDPOINT (+ SEARCH_API_KEY or az login)", config.SEARCH_SERVICE_ENDPOINT, hint="Azure AI Search"),
        row("AI_SEARCH_CONNECTION_NAME", config.AI_SEARCH_CONNECTION_NAME, hint="Search connection inside the Foundry project"),
        row("AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL", config.AZURE_STORAGE_CONNECTION_STRING or config.AZURE_STORAGE_ACCOUNT_URL, hint="Blob Storage"),
        row("KNOWLEDGE_BASE_NAME (only for EDUCATION_RETRIEVAL=knowledge_base)", config.KNOWLEDGE_BASE_NAME, hint="Foundry knowledge base on Blob"),
        row("KNOWLEDGE_INDEXERS (optional)", config.KNOWLEDGE_INDEXERS, hint="Indexers run after each upload (knowledge-base mode)"),
    ]


def test_blob() -> tuple[bool, str]:
    from src.azure_integration import blob
    if not blob.is_configured():
        return False, "Blob Storage is not configured in .env"
    try:
        cc = blob.container_client()
        n = sum(1 for _ in cc.list_blobs())
        return True, f"Connected. Container '{config.AZURE_STORAGE_CONTAINER}' holds {n} file(s)."
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


def test_search() -> tuple[bool, str]:
    from src.azure_integration import search
    if not config.SEARCH_SERVICE_ENDPOINT:
        return False, "SEARCH_SERVICE_ENDPOINT is not set"
    try:
        from azure.search.documents.indexes import SearchIndexClient
        names = [i.name for i in SearchIndexClient(endpoint=config.SEARCH_SERVICE_ENDPOINT, credential=search._credential()).list_indexes()]
        have = [n for n in search.FOLDER_TO_INDEX.values() if n in names]
        return True, f"Connected. {len(have)} of 3 project indexes exist ({', '.join(have) or 'none yet'})."
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


def test_foundry() -> tuple[bool, str]:
    if not config.FOUNDRY_PROJECT_ENDPOINT:
        return False, "FOUNDRY_PROJECT_ENDPOINT is not set"
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        client = AIProjectClient(endpoint=config.FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential())
        names = [a.name for a in client.agents.list()]
        have = [n for n in config.FOUNDRY_AGENT_NAMES.values() if n in names]
        return True, f"Connected. {len(have)} of 6 project agents exist in Foundry ({', '.join(have) or 'none yet'})."
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"
