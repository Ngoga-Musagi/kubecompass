# 0003 NetworkX read model instead of a graph database

Status: accepted

**Context.** ~1.8k nodes / ~9k edges per conference; needs neighborhoods, personalized PageRank, paths.

**Decision.** Persist edges in ES (`conference_relationships`) and build an in-memory NetworkX
graph per conference in the API, reloaded when the ES alias version changes. Callers depend on the
`GraphStore` protocol only.

**Consequences.** No extra infrastructure; PPR runs in ~100 ms. Revisit (Neo4j/Memgraph) when graphs
reach millions of edges or multi-instance writes are needed.
