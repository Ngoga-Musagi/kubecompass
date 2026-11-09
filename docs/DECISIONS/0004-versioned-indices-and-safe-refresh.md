# 0004 Versioned indices, alias swap and refusal of suspicious refreshes

Status: accepted

**Decision.** Each ingestion writes new `conference_<kind>__<conf>__<version>` indices and swaps
read aliases atomically after all bulk loads succeed; the previous version is kept for rollback.
Payloads failing schema validation, with < 10 sessions, or dropping > 30% of sessions are rejected
(`--force` overrides the drop rule). The disk snapshot is updated only after indexing succeeds.

**Consequences.** A bad refresh can never blank the product; status reports `rejected`/`failed`
with the last successful version still served.
