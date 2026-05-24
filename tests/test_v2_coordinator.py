"""RequirementsCoordinator 단위 테스트.

NarrativeRequirementAgent를 가짜로 갈아끼워 LLM 호출 없이 분기·폴백·머지 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from services_v2.agents.requirements.coordinator import (
    MIN_AVG_FILLED, MIN_TABLE_REQS, RequirementsCoordinator,
)
from services_v2.documents.rfp_document import RfpDocument, TableRegion
from services_v2.results.rfp_analysis import (
    Requirement, RfpClassification,
)


class FakeNarrativeAgent:
    """NarrativeRequirementAgent 대체 — extract 호출을 기록."""

    def __init__(self, return_value: list[Requirement] | None = None):
        self.calls = []
        self.invocations: list[dict[str, Any]] = []
        self._return = return_value or []

    def extract(self, doc, *, existing_reqs=None, existing_ids=None,
                classification=None, language_dialect=''):
        ids = (existing_ids or set()) | {
            r.id for r in (existing_reqs or []) if r.id
        }
        self.invocations.append({
            'existing_ids': ids,
            'existing_reqs': list(existing_reqs or []),
            'classification': classification,
            'language_dialect': language_dialect,
        })
        return list(self._return)


@pytest.fixture
def coordinator():
    coord = RequirementsCoordinator()
    return coord


def make_doc(*tables: TableRegion) -> RfpDocument:
    return RfpDocument(
        filename='unit.pdf', full_text='', pages=[], table_regions=list(tables),
    )


def req(id: str = '', name: str = '', filled_extras: int = 0) -> Requirement:
    """테스트용 Requirement 빌더 — filled_extras 만큼 임의 필드 채움."""
    r = Requirement(id=id, name=name, parse_method='narrative')
    extras = ('category', 'definition', 'detail', 'output_info',
              'related_reqs', 'source')
    for i in range(filled_extras):
        if i < len(extras):
            setattr(r, extras[i], f'value_{extras[i]}')
    return r


def rich_table(*ids: str) -> TableRegion:
    """세로형 표를 풍부도 4로 만들어 ids개수만큼 (각 표 하나씩) 반환은 불가.
    대신 가로형으로 한 표에 여러 행."""
    rows = [['요구사항 고유번호', '요구사항 명칭', '정의', '세부내용']]
    for i, rid in enumerate(ids):
        rows.append([rid, f'name_{rid}', f'def_{rid}', f'detail_{rid}'])
    return TableRegion(page_number=1, rows=rows)


# ── 분기: req_format 'table' (충분한 표 결과) ──────────────

def test_table_format_skips_narrative_when_rich(coordinator):
    """req_format='table' + 표 결과 풍부 → narrative 호출 안 함."""
    fake = FakeNarrativeAgent()
    coordinator._narrative = fake

    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003', 'FR-004',
                              'FR-005', 'FR-006'))
    cls = RfpClassification(req_format='table')

    result = coordinator.extract(doc, cls)

    assert len(result) == 6
    assert fake.invocations == [], 'narrative 호출되면 안 됨'


def test_table_format_falls_back_when_thin(coordinator):
    """req_format='table'이어도 표 결과가 MIN_TABLE_REQS 미만이면 narrative 폴백."""
    fake = FakeNarrativeAgent(return_value=[req('FR-100', 'narrated', 2)])
    coordinator._narrative = fake

    # 표 결과 3건만 (< MIN_TABLE_REQS=5)
    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003'))
    cls = RfpClassification(req_format='table')

    result = coordinator.extract(doc, cls)

    assert len(fake.invocations) == 1, 'narrative 폴백 호출 필요'
    # existing_ids에 표 ID 전달
    assert fake.invocations[0]['existing_ids'] == {'FR-001', 'FR-002', 'FR-003'}
    # 결과는 표 3건 + narrative 1건 = 4건
    assert {r.id for r in result} == {'FR-001', 'FR-002', 'FR-003', 'FR-100'}


def test_table_format_falls_back_when_low_richness(coordinator):
    """건수는 많지만 풍부도가 MIN_AVG_FILLED 미만 → 폴백."""
    fake = FakeNarrativeAgent()
    coordinator._narrative = fake

    # 5건이지만 filled가 1 (name만 채움) — avg < 1.5
    poor_table = TableRegion(page_number=1, rows=[
        ['요구사항 고유번호', '요구사항 명칭'],  # 2 필드만 매핑
        ['FR-001', 'a'], ['FR-002', 'b'], ['FR-003', 'c'],
        ['FR-004', 'd'], ['FR-005', 'e'],
    ])
    doc = make_doc(poor_table)
    cls = RfpClassification(req_format='table')

    coordinator.extract(doc, cls)
    assert len(fake.invocations) == 1, '풍부도 낮을 때 narrative 폴백 필요'


# ── 분기: req_format 'narrative' / 'mixed' / 미지정 ──────

def test_narrative_format_skips_table(coordinator):
    """req_format='narrative' → 표 파서 호출 안 함, narrative만."""
    fake = FakeNarrativeAgent(return_value=[req('FR-001', 'x', 3)])
    coordinator._narrative = fake

    # 표가 있어도 호출 안 됨
    doc = make_doc(rich_table('FR-XX'))
    cls = RfpClassification(req_format='narrative')

    result = coordinator.extract(doc, cls)

    assert len(fake.invocations) == 1
    # 표 파서 trace에 기록 없음
    table_calls = [c for c in coordinator._own_calls if c.agent == 'table_parser']
    assert table_calls == [], '표 파서가 호출되지 않아야 함'
    assert [r.id for r in result] == ['FR-001']


def test_mixed_format_calls_both(coordinator):
    """req_format='mixed' → 둘 다 호출."""
    fake = FakeNarrativeAgent(return_value=[req('FR-NEW', 'n', 2)])
    coordinator._narrative = fake

    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003',
                              'FR-004', 'FR-005', 'FR-006'))
    cls = RfpClassification(req_format='mixed')

    result = coordinator.extract(doc, cls)

    assert len(fake.invocations) == 1
    assert {r.id for r in result} == {
        'FR-001', 'FR-002', 'FR-003', 'FR-004', 'FR-005', 'FR-006', 'FR-NEW',
    }


def test_no_classification_defaults_to_mixed(coordinator):
    """classification=None → mixed 처럼 동작."""
    fake = FakeNarrativeAgent(return_value=[])
    coordinator._narrative = fake

    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003',
                              'FR-004', 'FR-005', 'FR-006'))

    coordinator.extract(doc, None)
    assert len(fake.invocations) == 1


# ── 머지 ────────────────────────────────────────────────

def test_merge_narrative_fills_table_gaps(coordinator):
    """같은 ID — 표 결과 우선, 빈 필드만 narrative로 보완."""
    fake = FakeNarrativeAgent(return_value=[
        Requirement(id='FR-001', name='narrative_name',
                    detail='narrative_detail',
                    source='narrative_source',
                    parse_method='narrative'),
    ])
    coordinator._narrative = fake

    # 표 결과는 name만 채움, detail/source는 비어있음
    table = TableRegion(page_number=1, rows=[
        ['요구사항 고유번호', '요구사항 명칭'],
        ['FR-001', 'table_name'],
    ])
    doc = make_doc(table)
    cls = RfpClassification(req_format='mixed')

    result = coordinator.extract(doc, cls)
    assert len(result) == 1
    r = result[0]
    assert r.name == 'table_name'  # 표 우선
    assert r.detail == 'narrative_detail'  # 빈 필드 보완
    assert r.source == 'narrative_source'  # 빈 필드 보완
    assert r.parse_method == 'merged'


def test_merge_narrative_adds_new_ids(coordinator):
    """narrative에 새 ID가 있으면 추가."""
    fake = FakeNarrativeAgent(return_value=[
        Requirement(id='FR-NEW', name='only_in_narrative',
                    parse_method='narrative'),
    ])
    coordinator._narrative = fake

    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003',
                              'FR-004', 'FR-005', 'FR-006'))
    cls = RfpClassification(req_format='mixed')

    result = coordinator.extract(doc, cls)
    ids = [r.id for r in result]
    assert ids == ['FR-001', 'FR-002', 'FR-003', 'FR-004', 'FR-005',
                   'FR-006', 'FR-NEW']


# ── trace 기록 ───────────────────────────────────────────

def test_table_parser_recorded_in_calls(coordinator):
    """표 파서 호출이 calls에 기록되어야 함 (LLM 미사용이지만 추적)."""
    fake = FakeNarrativeAgent()
    coordinator._narrative = fake

    doc = make_doc(rich_table('FR-001', 'FR-002', 'FR-003',
                              'FR-004', 'FR-005', 'FR-006'))
    cls = RfpClassification(req_format='table')

    coordinator.extract(doc, cls)

    table_calls = [c for c in coordinator.calls if c.agent == 'table_parser']
    assert len(table_calls) == 1
    assert table_calls[0].model == 'rule-based'
    assert table_calls[0].success is True
    assert table_calls[0].input_chars > 0


def test_narrative_failure_does_not_break(coordinator):
    """narrative parser 실패해도 표 결과는 반환."""

    class FailingNarrative:
        calls = []

        def extract(self, doc, *, existing_reqs=None, existing_ids=None,
                    classification=None, language_dialect=''):
            raise RuntimeError('boom')

    coordinator._narrative = FailingNarrative()

    # 표 결과 빈약 → narrative 폴백 시도
    doc = make_doc(rich_table('FR-001', 'FR-002'))
    cls = RfpClassification(req_format='table')

    # 예외 없이 표 결과만 반환되어야 함
    result = coordinator.extract(doc, cls)
    assert {r.id for r in result} == {'FR-001', 'FR-002'}
