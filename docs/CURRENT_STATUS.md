# Current Status

Updated: 2026-05-20

## Summary

Knowledge Base Agent has completed Phase 3 "Intelligent Retrieval". All five Phase 3 features are implemented: hot-path prioritization, graph-aware embeddings, temporal graph, advanced context composition (causal chain detection), and cross-language bridging.

## Verified Health

```text
pytest -q
257 passed, 3 dependency warnings
```

The warnings are SWIG/native dependency deprecation warnings; not project logic failures.

## Recommended Snapshot Command

```bash
python -m scripts.cli analyze --repo . --out .kb --skip-ai --with-graph --depth 2 --detect-bridges
python -m scripts.cli validate --kb .kb
```

Expected graph-mode layers:

- `arch`
- `mod`
- `file`
- `mem`
- `feature`

Expected graph files:

- `.kb/graph/nodes.jsonl`
- `.kb/graph/edges.jsonl`
- `.kb/graph/adjacency.json`
- `.kb/graph/features.jsonl`
- `.kb/graph/hotpath.json`
- `.kb/graph/versions/<version_id>/` (temporal snapshots)

## Canonical Runtime Model

```text
Parser output
  -> Symbol graph (+ cross-language bridges)
  -> Materialized KB views + deterministic feature overlay
  -> Hot-path scoring
  -> Graph-aware FAISS index
  -> Intent-planned graph-aware retrieval (+ causal chains)
  -> Temporal versioned snapshots
```

The symbol graph is the source of truth. KB entries are cached views designed for agent retrieval.

## Phase 3 Features

### Hot-Path Prioritization

- Nodes ranked by incoming CALLS edge count, normalized to 0.0–1.0 hotness.
- Hot-path scores persisted to `hotpath.json`.
- Context composition sorts nodes within tiers by hotness descending.
- Deterministic, no LLM needed.

### Graph-Aware Embeddings

- MEM entry embedding text enriched with: calls made, callers, feature membership, hotness score.
- Non-MEM entries keep plain text embeddings.
- Falls back gracefully when graph data is unavailable.
- Activated via `--with-graph` on `index` command, or automatically in `analyze --with-graph`.

### Temporal Graph

- Versioned snapshots saved to `.kb/graph/versions/<version_id>/`.
- Auto-detects git commit hash for version labels.
- `versions` CLI command lists stored versions.
- `diff` CLI command shows node/edge diffs between versions.
- `VERSION_DIFF` query intent for temporal queries.

### Advanced Context Composition

- `CHAIN_TRACE` intent for causal chain queries ("call chain from X to Y").
- `CausalChainDetector` walks CALLS edges to produce ordered execution chains.
- Chains sorted by (length desc, hotness desc).
- ExpandedSubgraph now supports up to 4 hops for chain tracing.
- New "chain" token budget tier in context composition.

### Cross-Language Bridging

- Abstract `LanguageBridge` base class with three strategies:
  - `HttpApiBridge`: C# `[HttpGet]` routes matched against Python `requests.get()` URLs.
  - `DataContractBridge`: Shared DTO class names between languages, boosted by field similarity.
  - `MessageQueueBridge`: Shared topic/channel names in node names/docstrings.
- `BridgeDetector` orchestrates strategies with deduplication.
- New `BRIDGES_TO` edge kind (confidence 0.30–0.75).
- `bridge_metadata` field on SymbolEdge stores protocol and route info.
- Activated via `--detect-bridges` flag on `analyze` command.

## New CLI Commands & Flags

| Command/Flag | Purpose |
|---|---|
| `analyze --detect-bridges` | Enable cross-language bridge detection |
| `analyze --version-id <label>` | Label for temporal snapshot |
| `index --with-graph` | Enrich embeddings with graph context |
| `versions` | List stored graph versions |
| `diff --from-version <v1> --to-version <v2>` | Diff between graph versions |
| `ingest-telemetry <traces.json> --kb .kb` | Map OpenTelemetry spans to graph nodes |
| `update-runtime-metadata --kb .kb` | Aggregate call counts, latency, and error rates from ingested traces |
| `train-ranking-model --kb .kb --min-samples 20` | Train retrieval tuning config from feedback |
| `auto-tune --kb .kb` | Apply saved tuning overrides to graph-aware retrieval |
| `show-tuning-stats --kb .kb` | Show feedback count, useful rate, and active overrides |
| `add-repo /path/to/other/.kb --name other --kb .kb` | Register another repository graph |
| `resolve-cross-repo --kb .kb` | Persist cross-repo references and foreign nodes |
| `update-shared-deps --kb .kb` | Refresh shared dependency references across registered repos |
| `dashboard --kb .kb` | Show graph health and retrieval analytics together |
| `graph-health --kb .kb` | Show graph-only health metrics |
| `query-analytics --kb .kb` | Show retrieval feedback analytics |

## Runtime/Federation Examples

Prerequisites:

- Run `analyze --with-graph` before telemetry, federation, or dashboard commands.
- For federation, pass an external repository `.kb` directory that contains `graph/`.
- Feedback for self-tuning is currently written by runtime or integration code into `.kb/telemetry/feedback.jsonl`; there is no CLI feedback collector yet.

```bash
python -m scripts.cli ingest-telemetry traces.json --kb .kb
python -m scripts.cli update-runtime-metadata --kb .kb
python -m scripts.cli train-ranking-model --kb .kb --min-samples 20
python -m scripts.cli auto-tune --kb .kb
python -m scripts.cli add-repo /path/to/other-project/.kb --name other-project --kb .kb
python -m scripts.cli resolve-cross-repo --kb .kb
python -m scripts.cli dashboard --kb .kb
```

Common fixes:

| Message | Fix |
|---|---|
| `No graph found. Run analyze --with-graph first.` | Rebuild with `analyze --with-graph`. |
| `No traces found. Run ingest-telemetry first.` | Run `ingest-telemetry` before `update-runtime-metadata`. |
| `No tuning config found. Run train-ranking-model first.` | Write feedback to `.kb/telemetry/feedback.jsonl`, then run `train-ranking-model`. |
| External repo is missing graph data | Point `add-repo` at a `.kb` directory with `graph/nodes.jsonl` and `graph/edges.jsonl`. |

## New Enums

| Type | New Values |
|---|---|
| EdgeKind | `BRIDGES_TO` (total: 7) |
| QueryIntent | `CHAIN_TRACE`, `VERSION_DIFF` (total: 7) |

## Next Best Action

Rebuild a clean `.kb/` graph snapshot with all Phase 3 features enabled, validate it, and update snapshot stats.
