"""Validator의 결정적 검증 + dedup 단위 테스트 (LLM 미사용)."""

from __future__ import annotations

from services_v2.agents.validator import _dedupe_issues, ValidatorAgent
from services_v2.results.rfp_analysis import (
    Overview, Requirement, ScoringItem, TocItem,
)


# ── _dedupe_issues ──────────────────────────────────

class TestDedupe:
    def test_scoring_total_duplicate_collapsed(self):
        """LLM판 + deterministic판 둘 다 '배점 합계 100점이 아님' — 긴 쪽 유지."""
        issues = [
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 100점이 아님 (실제: 99). 항목 누락 의심'},
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 100점이 아님 (실제: 99)'},
        ]
        result = _dedupe_issues(issues)
        assert len(result) == 1
        assert '항목 누락 의심' in result[0]['message']

    def test_toc_empty_duplicate_collapsed(self):
        issues = [
            {'severity': 'error', 'field': 'toc',
             'message': 'TOC L1 항목이 비어있음 - 최소 1개 L1 챕터 필수'},
            {'severity': 'warning', 'field': 'toc',
             'message': 'TOC L1 항목이 비어있음'},
        ]
        result = _dedupe_issues(issues)
        assert len(result) == 1

    def test_different_keyword_same_field_kept_separately(self):
        """같은 field지만 다른 내용 — 둘 다 유지."""
        issues = [
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 100점이 아님 (실제: 99)'},
            {'severity': 'info', 'field': 'scoring',
             'message': 'scoring category에 정량/정성만 있음 (다른 RFP는 기술/가격)'},
        ]
        result = _dedupe_issues(issues)
        assert len(result) == 2

    def test_unknown_field_passthrough(self):
        """매칭 안 되는 field는 그대로 통과."""
        issues = [
            {'severity': 'info', 'field': 'meta',
             'message': '문서 크기 정보'},
            {'severity': 'info', 'field': 'meta',
             'message': '다른 정보'},
        ]
        result = _dedupe_issues(issues)
        assert len(result) == 2

    def test_empty_input(self):
        assert _dedupe_issues([]) == []

    def test_scoring_dedup_with_varied_wording(self):
        """KIAT E2E에서 발견된 실제 케이스 — 다른 wording이지만 같은 사실."""
        issues = [
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계가 99점으로 100점이 아님 (1점 부족)'},
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 100점이 아님 (실제: 99)'},
        ]
        result = _dedupe_issues(issues)
        # 두 issue 모두 '합계' 키워드 매칭 → 한 그룹으로 묶임
        assert len(result) == 1
        # 더 긴 메시지(부족/실제 등 부가정보 포함) 유지
        assert len(result[0]['message']) >= 20

    def test_scoring_dedup_total_over_100(self):
        """청원24 케이스 — 135점 초과 메시지도 dedup."""
        issues = [
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 135점으로 100점 초과. 하도급 평가 의심'},
            {'severity': 'warning', 'field': 'scoring',
             'message': '배점 합계 100점이 아님 (실제: 135)'},
        ]
        result = _dedupe_issues(issues)
        assert len(result) == 1


# ── deterministic checks ─────────────────────────────

class TestDeterministicChecks:
    agent = ValidatorAgent()

    def test_missing_project_name(self):
        issues = self.agent._deterministic_checks(
            overview=Overview(),  # project_name 비어있음
            requirements=[], scoring=[], toc=[],
        )
        assert any('project_name' in i['message'] for i in issues)

    def test_duplicate_ids(self):
        reqs = [
            Requirement(id='FR-001', name='a'),
            Requirement(id='FR-001', name='b'),  # 중복
            Requirement(id='FR-002', name='c'),
        ]
        issues = self.agent._deterministic_checks(
            overview=Overview(project_name='x'), requirements=reqs,
            scoring=[], toc=[],
        )
        dup_issues = [i for i in issues if 'ID 중복' in i['message']]
        assert len(dup_issues) == 1
        assert 'FR-001' in dup_issues[0]['message']

    def test_scoring_total_not_100(self):
        scoring = [ScoringItem(item='a', score=30), ScoringItem(item='b', score=50)]
        issues = self.agent._deterministic_checks(
            overview=Overview(project_name='x'), requirements=[],
            scoring=scoring, toc=[],
        )
        assert any('80' in i['message'] for i in issues)  # 실제 합계 80

    def test_empty_toc_flagged(self):
        issues = self.agent._deterministic_checks(
            overview=Overview(project_name='x'), requirements=[],
            scoring=[], toc=[],
        )
        assert any('비어' in i['message'] for i in issues)

    def test_clean_state_no_issues(self):
        issues = self.agent._deterministic_checks(
            overview=Overview(project_name='OK'),
            requirements=[Requirement(id='FR-001', name='a')],
            scoring=[
                ScoringItem(item='a', score=50),
                ScoringItem(item='b', score=50),
            ],
            toc=[TocItem(title='Ⅰ. 사업개요')],
        )
        assert issues == []
