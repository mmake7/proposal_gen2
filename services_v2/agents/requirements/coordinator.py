"""Requirements Coordinator — 표/서술 파서 분기 및 병합.

품질 자동 폴백: 표 결과 건수·풍부도가 낮으면 req_format에 관계없이
narrative parser를 호출해 보완. 분류 오류나 비표준 표 양식에 견고.
"""

from __future__ import annotations

import logging
import time

from services_v2.agents.base import AgentCall
from services_v2.agents.requirements.narrative_parser import NarrativeRequirementAgent
from services_v2.agents.requirements.table_parser import (
    _filled_count, parse_tables,
)
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import Requirement, RfpClassification

logger = logging.getLogger(__name__)


# 폴백 임계값 — 표 결과 신뢰 못 하면 narrative 보강
MIN_TABLE_REQS = 5
MIN_AVG_FILLED = 1.5


class RequirementsCoordinator:
    """Classifier 메타에 따라 표/서술 파서를 분기 호출하고 결과를 병합."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key
        self._model = model
        self._narrative = NarrativeRequirementAgent(api_key=api_key, model=model)
        self._own_calls: list[AgentCall] = []

    @property
    def calls(self) -> list[AgentCall]:
        # 표 파서 + 서술 파서 호출을 합쳐 trace에 노출
        return self._own_calls + self._narrative.calls

    def extract(
        self,
        doc: RfpDocument,
        classification: RfpClassification | None,
    ) -> list[Requirement]:
        req_format = (classification.req_format if classification else 'mixed') or 'mixed'

        table_reqs: list[Requirement] = []
        narrative_reqs: list[Requirement] = []
        table_attempted = False

        if req_format in ('table', 'mixed'):
            table_reqs = self._run_table_parser(doc)
            table_attempted = True

        need_narrative = (
            req_format in ('narrative', 'mixed')
            or not table_attempted
            or _table_quality_low(table_reqs)
        )

        if need_narrative:
            try:
                narrative_reqs = self._narrative.extract(
                    doc,
                    existing_reqs=table_reqs,  # 양식 샘플 전달
                    classification=classification,
                )
                logger.info(
                    'narrative_parser: %d건 추출 (이미 표에 있던 ID 제외)',
                    len(narrative_reqs),
                )
            except Exception as exc:
                logger.warning('narrative_parser 실패 (계속 진행): %s', exc)

        return self._merge(table_reqs, narrative_reqs)

    # ── Internal ──────────────────────────────────────────────
    def _run_table_parser(self, doc: RfpDocument) -> list[Requirement]:
        """표 파서 실행 + trace 기록 (LLM 미사용이지만 호출 기록은 남김)."""
        start = time.time()
        input_chars = sum(len(t.text) for t in doc.table_regions)
        reqs = parse_tables(doc)
        output_chars = sum(len(r.desc or '') for r in reqs)
        self._own_calls.append(AgentCall(
            agent='table_parser',
            model='rule-based',
            duration_ms=int((time.time() - start) * 1000),
            input_chars=input_chars,
            output_chars=output_chars,
            success=True,
        ))
        logger.info('table_parser: %d건 추출 (셀 텍스트 %d자)', len(reqs), input_chars)
        return reqs

    @staticmethod
    def _merge(
        table_reqs: list[Requirement],
        narrative_reqs: list[Requirement],
    ) -> list[Requirement]:
        """표 결과 우선, 서술이 빈 필드를 보완. 같은 ID는 표 결과 유지."""
        by_id: dict[str, Requirement] = {}
        order: list[str] = []

        for req in table_reqs:
            key = req.id or f'_table_{len(order)}'
            by_id[key] = req
            order.append(key)

        for req in narrative_reqs:
            key = req.id or f'_narr_{len(order)}'
            if key in by_id:
                base = by_id[key]
                for attr in ('name', 'category', 'definition', 'detail',
                             'output_info', 'related_reqs', 'source'):
                    if not getattr(base, attr) and getattr(req, attr):
                        setattr(base, attr, getattr(req, attr))
                base.parse_method = 'merged'
                parts = [p for p in (base.definition, base.detail) if p]
                base.desc = '\n'.join(parts)
            else:
                by_id[key] = req
                order.append(key)

        return [by_id[k] for k in order]


def _table_quality_low(table_reqs: list[Requirement]) -> bool:
    """표 결과가 narrative 폴백이 필요할 만큼 빈약한지 판단."""
    if len(table_reqs) < MIN_TABLE_REQS:
        return True
    avg_filled = sum(_filled_count(r) for r in table_reqs) / len(table_reqs)
    return avg_filled < MIN_AVG_FILLED
