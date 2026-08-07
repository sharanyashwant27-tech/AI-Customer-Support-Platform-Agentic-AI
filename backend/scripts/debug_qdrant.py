import asyncio
from qdrant_client import QdrantClient
from app.rag.embeddings.factory import HashEmbeddingAdapter

c = QdrantClient(host="localhost", port=26333, check_compatibility=False)
print("collections", c.get_collections())
col = "knowledge_base"
info = c.get_collection(col)
print("points", info.points_count)
pts, _ = c.scroll(col, limit=2, with_payload=True, with_vectors=False)
print("scroll_payloads", [p.payload for p in pts])
emb = HashEmbeddingAdapter(384)
vec = asyncio.run(emb.embed_query("return policy"))
print("dim", len(vec))
resp = c.query_points(collection_name=col, query=vec, limit=3)
print("points", resp.points)
for p in resp.points:
    print(p.score, (p.payload or {}).get("source"), (p.payload or {}).get("text", "")[:60])
