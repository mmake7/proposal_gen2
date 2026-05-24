"""견적 휴리스틱 단위 테스트 (LLM 미사용)."""

from __future__ import annotations

import pytest

from services_v2.estimation.heuristic import (
    build_wbs_from_toc, estimate_from_analysis,
    extract_org_from_requirements, parse_project_months,
)
from services_v2.results.rfp_analysis import (
    Overview, Requirement, RfpAnalysisResult,
)


# ── 기간 파싱 ───────────────────────────────────────────

class TestParseProjectMonths:
    @pytest.mark.parametrize('text,expected', [
        ('12개월', 12),
        ('(12개월)', 12),
        ('24개월 사업', 24),
        ('계약일로부터 120일', 4.0),  # 120/30
        ('2024.01.01 ~ 2024.12.31', 12),
        ('2024.01 ~ 2024.12', 12),
        ('2026.04 ~ 2026.12', 9),
        ('2024.01.01 ~ 2024.06.30 (6개월)', 6),  # '개월' 우선
    ])
    def test_known_patterns(self, text, expected):
        assert parse_project_months(text) == expected

    def test_empty_returns_zero(self):
        assert parse_project_months('') == 0.0
        assert parse_project_months('미정') == 0.0


# ── 인력 추출 ───────────────────────────────────────────

class TestExtractOrg:
    def test_kiat_format(self):
        """KIAT MHR-001 형식 — '1) IT PM : 1명' 패턴."""
        reqs = [Requirement(
            id='MHR-001',
            detail='''○ 투입 인력 인원수
1) IT PM : 1명
2) 응용SW개발자 : 15명
3) UI/UX 디자이너 : 1명
4) IT지원기술자 : 5명'''
        )]
        org = extract_org_from_requirements(reqs)
        roles = {o.role: o.headcount for o in org}
        assert roles.get('PM') == 1
        assert roles.get('응용SW 개발자') == 15
        assert roles.get('UI/UX 디자이너') == 1
        assert roles.get('IT 지원기술자') == 5

    def test_max_wins_when_duplicated(self):
        """같은 직무가 여러 항목에 등장하면 최대값."""
        reqs = [
            Requirement(detail='PM 1명'),
            Requirement(detail='PM 3명'),
        ]
        org = extract_org_from_requirements(reqs)
        roles = {o.role: o.headcount for o in org}
        assert roles.get('PM') == 3

    def test_noise_filtered(self):
        """비-직무 단어 (시스템명 등)는 normalize에서 제거."""
        reqs = [Requirement(detail='대외시스템 4명, 대내시스템 4명')]
        org = extract_org_from_requirements(reqs)
        # 시스템명은 직무 아님
        assert org == []

    def test_unrealistic_count_excluded(self):
        """비현실적 인원 (51+ 또는 0)은 제외."""
        reqs = [Requirement(detail='PM 100명, 디자이너 0명')]
        org = extract_org_from_requirements(reqs)
        assert org == []

    def test_empty_requirements(self):
        assert extract_org_from_requirements([]) == []


# ── WBS ─────────────────────────────────────────────────

class TestWbs:
    def test_standard_4_phases(self):
        wbs = build_wbs_from_toc([], project_months=12)
        assert len(wbs) == 4
        names = [p.name for p in wbs]
        assert '분석/설계' in names and '구축/개발' in names
        # 총 주차 = 12개월 × 4 = 48주
        assert sum(p.duration_weeks for p in wbs) == 48

    def test_zero_months_no_weeks(self):
        wbs = build_wbs_from_toc([], project_months=0)
        assert len(wbs) == 4
        assert all(p.duration_weeks == 0 for p in wbs)

    def test_week_ranges_sequential(self):
        wbs = build_wbs_from_toc([], project_months=12)
        # week_start, week_end가 연속적
        prev_end = 0
        for p in wbs:
            assert p.week_start == prev_end + 1
            prev_end = p.week_end


# ── 통합 estimate_from_analysis ─────────────────────────

class TestEstimateFromAnalysis:
    def test_kiat_full_pipeline(self):
        result = RfpAnalysisResult(
            overview=Overview(period='2026.01 ~ 2027.12 (24개월)'),
            requirements=[Requirement(
                id='MHR-001',
                detail='1) IT PM : 1명\n2) 응용SW개발자 : 15명\n'
                       '3) UI/UX 디자이너 : 1명\n4) IT지원기술자 : 5명',
            )],
        )
        est = estimate_from_analysis(result)
        assert est.project_months == 24
        assert len(est.organization) == 4
        # 총 M/M = (1+15+1+5) × 24 = 528
        assert est.total_mm == 528.0
        # 4 WBS 단계
        assert len(est.wbs) == 4
        # 각 M/M 라인이 정확히 계산됨
        pm = next(m for m in est.man_months if m.role == 'PM')
        assert pm.headcount == 1
        assert pm.months == 24
        assert pm.total_mm == 24.0

    def test_empty_overview(self):
        result = RfpAnalysisResult(
            overview=Overview(period=''),
            requirements=[],
        )
        est = estimate_from_analysis(result)
        assert est.project_months == 0
        assert est.total_mm == 0
        # WBS는 4단계지만 duration_weeks=0
        assert len(est.wbs) == 4
        assert all(p.duration_weeks == 0 for p in est.wbs)
        # notes에 사유
        assert '기간' in est.notes or '인력' in est.notes

    def test_no_period_with_org(self):
        result = RfpAnalysisResult(
            overview=Overview(period=''),
            requirements=[Requirement(detail='PM 1명')],
        )
        est = estimate_from_analysis(result)
        # 인력 1명, 기간 0 → M/M 0
        assert len(est.organization) == 1
        assert est.total_mm == 0
