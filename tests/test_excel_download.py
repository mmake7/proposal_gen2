"""
Excel 다운로드 API 테스트 (Ticket #20)

GET /api/download/excel 엔드포인트 및 Excel 생성 로직을 검증합니다.
"""

import io
import os

import pytest
from openpyxl import load_workbook

import app as app_module
from services.excel_exporter import export_to_excel, generate_filename


# ── 테스트 픽스처 ────────────────────────────────────────────

SAMPLE_ANALYSIS = {
    'overview': {
        'project_name': '테스트 사업',
        'organization': '테스트 기관',
        'period': '2026.04 ~ 2026.12',
        'budget': '500',
        'budget_unit': '백만원',
        'contract_type': '제한경쟁입찰',
        'contract_method': '총액계약',
        'qualifications': '중소기업',
        'location': '서울특별시',
        'purpose': 'AI 기반 시스템 구축',
    },
    'requirements': [
        {'category': '기능', 'id': 'FR-001', 'name': '데이터 수집', 'desc': '자동 수집 기능', 'level': '필수'},
        {'category': '비기능', 'id': 'NFR-001', 'name': '보안', 'desc': '암호화 적용', 'level': '필수'},
    ],
    'scoring': [
        {'category': '기술', 'item': '아키텍처', 'criteria': '확장성', 'score': 30},
        {'category': '가격', 'item': '가격 평가', 'criteria': '적정 가격', 'score': 70},
    ],
    'toc': [
        {'level': 1, 'title': '사업 이해', 'children': [
            {'level': 2, 'title': '사업 배경', 'children': []},
        ]},
        {'level': 1, 'title': '기술 제안', 'children': []},
    ],
}


# ── API 엔드포인트 테스트 ────────────────────────────────────

class TestDownloadEndpoint:
    def test_no_analysis_returns_404(self, client):
        resp = client.get('/api/download/excel')
        assert resp.status_code == 404
        body = resp.get_json()
        assert 'error' in body

    def test_with_analysis_returns_xlsx(self, client):
        app_module._last_analysis = SAMPLE_ANALYSIS

        resp = client.get('/api/download/excel')
        assert resp.status_code == 200
        assert resp.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # Content-Disposition 헤더 확인
        cd = resp.headers.get('Content-Disposition', '')
        assert 'attachment' in cd
        assert '.xlsx' in cd

    def test_downloaded_file_is_valid_xlsx(self, client):
        app_module._last_analysis = SAMPLE_ANALYSIS

        resp = client.get('/api/download/excel')
        wb = load_workbook(io.BytesIO(resp.data))
        assert wb.sheetnames == ['사업개요', '요구사항', '배점기준', '제안목차']

    def test_filename_contains_project_name(self, client):
        app_module._last_analysis = SAMPLE_ANALYSIS

        resp = client.get('/api/download/excel')
        cd = resp.headers.get('Content-Disposition', '')
        # UTF-8 인코딩된 파일명 확인
        assert 'filename*=' in cd or 'filename=' in cd

    def test_empty_analysis_still_generates_file(self, client):
        app_module._last_analysis = {
            'overview': None,
            'requirements': [],
            'scoring': [],
            'toc': [],
        }

        resp = client.get('/api/download/excel')
        assert resp.status_code == 200
        wb = load_workbook(io.BytesIO(resp.data))
        assert len(wb.sheetnames) == 4


# ── Excel 생성 로직 테스트 ───────────────────────────────────

class TestExcelExporter:
    def test_export_returns_bytes_io(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        assert isinstance(buf, io.BytesIO)
        assert len(buf.getvalue()) > 0

    def test_four_sheets_created(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        assert wb.sheetnames == ['사업개요', '요구사항', '배점기준', '제안목차']

    def test_overview_sheet_has_data(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['사업개요']
        # 제목 행 + 빈 행 + 9개 필드 = 11행
        assert ws.max_row == 11

    def test_requirements_sheet_has_header_and_rows(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['요구사항']
        # 제목(1) + 빈(2) + 헤더(3) + 2 데이터 행 = 5행
        assert ws.max_row == 5
        # 헤더 확인
        assert ws.cell(row=3, column=1).value == 'ID'
        assert ws.cell(row=3, column=5).value == '필수여부'

    def test_scoring_sheet_has_total_row(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['배점기준']
        # 제목(1) + 빈(2) + 헤더(3) + 2 데이터 + 합계 = 6행
        last_row = ws.max_row
        assert ws.cell(row=last_row, column=1).value == '합계'
        assert ws.cell(row=last_row, column=4).value == 100

    def test_toc_sheet_flattens_hierarchy(self):
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['제안목차']
        # 제목(1) + 빈(2) + 헤더(3) + 3 항목 (사업이해, 사업배경, 기술제안) = 6행
        assert ws.max_row == 6

    def test_empty_overview_handled(self):
        data = {**SAMPLE_ANALYSIS, 'overview': None}
        buf = export_to_excel(data)
        wb = load_workbook(buf)
        ws = wb['사업개요']
        assert ws.cell(row=3, column=1).value == '데이터가 없습니다.'

    def test_empty_requirements_handled(self):
        data = {**SAMPLE_ANALYSIS, 'requirements': []}
        buf = export_to_excel(data)
        wb = load_workbook(buf)
        ws = wb['요구사항']
        assert ws.cell(row=4, column=1).value == '추출된 요구사항이 없습니다.'


# ── 파일명 생성 테스트 ───────────────────────────────────────

class TestFilename:
    def test_with_project_name(self):
        name = generate_filename({'project_name': '테스트 프로젝트'})
        assert name.startswith('RFP분석_테스트 프로젝트_')
        assert name.endswith('.xlsx')

    def test_without_overview(self):
        name = generate_filename(None)
        assert name.startswith('RFP_분석결과_')
        assert name.endswith('.xlsx')

    def test_special_chars_removed(self):
        name = generate_filename({'project_name': 'A/B:C*D?E'})
        assert '/' not in name
        assert ':' not in name
        assert '*' not in name
        assert '?' not in name

    def test_long_name_truncated(self):
        name = generate_filename({'project_name': 'A' * 100})
        # 이름 부분은 50자로 제한
        assert len(name) < 100

    def test_empty_project_name(self):
        """프로젝트명이 빈 문자열이면 기본 파일명 사용"""
        name = generate_filename({'project_name': ''})
        assert name.startswith('RFP_분석결과_')

    def test_whitespace_project_name(self):
        """프로젝트명이 공백만 있으면 기본 파일명 사용"""
        name = generate_filename({'project_name': '   '})
        assert name.startswith('RFP_분석결과_')


# ── Excel 데이터 정확성 테스트 ────────────────────────────

@pytest.mark.unit
class TestExcelDataAccuracy:
    def test_overview_budget_includes_unit(self):
        """사업개요 시트의 예산에 단위가 포함된다"""
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['사업개요']
        # 예산 행 찾기 (label이 '예산'인 행)
        budget_value = None
        for row in range(3, ws.max_row + 1):
            if ws.cell(row=row, column=1).value == '예산':
                budget_value = ws.cell(row=row, column=2).value
                break
        assert budget_value is not None
        assert '500' in budget_value
        assert '백만원' in budget_value

    def test_requirements_data_matches_input(self):
        """요구사항 시트의 데이터가 입력과 일치한다"""
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['요구사항']
        # 첫 번째 데이터 행 (row 4)
        assert ws.cell(row=4, column=1).value == 'FR-001'
        assert ws.cell(row=4, column=2).value == '기능'
        assert ws.cell(row=4, column=3).value == '데이터 수집'

    def test_scoring_data_matches_input(self):
        """배점기준 시트의 데이터가 입력과 일치한다"""
        buf = export_to_excel(SAMPLE_ANALYSIS)
        wb = load_workbook(buf)
        ws = wb['배점기준']
        # 첫 번째 데이터 행 (row 4)
        assert ws.cell(row=4, column=1).value == '기술'
        assert ws.cell(row=4, column=2).value == '아키텍처'
        assert ws.cell(row=4, column=4).value == 30

    def test_empty_scoring_handled(self):
        """빈 배점기준도 정상 처리된다"""
        data = {**SAMPLE_ANALYSIS, 'scoring': []}
        buf = export_to_excel(data)
        wb = load_workbook(buf)
        ws = wb['배점기준']
        assert ws.cell(row=4, column=1).value == '추출된 배점기준이 없습니다.'

    def test_empty_toc_handled(self):
        """빈 목차도 정상 처리된다"""
        data = {**SAMPLE_ANALYSIS, 'toc': []}
        buf = export_to_excel(data)
        wb = load_workbook(buf)
        ws = wb['제안목차']
        assert ws.cell(row=4, column=1).value == '추출된 목차가 없습니다.'

    def test_deeply_nested_toc(self):
        """3단계 이상 중첩된 목차도 정상 평탄화된다"""
        data = {
            **SAMPLE_ANALYSIS,
            'toc': [
                {'level': 1, 'title': '1장', 'children': [
                    {'level': 2, 'title': '1.1절', 'children': [
                        {'level': 3, 'title': '1.1.1항', 'children': []},
                    ]},
                ]},
            ],
        }
        buf = export_to_excel(data)
        wb = load_workbook(buf)
        ws = wb['제안목차']
        # 헤더(3) + 3 항목 = 6행
        assert ws.max_row == 6
        assert ws.cell(row=4, column=1).value == 1
        assert ws.cell(row=5, column=1).value == 2
        assert ws.cell(row=6, column=1).value == 3
