"""POST /api/parse 엔드포인트 테스트 (v2 멀티에이전트 정본).

업로드 유효성 검사, v2 라우팅, 응답 형식, 캐시, 인제스트 에러, 에러 핸들러를 검증한다.
(v1 분석 경로는 제거됨 — 모든 분석은 services_v2 파이프라인.)
"""

import io

import pytest
from unittest.mock import patch, MagicMock


def _pdf(content=b'%PDF-1.4 fake', filename='test.pdf'):
    return (io.BytesIO(content), filename)


# ── 파일 유효성 검사 ──────────────────────────────────────────

class TestFileValidation:
    def test_no_file_returns_400(self, client):
        resp = client.post('/api/parse')
        assert resp.status_code == 400
        assert '전송되지 않았습니다' in resp.get_json()['error']

    def test_empty_filename_returns_400(self, client):
        data = {'file': (io.BytesIO(b'x'), '')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        assert '선택되지 않았습니다' in resp.get_json()['error']

    def test_unsupported_extension_returns_415(self, client):
        data = {'file': (io.BytesIO(b'x'), 'document.txt')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 415
        body = resp.get_json()['error']
        assert 'PDF' in body or 'HWPX' in body or 'DOCX' in body

    @pytest.mark.parametrize('name', ['doc.PDF', 'doc.Pdf', 'rfp.hwpx', 'rfp.docx'])
    @patch('app.analyze_rfp_document')
    @patch('app.v2_ingest_bytes')
    def test_supported_extensions_pass_validation(self, MockIngest, MockAnalyze, name, client):
        """지원 확장자(.pdf/.hwpx/.docx, 대소문자 무관)는 v2 경로로 진입해 200."""
        MockIngest.return_value = MagicMock(full_text='x')
        ro = MagicMock()
        ro.to_dict.return_value = {'overview': None, 'requirements': [], 'scoring': [], 'toc': []}
        MockAnalyze.return_value = ro
        resp = client.post('/api/parse', data={'file': _pdf(filename=name)},
                           content_type='multipart/form-data')
        assert resp.status_code == 200


# ── v2 분석 경로 ──────────────────────────────────────────────

class TestV2Analysis:
    @patch('app.analyze_rfp_document')
    @patch('app.v2_ingest_bytes')
    def test_success_response_format(self, MockIngest, MockAnalyze, client):
        """정상 분석 시 프론트 호환 JSON 형식(overview/requirements/scoring/toc)을 반환."""
        doc = MagicMock(); doc.full_text = 'RFP 본문'
        MockIngest.return_value = doc
        result_obj = MagicMock()
        result_obj.to_dict.return_value = {
            'overview': {'project_name': '테스트 사업', 'organization': '기관',
                         'budget': '100', 'budget_unit': '백만원'},
            'requirements': [{'category': '기능', 'id': 'FR-001', 'name': '기능1',
                              'desc': '설명', 'level': '필수'}],
            'scoring': [{'category': '기술', 'item': '아키텍처', 'criteria': '설계', 'score': 100}],
            'toc': [{'level': 1, 'title': '대목차',
                     'children': [{'level': 2, 'title': '소목차', 'children': []}]}],
        }
        MockAnalyze.return_value = result_obj

        resp = client.post('/api/parse', data={'file': _pdf()},
                           content_type='multipart/form-data')
        assert resp.status_code == 200
        body = resp.get_json()
        for k in ('overview', 'requirements', 'scoring', 'toc'):
            assert k in body
        assert body['overview']['project_name'] == '테스트 사업'
        assert body['requirements'][0]['id'] == 'FR-001'
        assert body['scoring'][0]['score'] == 100
        MockIngest.assert_called_once()
        MockAnalyze.assert_called_once()

    @patch('app.analyze_rfp_document')
    @patch('app.v2_ingest_bytes')
    def test_caches_result_for_export(self, MockIngest, MockAnalyze, client):
        import app as app_module
        doc = MagicMock(); doc.full_text = 'x'; MockIngest.return_value = doc
        ro = MagicMock()
        ro.to_dict.return_value = {'overview': {'project_name': '캐시'},
                                   'requirements': [], 'scoring': [], 'toc': []}
        MockAnalyze.return_value = ro

        resp = client.post('/api/parse', data={'file': _pdf()},
                           content_type='multipart/form-data')
        assert resp.status_code == 200
        assert app_module._last_analysis['overview']['project_name'] == '캐시'
        assert app_module._last_v2_result is ro

    @patch('app.analyze_rfp_document')
    @patch('app.v2_ingest_bytes')
    def test_ingest_error_returns_422(self, MockIngest, MockAnalyze, client):
        from services_v2.documents import IngestError
        MockIngest.side_effect = IngestError('손상된 파일')
        resp = client.post('/api/parse', data={'file': _pdf()},
                           content_type='multipart/form-data')
        assert resp.status_code == 422
        MockAnalyze.assert_not_called()

    @patch('app.analyze_rfp_document')
    @patch('app.v2_ingest_bytes')
    def test_orchestrator_error_returns_422(self, MockIngest, MockAnalyze, client):
        from services_v2.orchestrator import OrchestratorError
        MockIngest.return_value = MagicMock(full_text='x')
        MockAnalyze.side_effect = OrchestratorError('파이프라인 실패')
        resp = client.post('/api/parse', data={'file': _pdf()},
                           content_type='multipart/form-data')
        assert resp.status_code == 422


# ── 에러 핸들러 ───────────────────────────────────────────────

@pytest.mark.api
class TestErrorHandlers:
    def test_404_api_endpoint(self, client):
        resp = client.get('/api/nonexistent')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_method_not_allowed_parse(self, client):
        resp = client.get('/api/parse')
        assert resp.status_code == 405
