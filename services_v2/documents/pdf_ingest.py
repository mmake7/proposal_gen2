"""PDF Ingest — Stage 1.

기존 services.pdf_extractor (PyMuPDF + OCR)로 텍스트 추출,
pdfplumber로 표 영역을 별도 보존하여 RfpDocument 생성.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from services.pdf_extractor import PdfExtractor, PdfExtractionError
from services_v2.documents.rfp_document import PageInfo, RfpDocument, TableRegion

logger = logging.getLogger(__name__)


class IngestError(Exception):
    """PDF 인제스트 실패."""


def ingest_pdf_bytes(data: bytes, filename: str = 'upload.pdf') -> RfpDocument:
    """바이트 PDF → RfpDocument."""
    if not data:
        raise IngestError('빈 PDF 데이터')

    # 1) 텍스트 + OCR (기존 추출기 재사용)
    try:
        extractor = PdfExtractor(enable_ocr=True)
        result = extractor.extract_from_bytes(data, filename=filename)
    except PdfExtractionError as exc:
        raise IngestError(f'텍스트 추출 실패: {exc}') from exc

    pages = [
        PageInfo(
            page_number=p.page_number,
            text=p.text,
            extraction_method=p.extraction_method,
        )
        for p in result.pages
    ]

    # 2) 표 추출 (pdfplumber) — 임시 파일 경유
    table_regions: list[TableRegion] = []
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        table_regions = _extract_tables(tmp_path)
    except Exception as exc:
        logger.warning('pdfplumber 표 추출 실패 (계속 진행): %s', exc)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # 3) has_tables 플래그 갱신
    table_pages = {t.page_number for t in table_regions}
    for page in pages:
        page.has_tables = page.page_number in table_pages

    return RfpDocument(
        filename=filename,
        full_text=result.full_text,
        pages=pages,
        table_regions=table_regions,
        metadata=result.metadata or {},
    )


def _extract_tables(path: str) -> list[TableRegion]:
    """pdfplumber로 모든 페이지에서 표 추출."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning('pdfplumber 미설치 — 표 추출 건너뜀')
        return []

    regions: list[TableRegion] = []
    with pdfplumber.open(path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.find_tables()
            except Exception as exc:
                logger.debug('page %d find_tables 실패: %s', idx, exc)
                continue
            for table in tables:
                rows = table.extract() or []
                # 공백 셀 정리
                cleaned = [
                    [(c or '').strip() for c in row]
                    for row in rows
                ]
                bbox = table.bbox if hasattr(table, 'bbox') else None
                regions.append(TableRegion(
                    page_number=idx,
                    rows=cleaned,
                    bbox=bbox,
                ))
    return regions
