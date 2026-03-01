"""
TOC ↔ Template Chapter Mapper
확정된 TOC 항목과 PPTX 템플릿 챕터를 매핑합니다.

difflib.SequenceMatcher를 사용한 퍼지 매칭으로
TOC 대분류(L1)와 템플릿 챕터를 자동 연결합니다.
"""

import difflib
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MapperError(Exception):
    """매핑 중 발생하는 에러"""


# ── Session State ─────────────────────────────────────────
_current_mapping: list[dict] | None = None
_template_id: str | None = None


def _normalize_title(title: str) -> str:
    """매칭을 위해 제목을 정규화합니다."""
    import re
    # 번호(로마숫자, 아라비아숫자, 한글 등) 및 구분자 제거
    s = re.sub(r'^[IVXivxⅠ-Ⅻⅰ-ⅻ\d]+[\.\s\-\:·]+', '', title.strip())
    s = re.sub(r'^제?\d+장[\.\s\:]+', '', s)
    s = re.sub(r'^Part\s*\d+[\.\s\:]+', '', s, flags=re.IGNORECASE)
    # 공백 정규화
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _calc_similarity(a: str, b: str) -> float:
    """두 문자열 사이의 유사도를 계산합니다 (0.0 ~ 1.0)."""
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def map_toc_to_template(
    toc_items: list[dict],
    template_detail: dict,
) -> list[dict]:
    """TOC L1 항목을 템플릿 챕터에 자동 매핑합니다.

    Args:
        toc_items: 확정된 TOC 항목 리스트 (L1 레벨)
        template_detail: 템플릿 상세 정보 (get_template_detail 반환값)

    Returns:
        매핑 결과 리스트. 각 항목:
        {
            "toc_index": int,
            "toc_title": str,
            "chapter_index": int | None,
            "chapter_title": str,
            "slides": list[int],
            "score": float,
            "status": "matched" | "unmatched" | "manual"
        }
    """
    global _current_mapping, _template_id

    chapters = template_detail.get('chapters', [])
    _template_id = template_detail.get('id')

    mapping = []
    used_chapters = set()

    for toc_idx, toc_item in enumerate(toc_items):
        toc_title = toc_item.get('title', '')

        best_score = 0.0
        best_ch_idx = None

        for ch_idx, chapter in enumerate(chapters):
            if ch_idx in used_chapters:
                continue
            ch_title = chapter.get('title', '')
            score = _calc_similarity(toc_title, ch_title)
            if score > best_score:
                best_score = score
                best_ch_idx = ch_idx

        threshold = 0.4
        if best_score >= threshold and best_ch_idx is not None:
            chapter = chapters[best_ch_idx]
            used_chapters.add(best_ch_idx)
            mapping.append({
                'toc_index': toc_idx,
                'toc_title': toc_title,
                'chapter_index': best_ch_idx,
                'chapter_title': chapter.get('title', ''),
                'slides': _get_chapter_slides(chapter),
                'score': round(best_score, 3),
                'status': 'matched',
            })
        else:
            mapping.append({
                'toc_index': toc_idx,
                'toc_title': toc_title,
                'chapter_index': None,
                'chapter_title': '',
                'slides': [],
                'score': round(best_score, 3) if best_ch_idx is not None else 0.0,
                'status': 'unmatched',
            })

    _current_mapping = mapping
    return mapping


def _get_chapter_slides(chapter: dict) -> list[int]:
    """챕터에 속한 슬라이드 번호 리스트를 반환합니다."""
    slides = chapter.get('slides', [])
    if isinstance(slides, list):
        return [s.get('slide_number', 0) if isinstance(s, dict) else s for s in slides]
    return []


def get_mapping() -> list[dict] | None:
    """현재 매핑 상태를 반환합니다."""
    return _current_mapping


def get_template_id() -> str | None:
    """현재 매핑에 사용된 템플릿 ID를 반환합니다."""
    return _template_id


def update_mapping(toc_index: int, chapter_index: int | None) -> list[dict]:
    """매핑을 수동으로 수정합니다.

    Args:
        toc_index: TOC 항목 인덱스
        chapter_index: 연결할 챕터 인덱스 (None이면 매핑 해제)
    """
    global _current_mapping
    if _current_mapping is None:
        raise MapperError('매핑 데이터가 없습니다. 먼저 매핑을 실행해주세요.')

    for entry in _current_mapping:
        if entry['toc_index'] == toc_index:
            if chapter_index is not None:
                entry['chapter_index'] = chapter_index
                entry['status'] = 'manual'
                entry['score'] = 1.0
            else:
                entry['chapter_index'] = None
                entry['chapter_title'] = ''
                entry['slides'] = []
                entry['status'] = 'unmatched'
                entry['score'] = 0.0
            break
    else:
        raise MapperError(f'TOC 인덱스 {toc_index}에 해당하는 매핑을 찾을 수 없습니다.')

    return _current_mapping


def reset_mapping():
    """매핑 상태를 초기화합니다."""
    global _current_mapping, _template_id
    _current_mapping = None
    _template_id = None
