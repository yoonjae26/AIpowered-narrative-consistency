from backend.rag.embeddings.embedder import SentenceTransformerEmbedder
from backend.database.vector_store import get_vector_store  # nếu bạn có

import os


def load_documents():
    """
    TEMP loader – bạn thay bằng DB thật của bạn sau
    """
    return [
        "NarrativeOS is an AI system for narrative consistency.",
        "Characters have traits, goals, and relationships.",
        "The system maintains world state using event sourcing.",
    ]


def main():
    print("🚀 Rebuilding vector store...")

    embedder = SentenceTransformerEmbedder()
    vector_store = get_vector_store()

    # 1. reset collection
    try:
        vector_store.delete_collection()
        print("🧹 Old collection cleared")
    except Exception:
        print("⚠️ No existing collection or delete failed (safe to ignore)")

    docs = load_documents()

    print(f"📦 Loading {len(docs)} documents")

    # 2. embed
    embeddings = embedder.embed(docs)

    # 3. upsert
    for i, (doc, emb) in enumerate(zip(docs, embeddings)):
        vector_store.add(
            id=f"doc-{i}",
            text=doc,
            embedding=emb,
            metadata={"source": "rebuild_script"}
        )

    print("✅ Vector store rebuilt successfully")


if __name__ == "__main__":
    main()