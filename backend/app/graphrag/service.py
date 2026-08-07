"""Hybrid GraphRAG: knowledge graph + Neo4j with in-memory fallback.

Knowledge Graph
  Customer → PURCHASED → Product → COVERED_BY → Warranty
           → LINKED_TO → Support Policy → LINKED_TO → FAQ

Example: "My laptop battery stopped charging after 7 months."
  Customer → Laptop → Warranty → Battery Issue → Policy → Replacement Process
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Canonical relationship types in the support knowledge graph
REL_PURCHASED = "PURCHASED"
REL_COVERED_BY = "COVERED_BY"
REL_LINKED_TO = "LINKED_TO"
REL_HAS_ISSUE = "HAS_ISSUE"
REL_GOVERNED_BY = "GOVERNED_BY"
REL_RESOLVED_BY = "RESOLVED_BY"
REL_COVERS = "COVERS"

ENTITY_PATTERNS = [
    ("ORDER", re.compile(r"\bORD-\d+\b", re.I)),
    ("TICKET", re.compile(r"\bTKT-[A-Z0-9]+\b", re.I)),
    ("SKU", re.compile(r"\bSKU-[\w-]+\b", re.I)),
    ("POLICY", re.compile(r"\b(return|refund|shipping|warranty|support)\s+policy\b", re.I)),
    (
        "PRODUCT",
        re.compile(
            r"\b(laptop|notebook|headphones|keyboard|mouse|hub|charger|battery)\b",
            re.I,
        ),
    ),
    ("ISSUE", re.compile(r"\b(battery|charging|won'?t charge|stopped charging|defect)\b", re.I)),
    ("WARRANTY", re.compile(r"\b(warranty|guarantee)\b", re.I)),
]


class InMemoryGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def upsert_node(self, node_id: str, label: str, props: dict[str, Any]) -> None:
        existing = self.nodes.get(node_id) or {}
        self.nodes[node_id] = {**existing, "id": node_id, "label": label, **props}

    def upsert_edge(
        self, source: str, target: str, rel: str, props: dict[str, Any] | None = None
    ) -> None:
        key = (source, target, rel)
        self.edges = [e for e in self.edges if (e["source"], e["target"], e["type"]) != key]
        self.edges.append(
            {"source": source, "target": target, "type": rel, "props": props or {}}
        )

    def neighbors(self, node_id: str, *, direction: str = "out") -> list[dict[str, Any]]:
        hits = []
        for edge in self.edges:
            if direction == "out" and edge["source"] == node_id:
                target = self.nodes.get(edge["target"])
                if target:
                    hits.append({"edge": edge, "node": target})
            elif direction == "in" and edge["target"] == node_id:
                source = self.nodes.get(edge["source"])
                if source:
                    hits.append({"edge": edge, "node": source})
        return hits

    def related(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        q = query.lower()
        tokens = [tok for tok in re.split(r"\W+", q) if len(tok) > 2]
        hits = []
        for node in self.nodes.values():
            blob = (
                f"{node.get('id', '')} {node.get('name', '')} "
                f"{node.get('label', '')} {node.get('aliases', '')}"
            ).lower()
            if any(tok in blob for tok in tokens):
                hits.append(node)
        return hits[:limit]

    def walk(
        self,
        start_id: str,
        *,
        rel_types: list[str] | None = None,
        max_hops: int = 6,
    ) -> list[dict[str, Any]]:
        """BFS path of nodes following outgoing edges."""
        if start_id not in self.nodes:
            return []
        path: list[dict[str, Any]] = [
            {"id": start_id, **self.nodes[start_id], "via": None}
        ]
        current = start_id
        seen = {start_id}
        for _ in range(max_hops):
            nxt = None
            for edge in self.edges:
                if edge["source"] != current:
                    continue
                if rel_types and edge["type"] not in rel_types:
                    continue
                if edge["target"] in seen:
                    continue
                nxt = edge
                break
            if not nxt:
                # Prefer any unused outgoing edge
                for edge in self.edges:
                    if edge["source"] == current and edge["target"] not in seen:
                        nxt = edge
                        break
            if not nxt:
                break
            target = self.nodes.get(nxt["target"])
            if not target:
                break
            seen.add(nxt["target"])
            path.append({**target, "via": nxt["type"]})
            current = nxt["target"]
        return path


class GraphRAGService:
    """Customer → Product → Warranty → Policy → FAQ knowledge graph."""

    def __init__(self) -> None:
        self._driver = None
        self._memory = InMemoryGraph()
        self._seed_knowledge_graph()

    def _seed_knowledge_graph(self) -> None:
        """
        Seed the canonical support knowledge graph:

        Customer —PURCHASED→ Product —COVERED_BY→ Warranty
                 —LINKED_TO→ Support Policy —LINKED_TO→ FAQ
        """
        g = self._memory

        g.upsert_node(
            "CUSTOMER:default",
            "Customer",
            {"name": "Customer", "aliases": "user buyer account"},
        )
        g.upsert_node(
            "PRODUCT:laptop",
            "Product",
            {
                "name": "Laptop",
                "sku": "SKU-LT-01",
                "aliases": "notebook computer laptop battery",
            },
        )
        g.upsert_node(
            "PRODUCT:headphones",
            "Product",
            {"name": "Wireless Headphones Pro", "sku": "SKU-WH-01"},
        )
        g.upsert_node(
            "WARRANTY:laptop-12m",
            "Warranty",
            {
                "name": "Laptop 12-Month Limited Warranty",
                "months": 12,
                "aliases": "warranty guarantee battery",
            },
        )
        g.upsert_node(
            "WARRANTY:headphones-12m",
            "Warranty",
            {"name": "Headphones 12-Month Limited Warranty", "months": 12},
        )
        g.upsert_node(
            "POLICY:warranty-support",
            "SupportPolicy",
            {
                "name": "Support Policy",
                "aliases": "warranty support policy replacement",
            },
        )
        g.upsert_node(
            "POLICY:return",
            "SupportPolicy",
            {"name": "Return Policy", "days": 30},
        )
        g.upsert_node(
            "FAQ:battery-charging",
            "FAQ",
            {
                "name": "FAQ: Battery not charging",
                "aliases": "battery charging stopped charge",
                "answer": (
                    "If a laptop battery stops charging within the warranty period, "
                    "open a warranty claim for diagnosis, repair, or replacement."
                ),
            },
        )
        g.upsert_node(
            "FAQ:returns",
            "FAQ",
            {"name": "FAQ: Returns within 30 days"},
        )
        g.upsert_node(
            "ISSUE:battery",
            "Issue",
            {
                "name": "Battery Issue",
                "aliases": "battery stopped charging won't charge charging defect",
                "symptoms": "stopped charging, not charging, dead battery",
            },
        )
        g.upsert_node(
            "PROCESS:replacement",
            "Process",
            {
                "name": "Replacement Process",
                "aliases": "replace replacement RMA swap",
                "steps": (
                    "1) Verify purchase and warranty window  "
                    "2) Diagnose battery fault  "
                    "3) Approve repair or replacement  "
                    "4) Ship prepaid return label  "
                    "5) Send replacement unit"
                ),
            },
        )

        # Canonical chain
        g.upsert_edge("CUSTOMER:default", "PRODUCT:laptop", REL_PURCHASED)
        g.upsert_edge("CUSTOMER:default", "PRODUCT:headphones", REL_PURCHASED)
        g.upsert_edge("PRODUCT:laptop", "WARRANTY:laptop-12m", REL_COVERED_BY)
        g.upsert_edge("PRODUCT:headphones", "WARRANTY:headphones-12m", REL_COVERED_BY)
        g.upsert_edge("WARRANTY:laptop-12m", "POLICY:warranty-support", REL_LINKED_TO)
        g.upsert_edge("WARRANTY:headphones-12m", "POLICY:warranty-support", REL_LINKED_TO)
        g.upsert_edge("POLICY:warranty-support", "FAQ:battery-charging", REL_LINKED_TO)
        g.upsert_edge("POLICY:return", "FAQ:returns", REL_LINKED_TO)
        g.upsert_edge("PRODUCT:headphones", "POLICY:return", REL_COVERED_BY)

        # Issue / resolution branch (example query path)
        g.upsert_edge("PRODUCT:laptop", "ISSUE:battery", REL_HAS_ISSUE)
        g.upsert_edge("WARRANTY:laptop-12m", "ISSUE:battery", REL_COVERS)
        g.upsert_edge("ISSUE:battery", "POLICY:warranty-support", REL_GOVERNED_BY)
        g.upsert_edge("ISSUE:battery", "PROCESS:replacement", REL_RESOLVED_BY)
        g.upsert_edge("POLICY:warranty-support", "PROCESS:replacement", REL_LINKED_TO)

    def _connect(self) -> bool:
        if self._driver is not None:
            return True
        settings = get_settings()
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            self._driver.verify_connectivity()
            self._sync_seed_to_neo4j()
            logger.info("neo4j_connected", uri=settings.neo4j_uri)
            return True
        except Exception as exc:
            logger.warning("neo4j_unavailable_using_memory_graph", error=str(exc))
            self._driver = None
            return False

    def _sync_seed_to_neo4j(self) -> None:
        if not self._driver:
            return

        def _write(tx: Any) -> None:
            for node in self._memory.nodes.values():
                tx.run(
                    """
                    MERGE (n:Entity {id: $id})
                    SET n.label = $label, n.name = $name,
                        n.aliases = $aliases, n.sku = $sku
                    """,
                    id=node["id"],
                    label=node.get("label"),
                    name=node.get("name"),
                    aliases=node.get("aliases"),
                    sku=node.get("sku"),
                )
            for edge in self._memory.edges:
                tx.run(
                    """
                    MATCH (a:Entity {id: $source})
                    MATCH (b:Entity {id: $target})
                    MERGE (a)-[r:REL {type: $type}]->(b)
                    """,
                    source=edge["source"],
                    target=edge["target"],
                    type=edge["type"],
                )

        try:
            with self._driver.session() as session:
                session.execute_write(_write)
        except Exception as exc:
            logger.warning("neo4j_seed_failed", error=str(exc))

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        entities: list[dict[str, str]] = []
        seen: set[str] = set()
        for label, pattern in ENTITY_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                # Normalize battery mention to issue, laptop to product
                if label == "PRODUCT" and value.lower() == "battery":
                    continue
                if label == "ISSUE":
                    node_id = "ISSUE:battery"
                    name = "Battery Issue"
                elif label == "PRODUCT" and value.lower() in {"laptop", "notebook"}:
                    node_id = "PRODUCT:laptop"
                    name = "Laptop"
                elif label == "WARRANTY":
                    node_id = "WARRANTY:laptop-12m"
                    name = "Warranty"
                else:
                    node_id = f"{label}:{value.lower()}"
                    name = value
                if node_id in seen:
                    continue
                seen.add(node_id)
                entities.append({"id": node_id, "label": label, "name": name})
        # Always include Customer anchor for support queries
        if entities and "CUSTOMER:default" not in seen:
            entities.insert(
                0, {"id": "CUSTOMER:default", "label": "Customer", "name": "Customer"}
            )
        return entities

    def extract_relationships(
        self, text: str, entities: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        rels: list[dict[str, str]] = []
        lower = text.lower()
        ids = {e["label"]: e["id"] for e in entities}
        if "refund" in lower or "return" in lower:
            if "ORDER" in ids:
                rels.append(
                    {
                        "source": ids["ORDER"],
                        "target": "POLICY:return",
                        "type": "REQUESTS_REFUND_UNDER",
                    }
                )
        if any(w in lower for w in ("battery", "charging", "warranty", "laptop")):
            if "PRODUCT" in ids or "ISSUE" in ids:
                rels.append(
                    {
                        "source": ids.get("PRODUCT", "PRODUCT:laptop"),
                        "target": ids.get("WARRANTY", "WARRANTY:laptop-12m"),
                        "type": REL_COVERED_BY,
                    }
                )
                rels.append(
                    {
                        "source": ids.get("ISSUE", "ISSUE:battery"),
                        "target": "PROCESS:replacement",
                        "type": REL_RESOLVED_BY,
                    }
                )
        return rels

    def _parse_months(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*months?", text, re.I)
        if match:
            return int(match.group(1))
        return None

    def discover_path(
        self,
        query: str,
        *,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        """
        GraphRAG discovery for support questions.

        Example query:
          "My laptop battery stopped charging after 7 months."

        Discovers:
          Customer → Laptop → Warranty → Battery Issue → Policy → Replacement Process
        """
        lower = query.lower()
        months = self._parse_months(query)
        customer_node = "CUSTOMER:default"
        if customer_id:
            cid = f"CUSTOMER:{customer_id}"
            self._memory.upsert_node(cid, "Customer", {"name": customer_id})
            # Link customer to known products if not present
            if not any(
                e["source"] == cid and e["type"] == REL_PURCHASED
                for e in self._memory.edges
            ):
                self._memory.upsert_edge(cid, "PRODUCT:laptop", REL_PURCHASED)
            customer_node = cid

        # Prefer the battery/laptop warranty discovery path
        is_battery_case = any(
            w in lower for w in ("battery", "charging", "charge")
        ) and any(w in lower for w in ("laptop", "notebook", "computer", "battery"))

        if is_battery_case or ("laptop" in lower and "warranty" in lower):
            hop_ids = [
                customer_node,
                "PRODUCT:laptop",
                "WARRANTY:laptop-12m",
                "ISSUE:battery",
                "POLICY:warranty-support",
                "PROCESS:replacement",
            ]
            labels = [
                "Customer",
                "Laptop",
                "Warranty",
                "Battery Issue",
                "Policy",
                "Replacement Process",
            ]
        elif "return" in lower or "refund" in lower:
            hop_ids = [
                customer_node,
                "PRODUCT:headphones",
                "POLICY:return",
                "FAQ:returns",
            ]
            labels = ["Customer", "Product", "Support Policy", "FAQ"]
        else:
            # Generic: Customer → Product → Warranty → Policy → FAQ
            product = "PRODUCT:laptop" if "laptop" in lower else "PRODUCT:headphones"
            warranty = (
                "WARRANTY:laptop-12m"
                if product.endswith("laptop")
                else "WARRANTY:headphones-12m"
            )
            hop_ids = [
                customer_node,
                product,
                warranty,
                "POLICY:warranty-support",
                "FAQ:battery-charging",
            ]
            labels = ["Customer", "Product", "Warranty", "Support Policy", "FAQ"]

        path_nodes: list[dict[str, Any]] = []
        for node_id, short in zip(hop_ids, labels, strict=False):
            node = self._memory.nodes.get(node_id) or {
                "id": node_id,
                "label": short,
                "name": short,
            }
            path_nodes.append(
                {
                    "id": node_id,
                    "label": node.get("label") or short,
                    "name": node.get("name") or short,
                    "display": short,
                }
            )

        in_warranty = None
        warranty_months = 12
        if months is not None:
            in_warranty = months <= warranty_months

        discovery_chain = " → ".join(labels)
        guidance = []
        if in_warranty is True:
            guidance.append(
                f"Purchase age ({months} months) is within the {warranty_months}-month warranty."
            )
            guidance.append(
                "Policy points to the Replacement Process for a covered battery fault."
            )
        elif in_warranty is False:
            guidance.append(
                f"Purchase age ({months} months) may be outside the {warranty_months}-month warranty."
            )
            guidance.append("Confirm purchase date, then offer paid repair or replacement options.")
        else:
            guidance.append("Confirm purchase date against the warranty window.")

        faq = self._memory.nodes.get("FAQ:battery-charging") or {}
        process = self._memory.nodes.get("PROCESS:replacement") or {}
        if faq.get("answer"):
            guidance.append(faq["answer"])
        if process.get("steps"):
            guidance.append(f"Replacement steps: {process['steps']}")

        return {
            "query": query,
            "discovery_path": labels,
            "discovery_chain": discovery_chain,
            "nodes": path_nodes,
            "months_since_purchase": months,
            "in_warranty": in_warranty,
            "guidance": guidance,
            "schema": [
                "Customer",
                "Purchased",
                "Product",
                "Covered by",
                "Warranty",
                "Linked to",
                "Support Policy",
                "Linked to",
                "FAQ",
            ],
        }

    async def ingest_text(self, text: str, *, source: str = "chat") -> dict[str, Any]:
        entities = self.extract_entities(text)
        relationships = self.extract_relationships(text, entities)
        for ent in entities:
            self._memory.upsert_node(
                ent["id"], ent["label"], {"name": ent["name"], "source": source}
            )
        for rel in relationships:
            self._memory.upsert_edge(rel["source"], rel["target"], rel["type"])

        if self._connect() and self._driver:

            def _write(tx: Any) -> None:
                for ent in entities:
                    tx.run(
                        "MERGE (n:Entity {id: $id}) SET n.label=$label, n.name=$name, n.source=$source",
                        id=ent["id"],
                        label=ent["label"],
                        name=ent["name"],
                        source=source,
                    )
                for rel in relationships:
                    tx.run(
                        """
                        MERGE (a:Entity {id: $source})
                        MERGE (b:Entity {id: $target})
                        MERGE (a)-[r:REL {type: $type}]->(b)
                        """,
                        source=rel["source"],
                        target=rel["target"],
                        type=rel["type"],
                    )

            with self._driver.session() as session:
                session.execute_write(_write)

        return {"entities": entities, "relationships": relationships}

    async def hybrid_retrieve(
        self,
        query: str,
        *,
        vector_citations: list[dict[str, Any]] | None = None,
        top_k: int = 5,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        entities = self.extract_entities(query)
        discovery = self.discover_path(query, customer_id=customer_id)
        graph_hits = [n for n in discovery.get("nodes") or []]
        # Enrich with fuzzy related nodes
        related = self._memory.related(query, limit=top_k)
        for node in related:
            if node["id"] not in {h["id"] for h in graph_hits}:
                graph_hits.append(node)

        if self._connect() and self._driver:

            def _read(tx: Any) -> list[dict[str, Any]]:
                result = tx.run(
                    """
                    MATCH (n:Entity)
                    WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($q)
                       OR toLower(n.id) CONTAINS toLower($q)
                       OR toLower(coalesce(n.aliases, '')) CONTAINS toLower($q)
                    RETURN n.id AS id, n.label AS label, n.name AS name
                    LIMIT $limit
                    """,
                    q=query.split()[0] if query.split() else query,
                    limit=top_k,
                )
                return [dict(r) for r in result]

            try:
                with self._driver.session() as session:
                    neo_hits = session.execute_read(_read) or []
                    for hit in neo_hits:
                        if hit.get("id") not in {h.get("id") for h in graph_hits}:
                            graph_hits.append(hit)
            except Exception as exc:
                logger.warning("neo4j_query_failed", error=str(exc))

        return {
            "entities": entities,
            "graph_nodes": graph_hits[: max(top_k, len(discovery.get("nodes") or []))],
            "discovery_path": discovery.get("discovery_path") or [],
            "discovery_chain": discovery.get("discovery_chain") or "",
            "discovery": discovery,
            "vector_citations": vector_citations or [],
            "summary": self._summarize(
                entities, graph_hits, vector_citations or [], discovery
            ),
        }

    def _summarize(
        self,
        entities: list[dict[str, str]],
        graph_nodes: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        discovery: dict[str, Any] | None = None,
    ) -> str:
        parts: list[str] = []
        if discovery and discovery.get("discovery_chain"):
            parts.append(f"GraphRAG discovers: {discovery['discovery_chain']}")
            for tip in discovery.get("guidance") or []:
                parts.append(tip)
        elif entities:
            parts.append(
                "Entities: " + ", ".join(f"{e['label']}:{e['name']}" for e in entities)
            )
        if graph_nodes and not (discovery and discovery.get("discovery_chain")):
            parts.append(
                "Graph: "
                + ", ".join(str(n.get("name") or n.get("id")) for n in graph_nodes[:5])
            )
        if citations:
            parts.append(
                "Docs: "
                + "; ".join(
                    (c.get("excerpt") or c.get("source") or "")[:120] for c in citations[:2]
                )
            )
        return " | ".join(parts) if parts else "No graph context found."


graph_rag_service = GraphRAGService()
