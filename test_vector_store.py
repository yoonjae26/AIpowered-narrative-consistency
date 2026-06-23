from backend.database.vector_store import get_vector_store

vs = get_vector_store()

vs.reset()

vs.upsert("a", [0.1, 0.2, 0.3], text="hello world")
vs.upsert("b", [0.9, 0.8, 0.7], text="far vector")
vs.upsert("c", [0.12, 0.21, 0.31], text="similar")

results = vs.query([0.1, 0.2, 0.3], limit=3)

for r in results:
    print(r.id, r.payload, r.vector)
