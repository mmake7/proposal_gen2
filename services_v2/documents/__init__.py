"""문서 인제스트 — 확장자에 따라 PDF/HWPX/DOCX로 자동 분기."""

from __future__ import annotations

import os

from services_v2.documents.docx_ingest import DocxIngestError, ingest_docx_bytes
from services_v2.documents.hwpx_ingest import HwpxIngestError, ingest_hwpx_bytes
from services_v2.documents.pdf_ingest import IngestError, ingest_pdf_bytes
from services_v2.documents.rfp_document import RfpDocument


def ingest_bytes(data: bytes, filename: str) -> RfpDocument:
    """파일명 확장자로 자동 분기. 지원: .pdf, .hwpx, .docx"""
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf':
        return ingest_pdf_bytes(data, filename=filename)
    if ext == '.hwpx':
        return ingest_hwpx_bytes(data, filename=filename)
    if ext == '.docx':
        return ingest_docx_bytes(data, filename=filename)
    raise IngestError(
        f'지원하지 않는 확장자: {ext} (지원: .pdf, .hwpx, .docx). '
        '.hwp/.doc는 scripts/convert_legacy.py로 변환 후 사용.'
    )


__all__ = [
    'ingest_bytes', 'IngestError',
    'HwpxIngestError', 'DocxIngestError',
]
