"""HWPX 네이티브 파싱 — Stage 1 (HWPX 파일용).

HWPX는 ZIP 컨테이너 + OWPML 기반 XML 문서.
- Contents/section*.xml 본문 텍스트와 표 구조 파싱
- 외부 도구·변환 없이 stdlib(zipfile + xml.etree)만 사용

표 구조 (hp 네임스페이스):
  <hp:tbl rowCnt colCnt>
    <hp:tr>
      <hp:tc>
        <hp:subList> ... <hp:p> ... <hp:run> ... <hp:t>텍스트</hp:t>
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from xml.etree import ElementTree as ET

from services_v2.documents.rfp_document import PageInfo, RfpDocument, TableRegion

logger = logging.getLogger(__name__)

# OWPML hp 네임스페이스 (2011년 사양 기준)
HP_NS = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
NS = {'hp': HP_NS}

# 줄바꿈/페이지 break 처리용 태그 로컬명
LINE_BREAK_TAGS = {'lineBreak'}
PARA_BREAK_TAGS = {'p'}


class HwpxIngestError(Exception):
    """HWPX 인제스트 실패."""


def ingest_hwpx_bytes(data: bytes, filename: str = 'upload.hwpx') -> RfpDocument:
    """바이트 HWPX → RfpDocument."""
    if not data:
        raise HwpxIngestError('빈 HWPX 데이터')

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HwpxIngestError(f'HWPX 파일 형식 오류: {exc}') from exc

    with zf:
        section_names = sorted(
            n for n in zf.namelist()
            if re.match(r'Contents/section\d+\.xml$', n)
        )
        if not section_names:
            raise HwpxIngestError(
                'Contents/section*.xml을 찾을 수 없습니다 (HWPX 구조 아님?)'
            )

        pages: list[PageInfo] = []
        all_regions: list[TableRegion] = []
        full_text_parts: list[str] = []

        for section_idx, name in enumerate(section_names, start=1):
            try:
                xml_bytes = zf.read(name)
                section_text, regions = _parse_section(xml_bytes, section_idx)
            except ET.ParseError as exc:
                logger.warning('%s 파싱 실패: %s', name, exc)
                continue

            pages.append(PageInfo(
                page_number=section_idx,
                text=section_text,
                extraction_method='hwpx',
                has_tables=bool(regions),
            ))
            full_text_parts.append(section_text)
            all_regions.extend(regions)

        # 메타데이터 추출
        metadata = _extract_metadata(zf)

    full_text = '\n\n'.join(full_text_parts)
    return RfpDocument(
        filename=filename,
        full_text=full_text,
        pages=pages,
        table_regions=all_regions,
        metadata=metadata,
    )


def _parse_section(xml_bytes: bytes, section_idx: int) -> tuple[str, list[TableRegion]]:
    """단일 section XML → (텍스트, 표 영역 리스트).

    본문 텍스트는 표 안 문단을 제외 (이중 추출 방지).
    1행 표가 chapter 헤더 패턴이면 본문에 인라인 마커로 삽입 (TOC agent 지원).
    """
    root = ET.fromstring(xml_bytes)

    # 표 안의 모든 hp:p를 식별 — 본문에서 제외 대상
    in_table_paras: set[int] = set()
    for tbl in root.iter(f'{{{HP_NS}}}tbl'):
        for para in tbl.iter(f'{{{HP_NS}}}p'):
            in_table_paras.add(id(para))

    text_parts: list[str] = []
    tables: list[TableRegion] = []

    for para in root.iter(f'{{{HP_NS}}}p'):
        if id(para) in in_table_paras:
            continue  # 표 안 문단은 셀에 이미 들어감 — 본문에서 중복 제거
        para_text = _para_text(para)
        if para_text:
            text_parts.append(para_text)

    for tbl in root.iter(f'{{{HP_NS}}}tbl'):
        region = _table_to_region(tbl, section_idx)
        if region is None:
            continue
        tables.append(region)
        # Chapter 헤더 표는 본문에도 인라인 마커로 삽입 → TOC agent가 인식
        marker = _detect_chapter_marker(region)
        if marker:
            text_parts.append(marker)

    section_text = '\n'.join(text_parts)
    return section_text, tables


# 한국 공공 RFP의 chapter 헤더 표는 다양한 형태로 나타남.
# 예: 표 #003 ['Ⅰ', '', '용역개요'] — 1행 표, 로마숫자 + 짧은 제목
ROMAN_NUMERAL_PATTERN = re.compile(
    r'^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]|[IVX]{1,5}|제?\d{1,2}장?)[.．]?\s*$'
)


def _detect_chapter_marker(region: TableRegion) -> str | None:
    """1~2행 표 중 chapter 헤더 패턴이면 인라인 마커 텍스트 반환.

    예:
      [Ⅰ, '', 용역개요]   → '[Chapter Ⅰ. 용역개요]'
      [I., 사업개요]       → '[Chapter I. 사업개요]'
    """
    if not region.rows or len(region.rows) > 2:
        return None
    row = region.rows[0]
    non_empty = [c.strip() for c in row if c and c.strip()]
    if len(non_empty) < 2:
        return None
    # 첫 비-빈 셀이 로마숫자/장번호 패턴이어야 함
    if not ROMAN_NUMERAL_PATTERN.match(non_empty[0]):
        return None
    # 나머지 셀에 짧은 제목 (50자 이내, 줄바꿈 없음)
    title = ' '.join(non_empty[1:])
    if not title or '\n' in title or len(title) > 50:
        return None
    return f'[Chapter {non_empty[0]} {title}]'


def _para_text(para: ET.Element) -> str:
    """문단 → 텍스트 (run 내 t 요소 결합).

    표 안의 문단도 같은 함수로 추출되지만, 본문 추출 시엔 표 셀의 텍스트도
    함께 들어가서 자연스러운 reading flow를 만든다.
    """
    parts: list[str] = []
    for elem in para.iter():
        tag = _local(elem.tag)
        if tag == 't':
            if elem.text:
                parts.append(elem.text)
        elif tag == 'lineBreak':
            parts.append('\n')
        elif tag == 'tab':
            parts.append('\t')
    return ''.join(parts).strip()


def _table_to_region(tbl: ET.Element, section_idx: int) -> TableRegion | None:
    """<hp:tbl> → TableRegion."""
    rows: list[list[str]] = []
    for tr in tbl.findall(f'{{{HP_NS}}}tr'):
        row: list[str] = []
        for tc in tr.findall(f'{{{HP_NS}}}tc'):
            cell_text = _cell_text(tc)
            row.append(cell_text)
        if row:
            rows.append(row)

    if not rows:
        return None

    return TableRegion(
        page_number=section_idx,  # HWPX는 페이지 개념이 약해 section 인덱스로 대체
        rows=rows,
    )


def _cell_text(tc: ET.Element) -> str:
    """셀 내부 모든 문단을 합쳐서 셀 텍스트 생성."""
    paras = tc.iter(f'{{{HP_NS}}}p')
    lines = [_para_text(p) for p in paras]
    lines = [ln for ln in lines if ln]
    return '\n'.join(lines)


def _local(tag: str) -> str:
    """{ns}local → local."""
    if tag.startswith('{'):
        return tag.split('}', 1)[1]
    return tag


def _extract_metadata(zf: zipfile.ZipFile) -> dict:
    """content.hpf 등에서 dc:title, dc:creator 추출."""
    meta: dict = {}
    try:
        hpf_bytes = zf.read('Contents/content.hpf')
    except KeyError:
        return meta

    try:
        root = ET.fromstring(hpf_bytes)
    except ET.ParseError:
        return meta

    dc_ns = 'http://purl.org/dc/elements/1.1/'
    for field in ('title', 'creator', 'subject', 'description', 'language'):
        elem = root.find(f'.//{{{dc_ns}}}{field}')
        if elem is not None and elem.text:
            meta[field] = elem.text.strip()
    return meta
