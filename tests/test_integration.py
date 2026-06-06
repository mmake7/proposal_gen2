"""
통합 테스트 – 샘플 PDF를 활용한 엔드투엔드 흐름 검증

실제 PDF 바이트를 생성하여 다음 흐름을 검증합니다:
  PDF 업로드 → 텍스트 추출 → AI 분석(모킹) → JSON 응답 → Excel 다운로드
"""

import io
import json

import pytest
from openpyxl import load_workbook
from unittest.mock import patch, MagicMock

import app as app_module
from services.pdf_extractor import PdfExtractor
from services.rfp_analyzer import RfpAnalysisResult, RfpOverview, RfpRequirement, RfpScoringItem, RfpTocItem
from tests.conftest import (
    create_rfp_like_pdf,
    create_text_pdf,
    create_empty_pdf,
    SAMPLE_ANALYSIS_RESULT,
    SAMPLE_ANALYSIS_JSON,
)


# ── PDF 추출 → 분석 통합 테스트 ───────────────────────────

@pytest.mark.integration
class TestPdfExtractionToAnalysis:
    """PDF 텍스트 추출 후 분석까지의 통합 흐름"""

    def test_rfp_pdf_text_extraction(self):
        """샘플 RFP PDF에서 텍스트가 올바르게 추출된다"""
        pdf_data = create_rfp_like_pdf()
        extractor = PdfExtractor(enable_ocr=False)
        result = extractor.extract_from_bytes(pdf_data, filename='rfp_sample.pdf')

        assert result.filename == 'rfp_sample.pdf'
        assert result.total_pages == 3
        assert len(result.pages) == 3

        full = result.full_text
        # 핵심 키워드가 추출되었는지 확인
        assert '제안요청서' in full or 'RFP' in full
        assert '스마트시티' in full
        assert '사업' in full

    def test_multi_page_extraction_preserves_order(self):
        """여러 페이지의 텍스트가 순서대로 추출된다"""
        pdf_data = create_text_pdf([
            'First page with enough content to pass the threshold for text extraction test.',
            'Second page with enough content to pass the threshold for text extraction test.',
            'Third page with enough content to pass the threshold for text extraction test.',
        ])
        extractor = PdfExtractor(enable_ocr=False)
        result = extractor.extract_from_bytes(pdf_data)

        pages_text = [p.text for p in result.pages]
        assert 'First page' in pages_text[0]
        assert 'Second page' in pages_text[1]
        assert 'Third page' in pages_text[2]

    def test_extraction_result_summary_fields(self):
        """추출 결과의 summary 필드가 정확하다"""
        pdf_data = create_rfp_like_pdf()
        extractor = PdfExtractor(enable_ocr=False)
        result = extractor.extract_from_bytes(pdf_data)

        summary = result.extraction_summary
        assert summary['total_pages'] == 3
        assert summary['extracted_pages'] == 3
        assert summary['text_pages'] == 3
        assert summary['ocr_pages'] == 0
        assert summary['skipped_pages'] == 0
        assert summary['total_chars'] > 0
        assert summary['ocr_available'] is False

    def test_extracted_text_not_empty_for_rfp(self):
        """RFP PDF에서 추출된 텍스트가 비어있지 않다"""
        pdf_data = create_rfp_like_pdf()
        extractor = PdfExtractor(enable_ocr=False)
        result = extractor.extract_from_bytes(pdf_data)

        assert result.full_text.strip() != ''
        assert len(result.full_text) > 100  # 충분한 텍스트가 있어야 함


# ── API 엔드투엔드 통합 테스트 ─────────────────────────────

@pytest.mark.integration
@pytest.mark.api
class TestApiEndToEnd:
    """PDF 업로드 → 분석 → Excel 다운로드 전체 흐름"""

    @patch('app.parse_rfp_requirements', return_value={'requirements': [], 'stats': {}, 'summary': []})
    @patch('app.RfpAnalyzer')
    def test_upload_rfp_pdf_and_get_analysis(self, MockAnalyzer, MockParser, client):
        """실제 PDF를 업로드하면 분석 결과 JSON을 받는다"""
        # RfpAnalyzer와 파서 모킹 (PdfExtractor는 실제 동작)
        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.return_value = RfpAnalysisResult(
            overview=RfpOverview(
                project_name='스마트시티 통합플랫폼 구축',
                organization='한국정보화진흥원',
                budget='500',
            ),
            requirements=[
                RfpRequirement(category='기능', id='FR-001', name='데이터 수집', desc='IoT 센서 데이터 수집', level='필수'),
            ],
            scoring=[
                RfpScoringItem(category='기술', item='아키텍처', criteria='확장성 설계', score=20),
            ],
            toc=[
                RfpTocItem(level=1, title='사업 이해', children=[
                    RfpTocItem(level=2, title='사업 배경'),
                ]),
            ],
        )

        pdf_data = create_rfp_like_pdf()
        data = {'file': (io.BytesIO(pdf_data), 'rfp_sample.pdf')}
        resp = client.post('/api/parse?engine=v1', data=data, content_type='multipart/form-data')

        assert resp.status_code == 200
        body = resp.get_json()

        # 응답 구조 검증
        assert 'overview' in body
        assert 'requirements' in body
        assert 'scoring' in body
        assert 'toc' in body

        assert body['overview']['project_name'] == '스마트시티 통합플랫폼 구축'
        assert len(body['requirements']) == 1
        assert body['requirements'][0]['id'] == 'FR-001'

        # PdfExtractor에 전달된 텍스트에 핵심 내용이 있는지 확인
        call_args = analyzer_instance.analyze.call_args
        analyzed_text = call_args[0][0]
        assert len(analyzed_text) > 0

    @patch('app.RfpAnalyzer')
    def test_upload_then_download_excel(self, MockAnalyzer, client):
        """PDF 업로드 후 Excel 다운로드까지 전체 흐름 동작"""
        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.return_value = RfpAnalysisResult(
            overview=RfpOverview(project_name='통합 테스트 사업', budget='100'),
            requirements=[
                RfpRequirement(category='기능', id='FR-001', name='기능1', desc='설명', level='필수'),
            ],
            scoring=[
                RfpScoringItem(category='기술', item='항목1', criteria='기준', score=50),
                RfpScoringItem(category='가격', item='항목2', criteria='기준', score=50),
            ],
            toc=[RfpTocItem(level=1, title='사업 이해')],
        )

        # 1단계: PDF 업로드 및 분석
        pdf_data = create_rfp_like_pdf()
        data = {'file': (io.BytesIO(pdf_data), 'test_rfp.pdf')}
        parse_resp = client.post('/api/parse?engine=v1', data=data, content_type='multipart/form-data')
        assert parse_resp.status_code == 200

        # 2단계: Excel 다운로드
        excel_resp = client.get('/api/download/excel')
        assert excel_resp.status_code == 200
        assert excel_resp.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # 3단계: Excel 내용 검증
        wb = load_workbook(io.BytesIO(excel_resp.data))
        assert wb.sheetnames == ['사업개요', '요구사항', '배점기준', '제안목차']

        # 사업개요 시트에 프로젝트명이 있는지 확인
        ws_overview = wb['사업개요']
        values = [ws_overview.cell(row=r, column=2).value for r in range(3, 12)]
        assert '통합 테스트 사업' in values

        # 배점기준 합계 확인
        ws_scoring = wb['배점기준']
        last_row = ws_scoring.max_row
        assert ws_scoring.cell(row=last_row, column=4).value == 100

    @patch('app.RfpAnalyzer')
    def test_empty_pdf_returns_422(self, MockAnalyzer, client):
        """텍스트가 없는 PDF 업로드 시 422 에러를 반환한다"""
        pdf_data = create_empty_pdf(1)
        data = {'file': (io.BytesIO(pdf_data), 'empty.pdf')}
        resp = client.post('/api/parse?engine=v1', data=data, content_type='multipart/form-data')

        assert resp.status_code == 422
        body = resp.get_json()
        assert '추출할 수 없습니다' in body['error']

        # AI 분석이 호출되지 않았는지 확인
        analyzer_instance = MockAnalyzer.return_value
        analyzer_instance.analyze.assert_not_called()

    def test_excel_download_before_parse_returns_404(self, client):
        """분석 전 Excel 다운로드 시 404를 반환한다"""
        resp = client.get('/api/download/excel')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()


# ── PDF 추출 + Excel 출력 통합 테스트 ─────────────────────

@pytest.mark.integration
class TestExtractionToExcel:
    """PDF 추출 결과를 Excel로 변환하는 통합 흐름"""

    def test_analysis_dict_to_excel_roundtrip(self):
        """분석 결과 dict → Excel → 워크북 검증"""
        from services.excel_exporter import export_to_excel

        buf = export_to_excel(SAMPLE_ANALYSIS_RESULT)
        wb = load_workbook(buf)

        # 4개 시트 존재
        assert len(wb.sheetnames) == 4

        # 요구사항 데이터 수 확인 (헤더 + 3 데이터)
        ws_req = wb['요구사항']
        assert ws_req.max_row == 3 + len(SAMPLE_ANALYSIS_RESULT['requirements'])

        # 배점기준 합계 검증
        ws_score = wb['배점기준']
        expected_total = sum(s['score'] for s in SAMPLE_ANALYSIS_RESULT['scoring'])
        last_row = ws_score.max_row
        assert ws_score.cell(row=last_row, column=4).value == expected_total

    def test_empty_analysis_to_excel(self):
        """빈 분석 결과도 Excel로 변환된다"""
        from services.excel_exporter import export_to_excel

        empty_data = {
            'overview': None,
            'requirements': [],
            'scoring': [],
            'toc': [],
        }
        buf = export_to_excel(empty_data)
        wb = load_workbook(buf)
        assert len(wb.sheetnames) == 4

        # 빈 데이터 메시지 확인
        assert wb['사업개요'].cell(row=3, column=1).value == '데이터가 없습니다.'
        assert wb['요구사항'].cell(row=4, column=1).value == '추출된 요구사항이 없습니다.'
