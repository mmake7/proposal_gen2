"""HWPX ingest 단위 테스트 (zip 안 만들고 _parse_section 직접 검증)."""

from __future__ import annotations

from services_v2.documents.hwpx_ingest import _detect_chapter_marker, _parse_section
from services_v2.documents.rfp_document import TableRegion


# 미니 HWPX section XML 빌더 ─────────────────────────────

HP_NS = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
SEC_NS = 'http://www.hancom.co.kr/hwpml/2011/section'


def build_section(*paras_or_tables: str) -> bytes:
    """간단한 section XML 빌더 — '<p>텍스트</p>' 또는 '<tbl>...</tbl>' 문자열을 받음."""
    body = '\n'.join(paras_or_tables)
    xml = f'''<?xml version="1.0"?>
<hs:sec xmlns:hp="{HP_NS}" xmlns:hs="{SEC_NS}">
{body}
</hs:sec>'''
    return xml.encode('utf-8')


def p(text: str) -> str:
    return f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'


def cell(text: str) -> str:
    return f'<hp:tc><hp:subList>{p(text)}</hp:subList></hp:tc>'


def tbl(*rows: list[str]) -> str:
    """rows = [['셀1', '셀2'], ...]"""
    tr_xml = '\n'.join(
        '<hp:tr>' + ''.join(cell(c) for c in row) + '</hp:tr>'
        for row in rows
    )
    return f'<hp:tbl>{tr_xml}</hp:tbl>'


# ── 표 안 문단 중복 제거 ────────────────────────────

class TestTextDedup:
    def test_table_cell_text_not_in_body(self):
        """표 안 셀 문단이 본문 텍스트에 중복되면 안 됨."""
        xml = build_section(
            p('본문 첫 문단'),
            tbl(['표셀A', '표셀B'], ['표셀C', '표셀D']),
            p('본문 끝 문단'),
        )
        text, tables = _parse_section(xml, 1)
        # 본문 텍스트엔 본문 문단만
        assert '본문 첫 문단' in text
        assert '본문 끝 문단' in text
        assert '표셀A' not in text  # 표 안 문단은 본문에서 제외
        assert '표셀B' not in text
        # 표는 별도로 보존
        assert len(tables) == 1
        assert tables[0].rows[0] == ['표셀A', '표셀B']

    def test_only_text_no_tables(self):
        xml = build_section(p('첫 줄'), p('둘째 줄'), p(''))
        text, tables = _parse_section(xml, 1)
        assert '첫 줄' in text and '둘째 줄' in text
        assert tables == []


# ── _detect_chapter_marker ───────────────────────────

class TestChapterMarker:
    def test_roman_numeral_chapter(self):
        region = TableRegion(page_number=1, rows=[['Ⅰ', '', '용역개요']])
        assert _detect_chapter_marker(region) == '[Chapter Ⅰ 용역개요]'

    def test_roman_numeral_with_dot(self):
        region = TableRegion(page_number=1, rows=[['I.', '사업개요']])
        assert _detect_chapter_marker(region) == '[Chapter I. 사업개요]'

    def test_jang_pattern(self):
        region = TableRegion(page_number=1, rows=[['제1장', '사업개요']])
        assert _detect_chapter_marker(region) == '[Chapter 제1장 사업개요]'

    def test_not_chapter_header(self):
        # 일반 데이터 표는 마커 안 됨
        region = TableRegion(page_number=1, rows=[['사업명', '정보시스템 운영']])
        assert _detect_chapter_marker(region) is None

    def test_too_many_rows_rejected(self):
        # 3행 이상 표는 chapter 헤더 아님
        region = TableRegion(page_number=1, rows=[
            ['Ⅰ', '', '용역개요'],
            ['데이터1', '데이터2', '데이터3'],
            ['데이터4', '데이터5', '데이터6'],
        ])
        assert _detect_chapter_marker(region) is None

    def test_title_too_long_rejected(self):
        # 제목이 너무 길면 chapter 헤더 아님 (50자 초과)
        long_title = '매우 ' * 30  # 90자
        region = TableRegion(page_number=1, rows=[['Ⅰ', long_title]])
        assert _detect_chapter_marker(region) is None

    def test_title_with_newline_rejected(self):
        region = TableRegion(page_number=1, rows=[['Ⅰ', '사업\n개요']])
        assert _detect_chapter_marker(region) is None

    def test_empty_table_safe(self):
        assert _detect_chapter_marker(TableRegion(page_number=1, rows=[])) is None


# ── Chapter 표가 본문에 마커로 삽입 ──────────────────

class TestChapterInsertedInBody:
    def test_chapter_table_inserts_marker(self):
        xml = build_section(
            p('표지'),
            tbl(['Ⅰ', '', '용역개요']),
            p('실제 본문 내용'),
        )
        text, tables = _parse_section(xml, 1)
        assert '[Chapter Ⅰ 용역개요]' in text
        assert '표지' in text
        assert '실제 본문 내용' in text

    def test_normal_table_no_marker(self):
        xml = build_section(
            p('표지'),
            tbl(['사업명', '운영 사업'], ['예산', '5억']),
        )
        text, tables = _parse_section(xml, 1)
        # chapter 마커 없음
        assert '[Chapter' not in text
        # 표는 보존
        assert len(tables) == 1
