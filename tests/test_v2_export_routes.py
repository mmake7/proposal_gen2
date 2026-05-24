"""Flask v2 export 라우트 (Excel/Markdown/JSON) 단위 테스트.

LLM 호출 없이 모듈 전역 _last_v2_result에 mock 결과를 직접 주입.
"""

from __future__ import annotations

import json

import pytest

import app as app_module
from services_v2.results.rfp_analysis import (
    Overview, Requirement, RfpAnalysisResult, RfpClassification,
    ScoringItem, ValidationReport,
)


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def reset_v2_state():
    """각 테스트 전후로 모듈 전역 상태 초기화."""
    app_module._last_v2_result = None
    app_module._last_v2_filename = ''
    yield
    app_module._last_v2_result = None
    app_module._last_v2_filename = ''


def make_sample_result() -> RfpAnalysisResult:
    return RfpAnalysisResult(
        overview=Overview(
            project_name='테스트사업', organization='테스트기관',
            budget='500', budget_unit='백만원',
        ),
        requirements=[
            Requirement(id='SFR-001', name='로그인', category='기능 요구사항'),
        ],
        scoring=[ScoringItem(item='이해도', score=100)],
        classification=RfpClassification(org_type='중앙부처'),
        validation=ValidationReport(confidence=0.85, issues=[]),
    )


# ── 분석 결과 없을 때 (404) ─────────────────────────────────

class TestNotAnalyzedYet:
    def test_excel_404_when_no_result(self, client, reset_v2_state):
        r = client.get('/api/v2/export/excel')
        assert r.status_code == 404
        assert 'v2 분석 결과 없음' in r.get_json()['error']

    def test_markdown_404_when_no_result(self, client, reset_v2_state):
        r = client.get('/api/v2/export/markdown')
        assert r.status_code == 404

    def test_json_404_when_no_result(self, client, reset_v2_state):
        r = client.get('/api/v2/export/json')
        assert r.status_code == 404


# ── 분석 결과 있을 때 (200) ─────────────────────────────────

class TestExports:
    def setup_method(self):
        app_module._last_v2_result = make_sample_result()
        app_module._last_v2_filename = '테스트.hwpx'

    def teardown_method(self):
        app_module._last_v2_result = None
        app_module._last_v2_filename = ''

    def test_excel_returns_xlsx(self, client):
        r = client.get('/api/v2/export/excel')
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        # XLSX는 ZIP 포맷 시그니처 PK
        assert r.data[:2] == b'PK'
        assert len(r.data) > 1000

    def test_excel_download_name(self, client):
        r = client.get('/api/v2/export/excel')
        disp = r.headers.get('Content-Disposition', '')
        assert '.xlsx' in disp
        # 사업명이 포함되어야 함
        assert '테스트사업' in disp or '%ED' in disp  # URL-인코딩 가능

    def test_markdown_returns_md(self, client):
        r = client.get('/api/v2/export/markdown')
        assert r.status_code == 200
        assert 'markdown' in r.content_type
        body = r.data.decode('utf-8')
        assert body.startswith('# 테스트.hwpx')
        assert '## 사업 개요' in body

    def test_json_returns_full_dict(self, client):
        r = client.get('/api/v2/export/json')
        assert r.status_code == 200
        assert 'json' in r.content_type
        data = json.loads(r.data.decode('utf-8'))
        # v1 호환 키
        assert 'overview' in data
        assert 'requirements' in data
        # v2 메타 키
        assert '_classification' in data
        assert '_validation' in data
        # 데이터 검증
        assert data['overview']['project_name'] == '테스트사업'
        assert data['requirements'][0]['id'] == 'SFR-001'


# ── 폴백 파일명 (overview 없을 때) ─────────────────────────

class TestFilenameFallback:
    def test_uses_filename_when_no_project_name(self, client):
        # project_name 비어있음
        result = RfpAnalysisResult(overview=Overview(project_name=''))
        app_module._last_v2_result = result
        app_module._last_v2_filename = 'fallback.hwpx'
        try:
            r = client.get('/api/v2/export/json')
            assert r.status_code == 200
            disp = r.headers.get('Content-Disposition', '')
            assert 'fallback' in disp or '%' in disp
        finally:
            app_module._last_v2_result = None
            app_module._last_v2_filename = ''
