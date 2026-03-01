"""
PdfExtractor 단위 테스트
"""

import io
import unittest
from unittest.mock import MagicMock, patch

import fitz  # PyMuPDF

from services.pdf_extractor import (
    PageContent,
    PdfExtractionError,
    PdfExtractionResult,
    PdfExtractor,
)


def _create_text_pdf(pages_text: list[str]) -> bytes:
    """테스트용 텍스트 PDF를 메모리에서 생성합니다."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        # 텍스트 삽입 (한글 지원을 위해 helv 폰트 사용)
        tw = fitz.TextWriter(page.rect)
        tw.append((72, 72), text, fontsize=12)
        tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


def _create_empty_pdf(page_count: int = 1) -> bytes:
    """텍스트가 없는 빈 PDF를 생성합니다."""
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


class TestPageContent(unittest.TestCase):
    """PageContent 데이터 클래스 테스트"""

    def test_char_count_auto_calculated(self):
        pc = PageContent(page_number=1, text='Hello World', extraction_method='text')
        self.assertEqual(pc.char_count, 11)

    def test_empty_text(self):
        pc = PageContent(page_number=1, text='', extraction_method='skipped')
        self.assertEqual(pc.char_count, 0)


class TestPdfExtractionResult(unittest.TestCase):
    """PdfExtractionResult 직렬화 테스트"""

    def test_to_dict(self):
        result = PdfExtractionResult(
            filename='test.pdf',
            total_pages=1,
            pages=[
                PageContent(page_number=1, text='page one', extraction_method='text'),
            ],
            metadata={'title': 'Test'},
            full_text='page one',
            extraction_summary={'total_pages': 1},
        )
        d = result.to_dict()
        self.assertEqual(d['filename'], 'test.pdf')
        self.assertEqual(d['total_pages'], 1)
        self.assertEqual(len(d['pages']), 1)
        self.assertEqual(d['pages'][0]['page_number'], 1)
        self.assertEqual(d['pages'][0]['text'], 'page one')
        self.assertEqual(d['pages'][0]['extraction_method'], 'text')
        self.assertEqual(d['pages'][0]['char_count'], 8)
        self.assertEqual(d['metadata']['title'], 'Test')
        self.assertEqual(d['full_text'], 'page one')


class TestPdfExtractorFromBytes(unittest.TestCase):
    """PdfExtractor.extract_from_bytes 테스트"""

    def setUp(self):
        self.extractor = PdfExtractor(enable_ocr=False)

    def test_extract_single_page_text_pdf(self):
        pdf_data = _create_text_pdf(['This is a sample text for testing purpose and more words to pass threshold.'])
        result = self.extractor.extract_from_bytes(pdf_data, filename='test.pdf')

        self.assertEqual(result.filename, 'test.pdf')
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(len(result.pages), 1)
        self.assertIn('sample text', result.pages[0].text)
        self.assertEqual(result.pages[0].extraction_method, 'text')
        self.assertTrue(result.pages[0].char_count > 0)

    def test_extract_multi_page_pdf(self):
        pdf_data = _create_text_pdf([
            'First page has enough content for threshold to be met in the extractor module test.',
            'Second page also has enough content for threshold to be met in the extractor module test.',
            'Third page similarly has enough content for threshold to be met in the extractor module test.',
        ])
        result = self.extractor.extract_from_bytes(pdf_data)

        self.assertEqual(result.total_pages, 3)
        self.assertEqual(len(result.pages), 3)
        for i, page in enumerate(result.pages, 1):
            self.assertEqual(page.page_number, i)

    def test_extract_specific_pages(self):
        pdf_data = _create_text_pdf([
            'Page one text is long enough to pass the threshold for text extraction.',
            'Page two text is long enough to pass the threshold for text extraction.',
            'Page three text is long enough to pass the threshold for text extraction.',
        ])
        result = self.extractor.extract_from_bytes(pdf_data, pages=[1, 3])

        self.assertEqual(result.total_pages, 3)
        self.assertEqual(len(result.pages), 2)
        self.assertEqual(result.pages[0].page_number, 1)
        self.assertEqual(result.pages[1].page_number, 3)

    def test_extract_empty_pdf(self):
        pdf_data = _create_empty_pdf(2)
        result = self.extractor.extract_from_bytes(pdf_data)

        self.assertEqual(result.total_pages, 2)
        for page in result.pages:
            self.assertEqual(page.text, '')
            self.assertEqual(page.extraction_method, 'skipped')

    def test_empty_bytes_raises_error(self):
        with self.assertRaises(PdfExtractionError):
            self.extractor.extract_from_bytes(b'')

    def test_invalid_bytes_raises_error(self):
        with self.assertRaises(PdfExtractionError):
            self.extractor.extract_from_bytes(b'not a pdf at all')

    def test_metadata_extraction(self):
        pdf_data = _create_text_pdf(['Some text content that is long enough.'])
        result = self.extractor.extract_from_bytes(pdf_data)

        self.assertIn('title', result.metadata)
        self.assertIn('author', result.metadata)
        self.assertIn('page_count', result.metadata)
        self.assertEqual(result.metadata['page_count'], 1)

    def test_extraction_summary(self):
        pdf_data = _create_text_pdf([
            'Content for page one exceeds the threshold limit.',
        ])
        result = self.extractor.extract_from_bytes(pdf_data)

        summary = result.extraction_summary
        self.assertEqual(summary['total_pages'], 1)
        self.assertEqual(summary['extracted_pages'], 1)
        self.assertIn('total_chars', summary)
        self.assertIn('ocr_available', summary)

    def test_full_text_joins_pages(self):
        pdf_data = _create_text_pdf([
            'First page content is long enough to exceed the threshold for the test.',
            'Second page content is long enough to exceed the threshold for the test.',
        ])
        result = self.extractor.extract_from_bytes(pdf_data)

        self.assertIn('First page', result.full_text)
        self.assertIn('Second page', result.full_text)

    def test_out_of_range_pages_ignored(self):
        pdf_data = _create_text_pdf(['Only one page with enough text to pass threshold.'])
        result = self.extractor.extract_from_bytes(pdf_data, pages=[1, 5, 99])

        self.assertEqual(len(result.pages), 1)
        self.assertEqual(result.pages[0].page_number, 1)


class TestPdfExtractorFromPath(unittest.TestCase):
    """PdfExtractor.extract_from_path 테스트"""

    def setUp(self):
        self.extractor = PdfExtractor(enable_ocr=False)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.extractor.extract_from_path('/nonexistent/path/file.pdf')


class TestPdfExtractorOcr(unittest.TestCase):
    """OCR 관련 테스트 (모킹)"""

    def test_ocr_fallback_called_for_empty_text_page(self):
        """텍스트가 부족한 페이지에서 OCR이 호출되는지 확인"""
        import services.pdf_extractor as mod

        mock_tesseract = MagicMock()
        mock_tesseract.image_to_string.return_value = 'OCR extracted text that exceeds threshold'
        mock_image_mod = MagicMock()
        mock_image_mod.open.return_value = MagicMock()

        # pytesseract/Image가 미설치 상태이므로 모듈에 직접 주입
        original_ocr = getattr(mod, 'pytesseract', None)
        original_image = getattr(mod, 'Image', None)
        mod.pytesseract = mock_tesseract
        mod.Image = mock_image_mod

        try:
            with patch.object(mod, '_ocr_available', True):
                extractor = PdfExtractor(enable_ocr=True)
                extractor._enable_ocr = True

                pdf_data = _create_empty_pdf(1)
                result = extractor.extract_from_bytes(pdf_data)

                self.assertTrue(mock_tesseract.image_to_string.called)
        finally:
            # 원래 상태 복원
            if original_ocr is None:
                delattr(mod, 'pytesseract') if hasattr(mod, 'pytesseract') else None
            else:
                mod.pytesseract = original_ocr
            if original_image is None:
                delattr(mod, 'Image') if hasattr(mod, 'Image') else None
            else:
                mod.Image = original_image

    def test_ocr_disabled_by_default_when_not_installed(self):
        """pytesseract가 없으면 OCR이 비활성화되는지 확인"""
        with patch('services.pdf_extractor._ocr_available', False):
            extractor = PdfExtractor(enable_ocr=True)
            self.assertFalse(extractor._enable_ocr)


if __name__ == '__main__':
    unittest.main()
