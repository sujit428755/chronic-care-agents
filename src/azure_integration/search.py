"""Azure AI Search: three indexes (education, FAQ, care-plan guidance) built from the APPROVED documents.

`sync_indexes()` is idempotent: it creates/updates each index, uploads approved documents with embeddings and
removes documents that are no longer approved (Draft, Retired or deleted), so the Foundry agent never cites them.
"""
from __future__ import annotations

import os
from typing import Callable

import config
from src.knowledge import load_documents

def _default_dimensions() -> str:
    """text-embedding-3-large returns 3072 numbers, the other common models 1536. Override with EMBEDDING_DIMENSIONS."""
    return "3072" if "3-large" in (os.getenv("TEXT_EMBEDDING_MODEL_NAME") or "").lower() else "1536"


DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS") or _default_dimensions())
FOLDER_TO_INDEX = {
    "education": config.SEARCH_INDEX_EDU,
    "faq": config.SEARCH_INDEX_FAQ,
    "careplan_guidance": config.SEARCH_INDEX_CAREPLAN,
}


def is_configured() -> bool:
    return bool(config.SEARCH_SERVICE_ENDPOINT and config.FOUNDRY_PROJECT_ENDPOINT and config.TEXT_EMBEDDING_MODEL_NAME)


def _vectorizers():
    """A vectorizer lets Azure AI Search embed the agent's QUESTION itself (needed for vector / hybrid agent queries).
    Built from AZURE_OPENAI_ENDPOINT (the resource host) + AZURE_OPENAI_API_KEY + the embedding deployment name.
    If these are missing the index is still created (keyword + semantic search work; set SEARCH_QUERY_TYPE=semantic)."""
    from urllib.parse import urlparse

    if not (config.AZURE_OPENAI_ENDPOINT and config.AZURE_OPENAI_API_KEY and config.TEXT_EMBEDDING_MODEL_NAME):
        return [], None
    try:
        from azure.search.documents.indexes.models import AzureOpenAIModelName, AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters
        u = urlparse(config.AZURE_OPENAI_ENDPOINT)
        model = config.TEXT_EMBEDDING_MODEL_NAME.lower()
        mname = (AzureOpenAIModelName.TEXT_EMBEDDING3_LARGE if "3-large" in model
                 else AzureOpenAIModelName.TEXT_EMBEDDING3_SMALL if "3-small" in model else AzureOpenAIModelName.TEXT_EMBEDDING_ADA002)
        v = AzureOpenAIVectorizer(
            vectorizer_name="aoai-vectorizer",
            parameters=AzureOpenAIVectorizerParameters(resource_url=f"{u.scheme}://{u.netloc}", deployment_name=config.TEXT_EMBEDDING_MODEL_NAME,
                                                       api_key=config.AZURE_OPENAI_API_KEY, model_name=mname))
        return [v], "aoai-vectorizer"
    except Exception:  # noqa: BLE001  older SDKs: keep the index usable without a vectorizer
        return [], None


def build_index(name: str):
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration, SearchableField, SearchField, SearchFieldDataType, SearchIndex, SemanticConfiguration,
        SemanticField, SemanticPrioritizedFields, SemanticSearch, SimpleField, VectorSearch, VectorSearchProfile,
    )
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="article_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="program", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="version", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="scope", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True,
                    vector_search_dimensions=DIMENSIONS, vector_search_profile_name="vector-profile"),
    ]
    vectorizers, vectorizer_name = _vectorizers()
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw-config",
                                      **({"vectorizer_name": vectorizer_name} if vectorizer_name else {}))],
        vectorizers=vectorizers or None,
    )
    semantic = SemanticSearch(
        configurations=[SemanticConfiguration(
            name="default-semantic",
            prioritized_fields=SemanticPrioritizedFields(title_field=SemanticField(field_name="title"),
                                                         content_fields=[SemanticField(field_name="content")]))],
        default_configuration_name="default-semantic",
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector_search, semantic_search=semantic)


def _credential():
    from azure.core.credentials import AzureKeyCredential
    from azure.identity import DefaultAzureCredential
    return AzureKeyCredential(config.SEARCH_API_KEY) if config.SEARCH_API_KEY else DefaultAzureCredential()


def _embedding_clients():
    """Yield (label, client). 1) the Azure OpenAI resource (AZURE_OPENAI_ENDPOINT + key) - same route the framework
    runtime uses; 2) the Foundry project's OpenAI client. The first one that answers is used."""
    from urllib.parse import urlparse
    if config.AZURE_OPENAI_ENDPOINT and config.AZURE_OPENAI_API_KEY:
        from openai import OpenAI
        u = urlparse(config.AZURE_OPENAI_ENDPOINT)
        base = f"{u.scheme}://{u.netloc}/openai/v1/"
        yield f"Azure OpenAI resource {base}", OpenAI(base_url=base, api_key=config.AZURE_OPENAI_API_KEY)
    if config.FOUNDRY_PROJECT_ENDPOINT:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        yield (f"Foundry project {config.FOUNDRY_PROJECT_ENDPOINT}",
               AIProjectClient(endpoint=config.FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential()).get_openai_client())


def embed(texts: list[str]) -> list[list[float]]:
    errors: list[str] = []
    for label, client in _embedding_clients():
        try:
            out: list[list[float]] = []
            for i in range(0, len(texts), 16):
                out += [d.embedding for d in client.embeddings.create(model=config.TEXT_EMBEDDING_MODEL_NAME, input=texts[i:i + 16]).data]
            return out
        except Exception as e:  # noqa: BLE001
            errors.append(f"  - {label}, deployment '{config.TEXT_EMBEDDING_MODEL_NAME}': {type(e).__name__}: {str(e)[:200]}")
    raise RuntimeError("Embedding call failed. The DEPLOYMENT NAME (not the model name) must exist on the resource being called.\n"
                       + "\n".join(errors or ["  - no endpoint configured"]))


def plan() -> dict[str, list[dict]]:
    by_folder: dict[str, list[dict]] = {f: [] for f in FOLDER_TO_INDEX}
    for d in load_documents():
        by_folder[d["folder"]].append(d)
    return by_folder


def sync_indexes(dry_run: bool = False, progress: Callable[[str], None] = lambda m: None) -> dict:
    by_folder = plan()
    if dry_run:
        for folder, name in FOLDER_TO_INDEX.items():
            idx = build_index(name)
            progress(f"[dry-run] index '{idx.name}' ({len(idx.fields)} fields) <- {len(by_folder[folder])} approved document(s)")
        return {name: len(by_folder[f]) for f, name in FOLDER_TO_INDEX.items()}
    if not is_configured():
        raise RuntimeError("SEARCH_SERVICE_ENDPOINT, FOUNDRY_PROJECT_ENDPOINT and TEXT_EMBEDDING_MODEL_NAME must be set in .env")
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    cred = _credential()
    index_client = SearchIndexClient(endpoint=config.SEARCH_SERVICE_ENDPOINT, credential=cred)
    result = {}
    for folder, name in FOLDER_TO_INDEX.items():
        docs = by_folder[folder]
        try:
            index_client.create_or_update_index(build_index(name))
        except Exception as e:  # noqa: BLE001
            if "CannotChangeExistingField" not in str(e) and "cannot be changed" not in str(e):
                raise
            # Azure cannot alter a vector field (e.g. 1536 -> 3072 dimensions). The index is only a copy of the
            # approved documents, so drop it and rebuild it.
            progress(f"'{name}': existing index has a different vector setup - deleting and rebuilding it")
            index_client.delete_index(name)
            index_client.create_or_update_index(build_index(name))
        client = SearchClient(endpoint=config.SEARCH_SERVICE_ENDPOINT, index_name=name, credential=cred)
        wanted = {d["article_id"] for d in docs}
        stale = [{"id": r["id"]} for r in client.search(search_text="*", select=["id"], top=1000) if r["id"] not in wanted]
        if stale:
            client.delete_documents(stale)
            progress(f"'{name}': removed {len(stale)} document(s) that are no longer approved")
        if docs:
            vecs = embed([f"{d['title']}\n{d['content']}" for d in docs])
            client.upload_documents([{
                "id": d["article_id"], "article_id": d["article_id"], "title": d["title"], "program": d["program"],
                "version": d["version"], "scope": d.get("scope", ""), "doc_type": folder, "content": d["content"],
                "content_vector": v} for d, v in zip(docs, vecs)])
        progress(f"'{name}': {len(docs)} approved document(s) indexed")
        result[name] = len(docs)
    return result


def refresh_knowledge_sources(progress: Callable[[str], None] = lambda m: None) -> dict:
    """Knowledge-base mode: ask the indexers behind your knowledge sources to read Blob Storage again.

    Names come from KNOWLEDGE_INDEXERS in .env (see the indexers list in the Azure portal; exact names: check docs).
    Deleted/retired files only disappear from the index if the indexer has deletion detection (check docs).
    """
    if not config.KNOWLEDGE_INDEXERS:
        progress("KNOWLEDGE_INDEXERS is empty: refresh the knowledge sources in the portal (or set the indexer names in .env).")
        return {"ran": [], "manual": True}
    from azure.search.documents.indexes import SearchIndexerClient
    client = SearchIndexerClient(endpoint=config.SEARCH_SERVICE_ENDPOINT, credential=_credential())
    ran = []
    for name in config.KNOWLEDGE_INDEXERS:
        client.run_indexer(name)
        progress(f"started indexer '{name}'")
        ran.append(name)
    return {"ran": ran, "manual": False}


def sync_for_current_mode(progress: Callable[[str], None] = lambda m: None) -> dict:
    """The right 'make the search side current' step for EDUCATION_RETRIEVAL."""
    from src.azure_integration import blob
    try:
        out = refresh_knowledge_sources(progress) if config.EDUCATION_RETRIEVAL == "knowledge_base" else sync_indexes(progress=progress)
        blob.record_sync("indexing", True, config.EDUCATION_RETRIEVAL)
        return out
    except Exception as exc:  # noqa: BLE001
        blob.record_sync("indexing", False, f"{type(exc).__name__}: {exc}")
        raise
