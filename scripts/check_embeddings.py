"""Quick test of the embedding deployment: python scripts/check_embeddings.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config
from src.azure_integration import search

print("Deployment name used :", config.TEXT_EMBEDDING_MODEL_NAME)
print("Azure OpenAI endpoint:", config.AZURE_OPENAI_ENDPOINT or "(not set)")
print("Foundry project      :", config.FOUNDRY_PROJECT_ENDPOINT or "(not set)")
try:
    v = search.embed(["home blood pressure reading"])[0]
    print(f"OK - got a vector of {len(v)} numbers. Index is configured for {search.DIMENSIONS}.")
    if len(v) != search.DIMENSIONS:
        print(f"MISMATCH: set EMBEDDING_DIMENSIONS={len(v)} in .env and delete the old indexes.")
except Exception as e:
    print("FAILED:\n", e)
