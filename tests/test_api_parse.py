"""
POST /api/parse 엔드포인트 테스트

PDF 업로드 유효성 검사, 에러 처리, 응답 형식을 검증합니다.
"""

import io
import json
import pytest
from unittest.mock import patch, MagicMock

from services.pdf_extractor import PdfExtractionResult, PageContent, PdfExtractionError
from services.rfp_analyzer import RfpAnalysisResult, RfpOverview, RfpRequirement, RfpScoringItem, RfpTocItem, RfpAnalysisError


def _make_pdf_file(content=b'%PDF-1.4 fake', filename='test.pdf'):
    """테스트용 파일 객체 생성"""
    return (io.BytesIO(content), filename)


# ── 파일 유효성 검사 테스트 ──────────────────────────────────

class TestFileValidation:
    def test_no_file_returns_400(self, client):
        """파일 없이 요청 시 400 에러"""
        resp = client.post('/api/parse')
        assert resp.status_code == 400
        data = resp.get_json()
        assert '전송되지 않았습니다' in data['error']

    def test_empty_filename_returns_400(self, client):
        """빈 파일명으로 요청 시 400 에러"""
        data = {'file': (io.BytesIO(b'test'), '')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        assert '선택되지 않았습니다' in resp.get_json()['error']

    def test_non_supported_file_returns_415(self, client):
        """지원하지 않는 확장자(.txt, .hwp 등) 업로드 시 415 에러.

        v2 통합 후 .pdf/.hwpx/.docx 모두 허용. .hwp/.doc는 변환 후 사용.
        """
        data = {'file': (io.BytesIO(b'test'), 'document.txt')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 415
        # 허용 포맷 또는 변환 안내 포함
        body = resp.get_json()['error']
        assert 'PDF' in body or 'HWPX' in body or 'DOCX' in body


# ── PDF 추출 에러 테스트 ─────────────────────────────────────

class TestPdfExtractionErrors:
    @patch('app.PdfExtractor')
    def test_extraction_error_returns_422(self, MockExtractor, client):
        """PDF 추출 실패 시 422 에러"""
        instance = MockExtractor.return_value
        instance.extract_from_bytes.side_effect = PdfExtractionError('파일 손상')

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 422
        assert '처리할 수 없습니다' in resp.get_json()['error']

    @patch('app.PdfExtractor')
    def test_empty_text_returns_422(self, MockExtractor, client):
        """텍스트가 추출되지 않은 경우 422 에러"""
        instance = MockExtractor.return_value
        instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[],
            full_text='   ',
        )

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 422
        assert '추출할 수 없습니다' in resp.get_json()['error']


# ── AI 분석 에러 테스트 ──────────────────────────────────────

class TestAnalysisErrors:
    @patch('app.RfpAnalyzer')
    @patch('app.PdfExtractor')
    @patch('app.parse_rfp_requirements')
    def test_analysis_error_fallback_to_parser(self, MockParser, MockExtractor, MockAnalyzer, client):
        """AI 분석 실패 시 파서 폴백으로 200 반환"""
        ext_instance = MockExtractor.return_value
        ext_instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[PageContent(page_number=1, text='RFP 내용', extraction_method='text')],
            full_text='RFP 내용',
        )

        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.side_effect = RfpAnalysisError('API 키 오류')

        MockParser.return_value = {
            'summary': [], 'requirements': [], 'requirement_list': [],
            'stats': {'parsed_total': 0, 'completeness_pct': 0},
        }

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200

    @patch('app.RfpAnalyzer')
    @patch('app.PdfExtractor')
    @patch('app.parse_rfp_requirements')
    def test_both_fail_returns_422(self, MockParser, MockExtractor, MockAnalyzer, client):
        """AI 분석과 파서 모두 실패 시 422 에러"""
        ext_instance = MockExtractor.return_value
        ext_instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[PageContent(page_number=1, text='RFP 내용', extraction_method='text')],
            full_text='RFP 내용',
        )

        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.side_effect = RfpAnalysisError('API 키 오류')

        MockParser.side_effect = Exception('파서 실패')

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 422
        assert '모두 실패' in resp.get_json()['error']


# ── 정상 응답 형식 테스트 ────────────────────────────────────

class TestSuccessResponse:
    @patch('app.RfpAnalyzer')
    @patch('app.PdfExtractor')
    def test_success_returns_expected_format(self, MockExtractor, MockAnalyzer, client):
        """정상 분석 시 프론트엔드 호환 JSON 형식을 반환한다"""
        ext_instance = MockExtractor.return_value
        ext_instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='rfp.pdf',
            total_pages=5,
            pages=[PageContent(page_number=1, text='RFP 내용', extraction_method='text')],
            full_text='RFP 내용이 충분히 있습니다.',
        )

        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.return_value = RfpAnalysisResult(
            overview=RfpOverview(
                project_name='테스트 사업',
                organization='테스트 기관',
                budget='100',
            ),
            requirements=[
                RfpRequirement(category='기능', id='FR-001', name='기능1', desc='설명', level='필수'),
            ],
            scoring=[],
            toc=[],
        )

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200

        body = resp.get_json()

        # 프론트엔드 필수 키 존재 확인
        assert 'overview' in body
        assert 'requirements' in body
        assert 'scoring' in body
        assert 'toc' in body

        # overview 필드 확인
        assert body['overview']['project_name'] == '테스트 사업'
        assert body['overview']['organization'] == '테스트 기관'
        assert body['overview']['budget'] == '100'
        assert body['overview']['budget_unit'] == '백만원'

        # requirements 형식 확인
        assert len(body['requirements']) == 1
        req = body['requirements'][0]
        assert req['category'] == '기능'
        assert req['id'] == 'FR-001'
        assert req['name'] == '기능1'
        assert req['level'] == '필수'

    @patch('app.RfpAnalyzer')
    @patch('app.PdfExtractor')
    def test_success_caches_result_for_excel(self, MockExtractor, MockAnalyzer, client):
        """분석 성공 시 결과가 캐시되어 Excel 다운로드가 가능하다"""
        import app as app_module

        ext_instance = MockExtractor.return_value
        ext_instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[PageContent(page_number=1, text='RFP 내용', extraction_method='text')],
            full_text='RFP 내용',
        )

        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.return_value = RfpAnalysisResult(
            overview=RfpOverview(project_name='캐시 테스트'),
            requirements=[],
            scoring=[],
            toc=[],
        )

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200

        # _last_analysis가 설정되었는지 확인
        assert app_module._last_analysis is not None
        assert app_module._last_analysis['overview']['project_name'] == '캐시 테스트'

    @patch('app.RfpAnalyzer')
    @patch('app.PdfExtractor')
    def test_success_response_has_all_scoring_fields(self, MockExtractor, MockAnalyzer, client):
        """배점기준과 목차가 포함된 완전한 응답 형식"""
        ext_instance = MockExtractor.return_value
        ext_instance.extract_from_bytes.return_value = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[PageContent(page_number=1, text='RFP 내용', extraction_method='text')],
            full_text='RFP 내용',
        )

        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.return_value = RfpAnalysisResult(
            overview=RfpOverview(project_name='전체 필드 테스트'),
            requirements=[],
            scoring=[
                RfpScoringItem(category='기술', item='아키텍처', criteria='설계', score=30),
                RfpScoringItem(category='가격', item='가격', criteria='적정성', score=70),
            ],
            toc=[
                RfpTocItem(level=1, title='대목차', children=[
                    RfpTocItem(level=2, title='소목차'),
                ]),
            ],
        )

        data = {'file': _make_pdf_file()}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200

        body = resp.get_json()
        assert len(body['scoring']) == 2
        assert body['scoring'][0]['score'] == 30
        assert body['scoring'][1]['score'] == 70

        assert len(body['toc']) == 1
        assert body['toc'][0]['title'] == '대목차'
        assert len(body['toc'][0]['children']) == 1


# ── 파일 확장자 변형 테스트 ────────────────────────────────

@pytest.mark.api
class TestFileExtensionVariants:
    def test_uppercase_pdf_accepted(self, client):
        """대문자 .PDF 확장자도 허용된다"""
        # 실제 PDF 파싱에서 에러가 발생할 수 있지만, 확장자 검증은 통과해야 함
        data = {'file': (io.BytesIO(b'%PDF-1.4 fake'), 'document.PDF')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        # 415가 아닌 다른 상태코드 (확장자 통과, 파싱에서 실패 가능)
        assert resp.status_code != 415

    def test_mixed_case_pdf_accepted(self, client):
        """혼합 대소문자 .Pdf 확장자도 허용된다"""
        data = {'file': (io.BytesIO(b'%PDF-1.4 fake'), 'document.Pdf')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code != 415

    def test_txt_extension_rejected(self, client):
        """.txt 확장자는 거부된다"""
        data = {'file': (io.BytesIO(b'some text'), 'document.txt')}
        resp = client.post('/api/parse', data=data, content_type='multipart/form-data')
        assert resp.status_code == 415


# ── 에러 핸들러 테스트 ────────────────────────────────────

@pytest.mark.api
class TestErrorHandlers:
    def test_404_api_endpoint(self, client):
        """존재하지 않는 API 엔드포인트 요청 시 JSON 404 응답"""
        resp = client.get('/api/nonexistent')
        assert resp.status_code == 404
        body = resp.get_json()
        assert 'error' in body

    def test_method_not_allowed_parse(self, client):
        """GET /api/parse 요청 시 405 에러"""
        resp = client.get('/api/parse')
        assert resp.status_code == 405
