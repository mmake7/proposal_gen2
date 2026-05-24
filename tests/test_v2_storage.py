"""분석 결과 저장/조회/요약 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services_v2.results.rfp_analysis import (
    Overview, Requirement, RfpAnalysisResult, RfpClassification,
    ScoringItem, ValidationReport,
)
from services_v2.results.storage import (
    list_analyses, load_summary, save_result, summarize_gallery,
)


def make_result(
    *,
    project='테스트사업', org_type='중앙부처',
    req_format='table', confidence=0.85,
    req_count=10, score_count=20, score_total=100,
):
    return RfpAnalysisResult(
        overview=Overview(project_name=project),
        requirements=[
            Requirement(id=f'FR-{i:03d}', name=f'req{i}')
            for i in range(req_count)
        ],
        scoring=[
            ScoringItem(item=f'item{i}', score=score_total // score_count)
            for i in range(score_count)
        ],
        classification=RfpClassification(
            org_type=org_type, req_format=req_format,
        ),
        validation=ValidationReport(confidence=confidence, issues=[]),
    )


# ── save_result ─────────────────────────────────────────

class TestSaveResult:
    def test_creates_json_file(self, tmp_path: Path):
        result = make_result()
        path = save_result(result, '테스트.hwpx', base_dir=tmp_path)
        assert path.exists()
        assert path.suffix == '.json'
        assert '테스트' in path.name

    def test_filename_sanitized(self, tmp_path: Path):
        result = make_result()
        # 특수문자/공백 포함 파일명
        path = save_result(result, '제안요청서 (2).hwpx', base_dir=tmp_path)
        # 파일이 만들어지고 읽을 수 있어야 함
        assert path.exists()
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['meta']['filename'] == '제안요청서 (2).hwpx'

    def test_meta_contains_summary_fields(self, tmp_path: Path):
        # score_count * (score_total // score_count) = 실제 합계
        # score_count=20, score_total=100 → 5×20 = 100
        result = make_result(req_count=33, score_count=20, score_total=100,
                            confidence=0.92)
        path = save_result(result, 'x.hwpx', base_dir=tmp_path)
        meta = json.loads(path.read_text(encoding='utf-8'))['meta']
        assert meta['confidence'] == 0.92
        assert meta['requirements_count'] == 33
        assert meta['scoring_total'] == 100
        assert meta['classification']['org_type'] == '중앙부처'

    def test_full_result_round_trip(self, tmp_path: Path):
        result = make_result(req_count=2)
        path = save_result(result, 'rt.hwpx', base_dir=tmp_path)
        data = json.loads(path.read_text(encoding='utf-8'))
        assert 'result' in data
        assert len(data['result']['requirements']) == 2


# ── list_analyses / load_summary ─────────────────────

class TestListAndSummary:
    def test_list_empty_dir(self, tmp_path: Path):
        assert list_analyses(base_dir=tmp_path) == []

    def test_list_returns_newest_first(self, tmp_path: Path):
        # 두 결과 저장
        save_result(make_result(project='첫번째'), 'a.hwpx', base_dir=tmp_path)
        import time
        time.sleep(1.1)  # timestamp 다르게
        save_result(make_result(project='두번째'), 'b.hwpx', base_dir=tmp_path)
        paths = list_analyses(base_dir=tmp_path)
        assert len(paths) == 2
        # 최신순 (두번째가 첫번째 항목)
        first_meta = load_summary(paths[0])
        assert first_meta['filename'] == 'b.hwpx'

    def test_load_summary(self, tmp_path: Path):
        save_result(make_result(req_count=5), 'x.hwpx', base_dir=tmp_path)
        paths = list_analyses(base_dir=tmp_path)
        meta = load_summary(paths[0])
        assert meta['requirements_count'] == 5


# ── summarize_gallery ───────────────────────────────

class TestSummarizeGallery:
    def test_empty_gallery(self, tmp_path: Path):
        result = summarize_gallery(base_dir=tmp_path)
        assert result['total'] == 0

    def test_aggregates_multiple_results(self, tmp_path: Path):
        import time
        save_result(make_result(org_type='중앙부처', req_format='table',
                                confidence=0.9, req_count=50),
                    'a.hwpx', base_dir=tmp_path)
        time.sleep(1.1)
        save_result(make_result(org_type='중앙부처', req_format='table',
                                confidence=0.8, req_count=30),
                    'b.hwpx', base_dir=tmp_path)
        time.sleep(1.1)
        save_result(make_result(org_type='지자체', req_format='narrative',
                                confidence=0.5, req_count=10),
                    'c.hwpx', base_dir=tmp_path)
        summary = summarize_gallery(base_dir=tmp_path)
        assert summary['total'] == 3
        assert summary['by_org_type']['중앙부처'] == 2
        assert summary['by_org_type']['지자체'] == 1
        assert summary['by_req_format']['table'] == 2
        assert summary['by_req_format']['narrative'] == 1
        assert 0.7 < summary['avg_confidence'] < 0.8
        assert summary['avg_requirements'] == 30  # (50+30+10)/3
        # confidence < 0.7 케이스
        assert 'c.hwpx' in summary['low_confidence_files']


# ── auto_save_enabled ─────────────────────────────

def test_auto_save_disabled_by_default(monkeypatch):
    monkeypatch.delenv('V2_AUTO_SAVE', raising=False)
    from services_v2.results.storage import auto_save_enabled
    assert auto_save_enabled() is False

@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', 'yes', 'Yes'])
def test_auto_save_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv('V2_AUTO_SAVE', value)
    from services_v2.results.storage import auto_save_enabled
    assert auto_save_enabled() is True

@pytest.mark.parametrize('value', ['0', 'false', '', 'no'])
def test_auto_save_disabled_falsy(monkeypatch, value):
    monkeypatch.setenv('V2_AUTO_SAVE', value)
    from services_v2.results.storage import auto_save_enabled
    assert auto_save_enabled() is False
