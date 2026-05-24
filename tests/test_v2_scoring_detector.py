"""Scoring 평가표 결정적 검출기 단위 테스트 (LLM 미사용)."""

from __future__ import annotations

from services_v2.agents.scoring import (
    find_scoring_table_candidates, _candidates_to_text,
)
from services_v2.documents.rfp_document import RfpDocument, TableRegion


def make_doc(*tables: TableRegion) -> RfpDocument:
    return RfpDocument(
        filename='unit.pdf', full_text='', pages=[], table_regions=list(tables),
    )


def eval_table(*data_rows, header=None):
    """기본 평가표 헬퍼."""
    header = header or ['평가항목', '평가기준', '배점']
    return TableRegion(page_number=1, rows=[header, *data_rows])


# ── 정상 평가표 인식 ─────────────────────────────────────

class TestDetector:
    def test_standard_eval_table_detected(self):
        t = eval_table(
            ['사업이해도', '사업 목적과 범위 이해', '10'],
            ['추진전략', '전략의 타당성', '15'],
            ['기술방안', '구현 방안의 구체성', '20'],
            ['추진체계', '조직 구성', '15'],
            ['관리방안', '품질·일정·위험', '10'],
            ['지원체계', '인프라', '15'],
            ['특화방안', '차별성', '15'],
        )
        cands = find_scoring_table_candidates(make_doc(t))
        assert len(cands) == 1
        assert cands[0] is t

    def test_header_with_변형_keywords(self):
        # 다양한 헤더 표현
        for header in [
            ['구분', '평가항목', '세부평가항목', '평가기준', '배점한도'],
            ['평가부문', '평가항목', '평가기준', '배점'],
            ['평가요소', '평가기준', '점수'],
        ]:
            t = TableRegion(page_number=1, rows=[
                header,
                *[['x', 'y', 'z', '10']] * 5,
            ])
            cands = find_scoring_table_candidates(make_doc(t))
            assert len(cands) >= 1, f'헤더 {header} 인식 실패'


# ── 비평가표 거부 ───────────────────────────────────────

class TestNonEvalRejection:
    def test_no_eval_keyword_in_header_rejected(self):
        # 점수 같은 정수가 많지만 헤더에 평가 키워드 없음
        t = TableRegion(page_number=1, rows=[
            ['번호', '시스템명', '구분', 'URL'],
            ['1', 'a', '대외', 'x'],
            ['2', 'b', '대내', 'y'],
            ['3', 'c', '대외', 'z'],
            ['4', 'd', '대내', 'w'],
            ['5', 'e', '대외', 'v'],
        ])
        assert find_scoring_table_candidates(make_doc(t)) == []

    def test_subcontract_table_excluded(self):
        """청원24 함정 — 하도급 심사표는 제외."""
        t = TableRegion(page_number=1, rows=[
            ['평가항목', '하도급 평가기준', '배점'],
            ['하도급 대금지급방식', '...', '30'],
            ['하도급 금액의 적정성', '...', '30'],
            ['고용안정 및 적법근로', '...', '10'],
            ['(재)하수급인 사업수행', '...', '30'],
            ['실적 비율', '...', '20'],
        ])
        # 헤더에 '하도급' 들어가서 제외
        assert find_scoring_table_candidates(make_doc(t)) == []

    def test_few_integer_cells_rejected(self):
        """평가 키워드 있지만 정수 셀이 너무 적음."""
        t = TableRegion(page_number=1, rows=[
            ['평가항목', '평가기준'],
            ['항목1', '설명1'],
            ['항목2', '설명2'],
            ['항목3', '설명3'],
        ])
        # 정수 셀 0개 → 제외
        assert find_scoring_table_candidates(make_doc(t)) == []

    def test_empty_table_safe(self):
        assert find_scoring_table_candidates(make_doc()) == []


# ── 정렬 (점수 셀 많은 표 우선) ────────────────────────

class TestOrdering:
    def test_more_scores_first(self):
        small = TableRegion(page_number=1, rows=[
            ['평가항목', '배점'],
            ['a', '10'], ['b', '20'], ['c', '30'],
            ['d', '40'], ['e', '5'],
        ])
        large = TableRegion(page_number=2, rows=[
            ['평가항목', '평가기준', '배점'],
            *[['x', 'y', str(i)] for i in (5, 10, 15, 20, 25, 10, 5)],
        ])
        cands = find_scoring_table_candidates(make_doc(small, large))
        assert cands[0] is large  # 점수 7개 > 5개


# ── 텍스트 직렬화 ──────────────────────────────────────

class TestCandidatesToText:
    def test_format_includes_table_header(self):
        t = eval_table(['a', 'b', '10'], ['c', 'd', '20'])
        text = _candidates_to_text([t], max_chars=10_000)
        assert '[평가표 후보 #1' in text
        assert '평가항목' in text
        assert '10' in text

    def test_first_candidate_truncated_if_too_large(self):
        """첫 후보는 max_chars 초과해도 잘라서 무조건 포함."""
        large_rows = [['항목' * 50, '기준' * 50, '10']] * 100
        t = TableRegion(page_number=1, rows=[
            ['평가항목', '평가기준', '배점'],
            *large_rows,
        ])
        text = _candidates_to_text([t], max_chars=1_000)
        assert '평가표 후보 #1' in text
        assert len(text) <= 1_000

    def test_subsequent_candidate_dropped_if_no_room(self):
        """두 번째 후보부터는 남은 공간에 안 맞으면 제외."""
        large_rows = [['항목' * 50, '기준' * 50, '10']] * 100
        t1 = TableRegion(page_number=1, rows=[
            ['평가항목', '평가기준', '배점'],
            *large_rows,
        ])
        t2 = eval_table(['x', 'y', '10'])
        text = _candidates_to_text([t1, t2], max_chars=1_000)
        # t1만 포함, t2는 잘림
        assert '평가표 후보 #1' in text
        assert '평가표 후보 #2' not in text
