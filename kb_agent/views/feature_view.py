"""Feature view builder — produces KBEntry objects from feature clusters."""
from __future__ import annotations

import logging

from kb_agent.analyzer.llm import LLMClient
from kb_agent.models.entry import AIData, KBEntry, Layer, StaticData, SymbolKind
from kb_agent.models.graph import SymbolNode
from kb_agent.graph.features import Feature
from kb_agent.views.base import ViewBuilder, ViewIDMapper

logger = logging.getLogger(__name__)


class FeatureViewBuilder(ViewBuilder):
    """Build FEATURE entries from extracted feature clusters."""

    def __init__(self, mapper: ViewIDMapper, llm: LLMClient | None = None) -> None:
        super().__init__(mapper, llm)

    async def build(self, **kwargs) -> list[KBEntry]:
        features: list[Feature] = kwargs.get("features", [])
        nodes: list[SymbolNode] = kwargs.get("nodes", [])
        node_by_id = {n.id: n for n in nodes}

        entries: list[KBEntry] = []
        for feature in features:
            if not feature.member_node_ids:
                continue

            # Collect member signatures for the feature
            member_sigs: list[str] = []
            for nid in feature.member_node_ids:
                node = node_by_id.get(nid) or self._mapper.node_by_id.get(nid)
                if node:
                    member_sigs.append(node.signature or f"{node.kind.value} {node.name}")

            first_node = (
                node_by_id.get(feature.member_node_ids[0])
                or self._mapper.node_by_id.get(feature.member_node_ids[0])
            )
            if first_node is None:
                continue

            entry = KBEntry(
                id=feature.id,
                layer=Layer.FEATURE,
                parent=None,
                children=[],
                static=StaticData(
                    kind=SymbolKind.PACKAGE,
                    language=first_node.language,
                    path="",
                    line_start=0,
                    line_end=0,
                    signature=f"feature {feature.name} ({len(feature.member_node_ids)} symbols, {feature.edge_density} edges)",
                    exports=[nid for nid in feature.member_node_ids],
                    source="feature_overlay",
                ),
                ai=AIData(
                    tags=[feature.naming_basis],
                    confidence=1.0,
                ),
            )
            entries.append(entry)

        return entries
