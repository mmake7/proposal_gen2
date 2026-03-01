"""
RFP 분석 결과 Excel 내보내기 모듈 (Ticket #20)

분석 결과 dict를 4개 시트(사업개요, 요구사항, 배점기준, 제안목차)로
구성된 Excel 워크북으로 변환합니다.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

# ── 스타일 상수 ──────────────────────────────────────────────

_HEADER_FONT = Font(name='맑은 고딕', bold=True, size=11, color='FFFFFF')
_HEADER_FILL = PatternFill(start_color='2B579A', end_color='2B579A', fill_type='solid')
_HEADER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)

_LABEL_FONT = Font(name='맑은 고딕', bold=True, size=11, color='2B579A')
_LABEL_FILL = PatternFill(start_color='E8EEF7', end_color='E8EEF7', fill_type='solid')

_BODY_FONT = Font(name='맑은 고딕', size=11)
_BODY_ALIGNMENT = Alignment(vertical='center', wrap_text=True)

_THIN_BORDER = Border(
    left=Side(style='thin', color='B0B0B0'),
    right=Side(style='thin', color='B0B0B0'),
    top=Side(style='thin', color='B0B0B0'),
    bottom=Side(style='thin', color='B0B0B0'),
)

_TITLE_FONT = Font(name='맑은 고딕', bold=True, size=14, color='2B579A')


# ── Public API ───────────────────────────────────────────────

def export_to_excel(data: dict) -> io.BytesIO:
    """분석 결과 dict를 Excel 바이트 스트림으로 변환합니다.

    Args:
        data: RfpAnalysisResult.to_dict() 형식의 dict.
              키: overview, requirements, scoring, toc

    Returns:
        io.BytesIO: xlsx 파일 바이트 스트림 (seek(0) 완료)
    """
    wb = Workbook()

    # 기본 시트 제거 후 순서대로 생성
    wb.remove(wb.active)

    _build_overview_sheet(wb, data.get('overview'))
    _build_requirements_sheet(wb, data.get('requirements', []))
    _build_scoring_sheet(wb, data.get('scoring', []))
    _build_toc_sheet(wb, data.get('toc', []))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── 사업개요 시트 ────────────────────────────────────────────

_OVERVIEW_LABELS = [
    ('project_name',    '사업명'),
    ('organization',    '발주기관'),
    ('purpose',         '사업 목적'),
    ('period',          '사업기간'),
    ('budget',          '예산'),
    ('contract_type',   '계약 방식'),
    ('contract_method', '계약 유형'),
    ('qualifications',  '참가자격'),
    ('location',        '수행장소'),
]


def _build_overview_sheet(wb: Workbook, overview: dict | None) -> None:
    ws = wb.create_sheet(title='사업개요')

    # 시트 제목
    ws.merge_cells('A1:B1')
    title_cell = ws['A1']
    title_cell.value = '사업개요'
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 36

    if not overview:
        ws['A3'].value = '데이터가 없습니다.'
        ws['A3'].font = _BODY_FONT
        _auto_column_width(ws, [40, 80])
        return

    row = 3
    for key, label in _OVERVIEW_LABELS:
        value = overview.get(key, '')

        # 예산은 단위 포함
        if key == 'budget' and value:
            unit = overview.get('budget_unit', '백만원')
            value = f'{value} {unit}'

        label_cell = ws.cell(row=row, column=1, value=label)
        label_cell.font = _LABEL_FONT
        label_cell.fill = _LABEL_FILL
        label_cell.border = _THIN_BORDER
        label_cell.alignment = Alignment(horizontal='left', vertical='center')

        value_cell = ws.cell(row=row, column=2, value=value or '-')
        value_cell.font = _BODY_FONT
        value_cell.border = _THIN_BORDER
        value_cell.alignment = _BODY_ALIGNMENT

        ws.row_dimensions[row].height = 28
        row += 1

    _auto_column_width(ws, [20, 80])


# ── 요구사항 시트 ────────────────────────────────────────────

_REQ_HEADERS = ['ID', '분류', '요구사항명', '설명', '필수여부']


def _build_requirements_sheet(wb: Workbook, requirements: list[dict]) -> None:
    ws = wb.create_sheet(title='요구사항')

    # 시트 제목
    ws.merge_cells('A1:E1')
    title_cell = ws['A1']
    title_cell.value = '요구사항 목록'
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 36

    # 헤더 행
    for col_idx, header in enumerate(_REQ_HEADERS, start=1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _THIN_BORDER
    ws.row_dimensions[3].height = 30

    if not requirements:
        ws.merge_cells('A4:E4')
        ws['A4'].value = '추출된 요구사항이 없습니다.'
        ws['A4'].font = _BODY_FONT
        _auto_column_width(ws, [12, 10, 30, 60, 10])
        return

    row = 4
    for req in requirements:
        values = [
            req.get('id', ''),
            req.get('category', ''),
            req.get('name', ''),
            req.get('desc', ''),
            req.get('level', ''),
        ]
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col_idx, value=val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            cell.alignment = _BODY_ALIGNMENT
        row += 1

    _auto_column_width(ws, [12, 10, 30, 60, 10])
    ws.auto_filter.ref = f'A3:E{row - 1}'


# ── 배점기준 시트 ────────────────────────────────────────────

_SCORING_HEADERS = ['대분류', '평가항목', '평가기준', '배점']


def _build_scoring_sheet(wb: Workbook, scoring: list[dict]) -> None:
    ws = wb.create_sheet(title='배점기준')

    # 시트 제목
    ws.merge_cells('A1:D1')
    title_cell = ws['A1']
    title_cell.value = '배점기준'
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 36

    # 헤더 행
    for col_idx, header in enumerate(_SCORING_HEADERS, start=1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _THIN_BORDER
    ws.row_dimensions[3].height = 30

    if not scoring:
        ws.merge_cells('A4:D4')
        ws['A4'].value = '추출된 배점기준이 없습니다.'
        ws['A4'].font = _BODY_FONT
        _auto_column_width(ws, [15, 25, 60, 10])
        return

    row = 4
    total_score = 0
    for item in scoring:
        score = item.get('score', 0)
        total_score += score
        values = [
            item.get('category', ''),
            item.get('item', ''),
            item.get('criteria', ''),
            score,
        ]
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col_idx, value=val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            cell.alignment = _BODY_ALIGNMENT
            if col_idx == 4:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        row += 1

    # 합계 행
    ws.merge_cells(f'A{row}:C{row}')
    total_label = ws.cell(row=row, column=1, value='합계')
    total_label.font = Font(name='맑은 고딕', bold=True, size=11)
    total_label.alignment = Alignment(horizontal='right', vertical='center')
    total_label.border = _THIN_BORDER
    for c in range(2, 4):
        ws.cell(row=row, column=c).border = _THIN_BORDER

    total_cell = ws.cell(row=row, column=4, value=total_score)
    total_cell.font = Font(name='맑은 고딕', bold=True, size=11)
    total_cell.alignment = Alignment(horizontal='center', vertical='center')
    total_cell.border = _THIN_BORDER

    _auto_column_width(ws, [15, 25, 60, 10])
    ws.auto_filter.ref = f'A3:D{row - 1}'


# ── 제안목차 시트 ────────────────────────────────────────────

_TOC_HEADERS = ['수준', '목차 제목']


def _build_toc_sheet(wb: Workbook, toc: list[dict]) -> None:
    ws = wb.create_sheet(title='제안목차')

    # 시트 제목
    ws.merge_cells('A1:B1')
    title_cell = ws['A1']
    title_cell.value = '제안목차'
    title_cell.font = _TITLE_FONT
    title_cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 36

    # 헤더 행
    for col_idx, header in enumerate(_TOC_HEADERS, start=1):
        cell = ws.cell(row=3, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _THIN_BORDER
    ws.row_dimensions[3].height = 30

    if not toc:
        ws.merge_cells('A4:B4')
        ws['A4'].value = '추출된 목차가 없습니다.'
        ws['A4'].font = _BODY_FONT
        _auto_column_width(ws, [10, 80])
        return

    rows: list[tuple[int, str]] = []
    _flatten_toc(toc, rows)

    row = 4
    for level, title in rows:
        # 수준 표시
        level_cell = ws.cell(row=row, column=1, value=level)
        level_cell.font = _BODY_FONT
        level_cell.border = _THIN_BORDER
        level_cell.alignment = Alignment(horizontal='center', vertical='center')

        # 들여쓰기로 계층 표현
        indent = '    ' * (level - 1)
        title_cell = ws.cell(row=row, column=2, value=f'{indent}{title}')
        title_font = Font(
            name='맑은 고딕',
            bold=(level <= 1),
            size=11,
        )
        title_cell.font = title_font
        title_cell.border = _THIN_BORDER
        title_cell.alignment = _BODY_ALIGNMENT

        row += 1

    _auto_column_width(ws, [10, 80])


def _flatten_toc(items: list[dict], out: list[tuple[int, str]]) -> None:
    """재귀적으로 TOC 항목을 평탄화합니다."""
    for item in items:
        level = item.get('level', 1)
        title = item.get('title', '')
        out.append((level, title))
        children = item.get('children', [])
        if children:
            _flatten_toc(children, out)


# ── 유틸리티 ─────────────────────────────────────────────────

def _auto_column_width(ws, min_widths: list[int]) -> None:
    """열 너비를 최소값 기준으로 설정합니다."""
    for col_idx, width in enumerate(min_widths, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width


def generate_filename(overview: dict | None = None) -> str:
    """다운로드용 파일명을 생성합니다."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if overview and overview.get('project_name'):
        # 파일명에 사용할 수 없는 문자 제거
        safe_name = overview['project_name']
        for ch in r'\/:*?"<>|':
            safe_name = safe_name.replace(ch, '')
        safe_name = safe_name.strip()[:50]
        if safe_name:
            return f'RFP분석_{safe_name}_{timestamp}.xlsx'
    return f'RFP_분석결과_{timestamp}.xlsx'
