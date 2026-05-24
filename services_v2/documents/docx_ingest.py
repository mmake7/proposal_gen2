"""DOCX 네이티브 파싱 — Office Open XML (OOXML) 직접 처리.

.docx도 zip 컨테이너 + xml. stdlib(zipfile + xml.etree)로 처리.

OOXML 구조:
  word/document.xml — 본문 (텍스트 + 표)
  <w:p>            — 문단
    <w:r>          — run (스타일 단위)
      <w:t>        — 텍스트
      <w:br/>      — 줄바꿈
      <w:tab/>     — 탭
  <w:tbl>          — 표
    <w:tr>         — 행
      <w:tc>       — 셀
        <w:p>      — 셀 내부 문단
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from xml.etree import ElementTree as ET

from services_v2.documents.rfp_document import PageInfo, RfpDocument, TableRegion
from services_v2.documents.hwpx_ingest import _detect_chapter_marker

logger = logging.getLogger(__name__)

# OOXML w 네임스페이스
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class DocxIngestError(Exception):
    """DOCX 인제스트 실패."""


def ingest_docx_bytes(data: bytes, filename: str = 'upload.docx') -> RfpDocument:
    if not data:
        raise DocxIngestError('빈 DOCX 데이터')

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocxIngestError(f'DOCX 파일 형식 오류: {exc}') from exc

    with zf:
        try:
            xml_bytes = zf.read('word/document.xml')
        except KeyError as exc:
            raise DocxIngestError(
                'word/document.xml 찾을 수 없음 (DOCX 구조 아님?)'
            ) from exc

        try:
            text, table_regions = _parse_document(xml_bytes)
        except ET.ParseError as exc:
            raise DocxIngestError(f'XML 파싱 실패: {exc}') from exc

        metadata = _extract_core_properties(zf)

    pages = [PageInfo(
        page_number=1,
        text=text,
        extraction_method='docx',
        has_tables=bool(table_regions),
    )]

    return RfpDocument(
        filename=filename,
        full_text=text,
        pages=pages,
        table_regions=table_regions,
        metadata=metadata,
    )


def _parse_document(xml_bytes: bytes) -> tuple[str, list[TableRegion]]:
    """word/document.xml → (본문 텍스트, 표 영역 리스트).

    표 안 문단은 본문 텍스트에서 제외(셀에 이미 포함). hwpx_ingest와 동일 정책.
    Chapter 헤더 패턴 표는 본문에 인라인 마커 삽입.
    """
    root = ET.fromstring(xml_bytes)

    # 표 안의 모든 w:p — 본문에서 제외
    in_table_paras: set[int] = set()
    for tbl in root.iter(f'{{{W_NS}}}tbl'):
        for para in tbl.iter(f'{{{W_NS}}}p'):
            in_table_paras.add(id(para))

    text_parts: list[str] = []
    tables: list[TableRegion] = []

    for para in root.iter(f'{{{W_NS}}}p'):
        if id(para) in in_table_paras:
            continue
        para_text = _para_text(para)
        if para_text:
            text_parts.append(para_text)

    for tbl in root.iter(f'{{{W_NS}}}tbl'):
        region = _table_to_region(tbl)
        if region is None:
            continue
        tables.append(region)
        marker = _detect_chapter_marker(region)
        if marker:
            text_parts.append(marker)

    return '\n'.join(text_parts), tables


def _para_text(para: ET.Element) -> str:
    """w:p → 텍스트 (w:t 결합 + w:br/w:tab 처리)."""
    parts: list[str] = []
    for elem in para.iter():
        tag = _local(elem.tag)
        if tag == 't':
            if elem.text:
                parts.append(elem.text)
        elif tag == 'br':
            parts.append('\n')
        elif tag == 'tab':
            parts.append('\t')
    return ''.join(parts).strip()


def _table_to_region(tbl: ET.Element) -> TableRegion | None:
    """w:tbl → TableRegion."""
    rows: list[list[str]] = []
    for tr in tbl.findall(f'{{{W_NS}}}tr'):
        row: list[str] = []
        for tc in tr.findall(f'{{{W_NS}}}tc'):
            cell_text = _cell_text(tc)
            row.append(cell_text)
        if row:
            rows.append(row)
    if not rows:
        return None
    # DOCX는 페이지 개념이 약함 — 1로 통일
    return TableRegion(page_number=1, rows=rows)


def _cell_text(tc: ET.Element) -> str:
    """w:tc 내부 모든 문단을 합쳐 셀 텍스트 생성."""
    lines = [_para_text(p) for p in tc.iter(f'{{{W_NS}}}p')]
    lines = [ln for ln in lines if ln]
    return '\n'.join(lines)


def _local(tag: str) -> str:
    if tag.startswith('{'):
        return tag.split('}', 1)[1]
    return tag


def _extract_core_properties(zf: zipfile.ZipFile) -> dict:
    """docProps/core.xml에서 dc:title 등 메타 추출."""
    meta: dict = {}
    try:
        core_xml = zf.read('docProps/core.xml')
    except KeyError:
        return meta
    try:
        root = ET.fromstring(core_xml)
    except ET.ParseError:
        return meta

    dc_ns = 'http://purl.org/dc/elements/1.1/'
    for field in ('title', 'creator', 'subject', 'description'):
        elem = root.find(f'.//{{{dc_ns}}}{field}')
        if elem is not None and elem.text:
            meta[field] = elem.text.strip()
    return meta
