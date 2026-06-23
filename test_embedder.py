from backend.rag.embeddings.embedder import SentenceTransformerEmbedder

embedder = SentenceTransformerEmbedder()

v1 = embedder.embed("hello world")
v2 = embedder.embed("hello world again")

print(len(v1), v1[:5])
print(len(v2), v2[:5])
