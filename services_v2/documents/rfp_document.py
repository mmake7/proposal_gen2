"""RfpDocument — Stage 1 (Ingest) 산출물.

PDF에서 추출한 텍스트와 구조 정보를 후속 에이전트가 사용할 수 있는 형태로 보존.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TableRegion:
    """pdfplumber로 추출한 표의 한 영역."""
    page_number: int            # 1-based
    rows: list[list[str]]       # 셀 텍스트 행렬
    bbox: tuple[float, float, float, float] | None = None  # (x0, top, x1, bottom)

    @property
    def text(self) -> str:
        return '\n'.join('\t'.join(c or '' for c in row) for row in self.rows)


@dataclass
class PageInfo:
    """페이지 단위 메타 — 청크 분할/디버깅에 사용."""
    page_number: int
    text: str
    char_count: int = 0
    has_tables: bool = False
    extraction_method: str = 'text'  # 'text' | 'ocr'

    def __post_init__(self):
        self.char_count = len(self.text)


@dataclass
class RfpDocument:
    """파이프라인 전체에서 공유되는 RFP 문서 표현."""
    filename: str
    full_text: str
    pages: list[PageInfo] = field(default_factory=list)
    table_regions: list[TableRegion] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        return len(self.full_text)

    def pages_with_tables(self) -> list[int]:
        return sorted({t.page_number for t in self.table_regions})

    def to_summary(self) -> dict:
        return {
            'filename': self.filename,
            'total_pages': self.total_pages,
            'total_chars': self.total_chars,
            'table_count': len(self.table_regions),
            'ocr_pages': [p.page_number for p in self.pages if p.extraction_method == 'ocr'],
        }
