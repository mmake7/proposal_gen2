"""Scoring Agent — 배점기준 추출.

전략:
  1. 결정적 검출기로 평가표 후보 식별 (헤더 키워드 + 정수 셀)
  2. 후보가 있으면 그 표 텍스트를 LLM에 강제 전달 (tail_sample 대신)
  3. 후보 없으면 tail_sample 폴백
  → 청원24 같은 큰 RFP에서 평가표가 본문 중간에 있어도 정확히 찾음.
"""

from __future__ import annotations

import logging
import re

from services_v2.agents.base import ClaudeAgent
from services_v2.documents.rfp_document import RfpDocument, TableRegion
from services_v2.results.rfp_analysis import ScoringItem

logger = logging.getLogger(__name__)


# 평가표 헤더 키워드 — 강한 신호
SCORING_HEADER_KEYWORDS = (
    '평가항목', '평가기준', '평가부문', '평가요소',
    '배점', '배점한도', '점수', '평가표', '심사기준',
)
# 일반 기술평가가 아닌 부속표 (제외)
SCORING_EXCLUDE_KEYWORDS = (
    '하도급', '하수급', '계약공정성', '하도급심사',
)
# 점수 셀 패턴 (1~100 정수, 옵션 '점' 접미사)
SCORE_CELL_PATTERN = re.compile(r'^\s*(\d{1,3})\s*점?\s*$')


class ScoringAgent(ClaudeAgent):
    name = 'scoring'
    prompt_file = 'scoring.md'
    max_tokens = 8192

    def extract(self, doc: RfpDocument, scoring_format: str = '') -> list[ScoringItem]:
        candidates = find_scoring_table_candidates(doc)
        if candidates:
            text = _candidates_to_text(candidates, max_chars=40_000)
            # 가격(입찰가격)평가는 별도 표/수식이라 후보 표에 없을 수 있다.
            # 본문 뒷부분을 추가 문맥으로 동봉해 기술+가격 합산(=100)이 가능하게 한다.
            tail = self._tail_sample(doc, max_chars=8_000)
            text += '\n\n--- 추가 문맥 (가격/입찰가격 평가 등 본문 뒷부분) ---\n' + tail
            text_source = f'평가표 후보 {len(candidates)}개 + 본문 뒷부분 문맥'
            logger.info('scoring: 결정적 평가표 후보 %d개 발견', len(candidates))
        else:
            text = self._tail_sample(doc, max_chars=40_000)
            text_source = 'RFP 뒷부분 샘플 (평가표 후보 없음)'
            logger.info('scoring: 평가표 후보 없음 — tail_sample 사용')

        user_parts = [f"파일명: {doc.filename}"]
        if scoring_format:
            user_parts.append(f"예상 배점 포맷: {scoring_format}")
        user_parts.append(f"\n--- {text_source} ---\n{text}")
        data = self.run('\n'.join(user_parts))

        items = []
        for s in data.get('scoring', []):
            try:
                score = int(s.get('score', 0))
            except (TypeError, ValueError):
                score = 0
            items.append(ScoringItem(
                category=s.get('category', ''),
                item=s.get('item', ''),
                criteria=s.get('criteria', ''),
                score=score,
            ))
        return items

    @staticmethod
    def _tail_sample(doc: RfpDocument, max_chars: int) -> str:
        if doc.total_chars <= max_chars:
            return doc.full_text
        return doc.full_text[-max_chars:]


def find_scoring_table_candidates(doc: RfpDocument) -> list[TableRegion]:
    """평가표 후보를 결정적 규칙으로 찾는다.

    조건:
      - 헤더에 '평가항목/평가기준/배점/배점한도/평가부문' 등 키워드
      - 헤더에 '하도급/하수급' 키워드 없음 (별개 부속표)
      - 정수 점수 셀 5개 이상

    반환 순서: 점수 셀이 많은 표 우선 (큰 평가표가 본 평가표일 가능성 높음).
    """
    scored: list[tuple[int, TableRegion]] = []
    for table in doc.table_regions:
        if not table.rows:
            continue
        header_text = ' '.join(
            ' '.join(c or '' for c in row) for row in table.rows[:2]
        )
        if not any(kw in header_text for kw in SCORING_HEADER_KEYWORDS):
            continue
        if any(kw in header_text for kw in SCORING_EXCLUDE_KEYWORDS):
            continue

        n_scores = 0
        for row in table.rows:
            for cell in row:
                if cell and SCORE_CELL_PATTERN.match(cell.strip()):
                    val = int(SCORE_CELL_PATTERN.match(cell.strip()).group(1))
                    if 1 <= val <= 100:
                        n_scores += 1
        if n_scores >= 5:
            scored.append((n_scores, table))

    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored]


def _candidates_to_text(tables: list[TableRegion], max_chars: int) -> str:
    """후보 표를 LLM 입력 텍스트로 직렬화.

    첫 후보는 점수 셀이 가장 많아 본 평가표일 가능성 큼 → max_chars 초과해도
    잘라서 무조건 포함. 두 번째 이후는 남은 공간에 들어가는 만큼만.
    """
    parts: list[str] = []
    total = 0
    for i, table in enumerate(tables, start=1):
        header = f'[평가표 후보 #{i}, page={table.page_number}, '\
                 f'{len(table.rows)}행 × {max(len(r) for r in table.rows)}열]'
        block = header + '\n' + table.text
        if i == 1:
            if len(block) > max_chars:
                block = block[:max_chars]
            parts.append(block)
            total += len(block)
            continue
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return '\n\n'.join(parts)
