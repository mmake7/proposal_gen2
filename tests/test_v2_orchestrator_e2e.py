"""v2 orchestrator 결합(E2E) 테스트.

페이크 에이전트를 orchestrator 모듈에 주입해 LLM/네트워크 없이
봉합부 로직을 검증한다: 병렬 실행(_safe_get) → 검증 → 재시도(_retry)
→ synthesize(_collect_trace) → 견적(estimation) 연결.

(개별 에이전트 단위 테스트는 별도 파일에 있음. 여기서는 '조립'만 본다.)
"""

import types

import pytest

import services_v2.orchestrator as orch
from services_v2.results.rfp_analysis import (
    Overview, Requirement, ScoringItem, TocItem,
    RfpClassification, ValidationReport,
)

_AGENT_NAMES = [
    'ClassifierAgent', 'OverviewAgent', 'RequirementsCoordinator',
    'ScoringAgent', 'TocAgent', 'ValidatorAgent',
]


def _fake_doc(filename='test.pdf'):
    # orchestrator는 doc를 에이전트에 넘기고 doc.filename만 직접 사용한다.
    return types.SimpleNamespace(
        filename=filename, full_text='RFP 본문', pages=[], table_regions=[],
    )


def _make_fakes(validator_seq, *, overview_first=None):
    """페이크 에이전트 6종 + 호출 로그를 만든다.

    validator_seq: validate() 호출 순서대로 반환할 (confidence, retry_targets).
    overview_first: 지정 시 overview.extract 첫 호출이 이 값을 반환(재시도 분기 테스트용).
    """
    log: list[str] = []

    class FakeClassifier:
        def __init__(self, *a, **k):
            self.calls = []

        def classify(self, doc):
            log.append('classify')
            return RfpClassification(
                req_format='table', scoring_format='table',
                toc_location='back', notes='fake',
            )

    class FakeOverview:
        def __init__(self, *a, **k):
            self.calls = []

        def extract(self, doc, notes):
            log.append('overview')
            if overview_first is not None and log.count('overview') == 1:
                return overview_first
            return Overview(
                project_name='페이크 사업', organization='페이크 기관',
                period='2026.04 ~ 2026.12', budget='500',
            )

    class FakeReq:
        def __init__(self, *a, **k):
            self.calls = []

        def extract(self, doc, classification):
            log.append('requirements')
            return [Requirement(id='FR-001', name='로그인', category='기능', level='필수')]

    class FakeScoring:
        def __init__(self, *a, **k):
            self.calls = []

        def extract(self, doc, scoring_format):
            log.append('scoring')
            return [ScoringItem(category='기술', item='아키텍처', criteria='확장성', score=100)]

    class FakeToc:
        def __init__(self, *a, **k):
            self.calls = []

        def extract(self, doc, toc_location):
            log.append('toc')
            return [TocItem(level=1, number='I.', title='사업 이해')]

    class FakeValidator:
        def __init__(self, *a, **k):
            self.calls = []
            self.i = 0

        def validate(self, *, overview, requirements, scoring, toc):
            log.append('validate')
            conf, targets = validator_seq[min(self.i, len(validator_seq) - 1)]
            self.i += 1
            return ValidationReport(confidence=conf, retry_targets=list(targets))

    fakes = (FakeClassifier, FakeOverview, FakeReq, FakeScoring, FakeToc, FakeValidator)
    return fakes, log


def _inject(monkeypatch, fakes):
    for name, fake in zip(_AGENT_NAMES, fakes):
        monkeypatch.setattr(orch, name, fake)
    # fingerprint 자동학습은 data/analyses에 파일을 쓰므로 테스트에서 무력화
    monkeypatch.setattr(
        'services_v2.results.fingerprints.update_library',
        lambda *a, **k: None,
    )


def test_pipeline_happy_path(monkeypatch):
    """고신뢰 결과 → 재시도 없이 일관된 RfpAnalysisResult 조립."""
    fakes, log = _make_fakes(validator_seq=[(0.9, [])])
    _inject(monkeypatch, fakes)

    result = orch.analyze_rfp_document(_fake_doc())

    assert result.overview.project_name == '페이크 사업'
    assert [r.id for r in result.requirements] == ['FR-001']
    assert sum(s.score for s in result.scoring) == 100
    assert [t.title for t in result.toc] == ['사업 이해']
    assert result.classification.req_format == 'table'
    assert result.validation.confidence == 0.9
    # 견적 휴리스틱 연결 확인 (LLM 없이 결정적 산정)
    assert result.estimation is not None
    assert result.estimation.project_months > 0
    # 재시도 없음 → 각 전문가 1회, validate 1회
    assert log.count('validate') == 1
    assert log.count('scoring') == 1

    # v1 호환 + v2 메타 키 모두 직렬화되는지
    d = result.to_dict()
    for key in ('overview', 'requirements', 'scoring', 'toc',
                '_classification', '_validation', '_estimation', '_agent_trace'):
        assert key in d


def test_pipeline_retries_on_low_confidence(monkeypatch):
    """confidence<0.7 + retry_targets → 해당 대상만 재실행 후 재검증."""
    fakes, log = _make_fakes(validator_seq=[(0.5, ['scoring']), (0.85, [])])
    _inject(monkeypatch, fakes)

    result = orch.analyze_rfp_document(_fake_doc())

    # validate 2회(초기+재검증), scoring 2회(초기+재시도), 비대상은 1회
    assert log.count('validate') == 2
    assert log.count('scoring') == 2
    assert log.count('overview') == 1
    assert result.validation.confidence == 0.85


def test_pipeline_retries_on_critical_empty_overview(monkeypatch):
    """overview가 비면(critical) confidence와 무관하게 재시도."""
    empty_overview = Overview()  # project_name 빈 값 → critical_empty
    fakes, log = _make_fakes(
        validator_seq=[(0.95, []), (0.95, [])],  # confidence는 높지만
        overview_first=empty_overview,           # 첫 overview가 비어 재시도 유발
    )
    _inject(monkeypatch, fakes)

    result = orch.analyze_rfp_document(_fake_doc())

    assert log.count('overview') == 2          # 재시도로 2회
    assert result.overview.project_name == '페이크 사업'  # 2번째(정상) 결과 채택
