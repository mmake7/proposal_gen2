"""
PDF 텍스트 추출 모듈 (Ticket #16)

업로드된 PDF 파일에서 텍스트를 추출하는 핵심 모듈.
- PyMuPDF(fitz) 기반 텍스트 추출
- 스캔 기반 PDF에 대한 OCR 폴백 (pytesseract, 선택적)
- 페이지별 텍스트 추출 및 구조화

이 모듈은 PDF 파싱 API (Ticket #19)에서 사용됩니다.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ── OCR 의존성 (선택적) ──────────────────────────────────────
_ocr_available = False
try:
    from PIL import Image
    import pytesseract
    _ocr_available = True
except ImportError:
    pass

# 스캔 페이지 판별 기준: 텍스트 문자 수가 이 값 미만이면 스캔 페이지로 간주
_SCANNED_PAGE_CHAR_THRESHOLD = 30

# OCR 시 페이지를 이미지로 렌더링할 DPI
_OCR_DPI = 300


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class PageContent:
    """페이지별 추출 결과"""
    page_number: int           # 1-based
    text: str
    extraction_method: str     # 'text' | 'ocr' | 'skipped'
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)


@dataclass
class PdfExtractionResult:
    """PDF 전체 추출 결과"""
    filename: str
    total_pages: int
    pages: list[PageContent] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    full_text: str = ''
    extraction_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """직렬화 가능한 dict로 변환"""
        return {
            'filename': self.filename,
            'total_pages': self.total_pages,
            'metadata': self.metadata,
            'full_text': self.full_text,
            'extraction_summary': self.extraction_summary,
            'pages': [
                {
                    'page_number': p.page_number,
                    'text': p.text,
                    'extraction_method': p.extraction_method,
                    'char_count': p.char_count,
                }
                for p in self.pages
            ],
        }


# ── Core Extractor ───────────────────────────────────────────

class PdfExtractor:
    """
    PDF 텍스트 추출기.

    사용법::

        extractor = PdfExtractor()

        # 파일 경로로 추출
        result = extractor.extract_from_path('document.pdf')

        # 바이트 스트림으로 추출 (Flask 업로드 등)
        result = extractor.extract_from_bytes(file_bytes, filename='upload.pdf')

        # 특정 페이지만 추출
        result = extractor.extract_from_path('doc.pdf', pages=[1, 3, 5])
    """

    def __init__(self, *, enable_ocr: bool = True, ocr_lang: str = 'kor+eng'):
        """
        Args:
            enable_ocr: 스캔 페이지 OCR 활성화 여부 (pytesseract 필요)
            ocr_lang: Tesseract OCR 언어 코드 (기본: 한국어+영어)
        """
        self._enable_ocr = enable_ocr and _ocr_available
        self._ocr_lang = ocr_lang

        if enable_ocr and not _ocr_available:
            logger.warning(
                'OCR이 요청되었으나 pytesseract 또는 Pillow가 설치되지 않았습니다. '
                'OCR 없이 텍스트 기반 추출만 수행합니다. '
                '설치: pip install pytesseract Pillow'
            )

    # ── Public API ───────────────────────────────────────────

    def extract_from_path(
        self,
        file_path: str | Path,
        *,
        pages: list[int] | None = None,
    ) -> PdfExtractionResult:
        """파일 경로에서 PDF 텍스트를 추출합니다.

        Args:
            file_path: PDF 파일 경로
            pages: 추출할 페이지 번호 리스트 (1-based). None이면 전체 페이지.

        Returns:
            PdfExtractionResult

        Raises:
            FileNotFoundError: 파일이 존재하지 않는 경우
            PdfExtractionError: PDF 파싱 실패 시
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f'PDF 파일을 찾을 수 없습니다: {file_path}')

        try:
            doc = fitz.open(str(file_path))
        except Exception as exc:
            raise PdfExtractionError(f'PDF 파일을 열 수 없습니다: {exc}') from exc

        with doc:
            return self._extract(doc, filename=file_path.name, pages=pages)

    def extract_from_bytes(
        self,
        data: bytes,
        *,
        filename: str = 'upload.pdf',
        pages: list[int] | None = None,
    ) -> PdfExtractionResult:
        """바이트 데이터에서 PDF 텍스트를 추출합니다.

        Flask 파일 업로드 등에서 사용::

            file = request.files['file']
            result = extractor.extract_from_bytes(
                file.read(), filename=file.filename
            )

        Args:
            data: PDF 바이트 데이터
            filename: 원본 파일명
            pages: 추출할 페이지 번호 리스트 (1-based). None이면 전체 페이지.

        Returns:
            PdfExtractionResult

        Raises:
            PdfExtractionError: PDF 파싱 실패 시
        """
        if not data:
            raise PdfExtractionError('빈 PDF 데이터가 전달되었습니다.')

        try:
            doc = fitz.open(stream=data, filetype='pdf')
        except Exception as exc:
            raise PdfExtractionError(f'PDF 데이터를 파싱할 수 없습니다: {exc}') from exc

        with doc:
            return self._extract(doc, filename=filename, pages=pages)

    # ── Internal ─────────────────────────────────────────────

    def _extract(
        self,
        doc: fitz.Document,
        *,
        filename: str,
        pages: list[int] | None,
    ) -> PdfExtractionResult:
        """fitz.Document에서 텍스트를 추출합니다."""
        total_pages = len(doc)
        metadata = self._extract_metadata(doc)

        # 추출 대상 페이지 결정 (1-based → 0-based)
        if pages is not None:
            target_indices = [p - 1 for p in pages if 1 <= p <= total_pages]
        else:
            target_indices = list(range(total_pages))

        page_results: list[PageContent] = []
        text_count = 0
        ocr_count = 0
        skipped_count = 0

        for idx in target_indices:
            page = doc[idx]
            page_content = self._extract_page(page, page_number=idx + 1)
            page_results.append(page_content)

            if page_content.extraction_method == 'text':
                text_count += 1
            elif page_content.extraction_method == 'ocr':
                ocr_count += 1
            else:
                skipped_count += 1

        full_text = '\n\n'.join(p.text for p in page_results if p.text)

        return PdfExtractionResult(
            filename=filename,
            total_pages=total_pages,
            pages=page_results,
            metadata=metadata,
            full_text=full_text,
            extraction_summary={
                'total_pages': total_pages,
                'extracted_pages': len(page_results),
                'text_pages': text_count,
                'ocr_pages': ocr_count,
                'skipped_pages': skipped_count,
                'total_chars': len(full_text),
                'ocr_available': self._enable_ocr,
            },
        )

    def _extract_page(self, page: fitz.Page, *, page_number: int) -> PageContent:
        """단일 페이지에서 텍스트를 추출합니다."""
        # 1차: 텍스트 레이어에서 직접 추출
        text = self._get_text_from_page(page)

        if len(text.strip()) >= _SCANNED_PAGE_CHAR_THRESHOLD:
            return PageContent(
                page_number=page_number,
                text=text.strip(),
                extraction_method='text',
            )

        # 2차: 텍스트가 부족 → OCR 시도
        if self._enable_ocr:
            logger.info('페이지 %d: 텍스트 부족, OCR 시도', page_number)
            ocr_text = self._extract_with_ocr(page)
            if ocr_text.strip():
                return PageContent(
                    page_number=page_number,
                    text=ocr_text.strip(),
                    extraction_method='ocr',
                )

        # 3차: 추출 가능한 텍스트가 없음
        if text.strip():
            return PageContent(
                page_number=page_number,
                text=text.strip(),
                extraction_method='text',
            )

        logger.warning('페이지 %d: 추출 가능한 텍스트가 없습니다.', page_number)
        return PageContent(
            page_number=page_number,
            text='',
            extraction_method='skipped',
        )

    @staticmethod
    def _get_text_from_page(page: fitz.Page) -> str:
        """PyMuPDF 텍스트 레이어에서 텍스트를 추출합니다.

        'blocks' 모드를 사용하여 텍스트 블록 순서를 보존하고,
        읽기 순서(위→아래, 좌→우)에 따라 정렬합니다.
        """
        blocks = page.get_text('blocks')  # (x0, y0, x1, y1, text, block_no, block_type)
        # block_type 0 = 텍스트, 1 = 이미지
        text_blocks = [b for b in blocks if b[6] == 0]

        # 읽기 순서 정렬: y좌표 우선 → x좌표 순
        text_blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))

        lines = []
        for block in text_blocks:
            block_text = block[4].strip()
            if block_text:
                lines.append(block_text)

        return '\n'.join(lines)

    def _extract_with_ocr(self, page: fitz.Page) -> str:
        """스캔 페이지를 이미지로 렌더링한 후 OCR로 텍스트를 추출합니다."""
        if not self._enable_ocr:
            return ''

        try:
            # 페이지를 고해상도 이미지로 렌더링
            mat = fitz.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)
            pix = page.get_pixmap(matrix=mat)

            img = Image.open(io.BytesIO(pix.tobytes('png')))

            text = pytesseract.image_to_string(img, lang=self._ocr_lang)
            return text

        except Exception as exc:
            logger.error('OCR 추출 실패: %s', exc)
            return ''

    @staticmethod
    def _extract_metadata(doc: fitz.Document) -> dict:
        """PDF 메타데이터를 추출합니다."""
        meta = doc.metadata or {}
        return {
            'title': meta.get('title', ''),
            'author': meta.get('author', ''),
            'subject': meta.get('subject', ''),
            'creator': meta.get('creator', ''),
            'producer': meta.get('producer', ''),
            'creation_date': meta.get('creationDate', ''),
            'modification_date': meta.get('modDate', ''),
            'page_count': len(doc),
        }


# ── Exception ────────────────────────────────────────────────

class PdfExtractionError(Exception):
    """PDF 추출 중 발생한 오류"""
