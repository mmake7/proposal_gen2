"""Validator Agent — 추출 결과 일관성/완전성 검증."""

from __future__ import annotations

import json

from services_v2.agents.base import ClaudeAgent
from services_v2.results.rfp_analysis import (
    Overview, Requirement, ScoringItem, TocItem, ValidationReport,
)


# Deterministic issue와 LLM issue가 같은 사실을 다른 표현으로 보고할 때 dedup.
# 키워드는 짧은 단어 1개로 단순화 — 키워드 우선순위 충돌 방지.
# field 별로 한 그룹의 사실만 키워드로 묶임.
DEDUPE_KEYWORDS: dict[str, list[str]] = {
    'overview': ['project_name', '핵심 필드'],
    'requirements': ['중복'],            # ID 중복
    'scoring': ['합계'],                  # 배점 합계 100점이 아님/초과/부족 모두 잡힘
    'toc': ['비어'],                      # L1 비어있음 / TOC 비어 모두 잡힘
}


def _dedupe_issues(issues: list[dict]) -> list[dict]:
    """같은 (field, 키워드) 그룹의 issue들 중 가장 긴 메시지만 유지.

    Deterministic 룰과 LLM이 같은 사실(예: '배점 합계 100점 아님')을
    독립적으로 보고하는 거품을 정리.
    """
    grouped: dict[tuple[str, str], dict] = {}
    others: list[dict] = []
    for issue in issues:
        field = issue.get('field', '')
        msg = issue.get('message', '')
        matched_kw: str | None = None
        for kw in DEDUPE_KEYWORDS.get(field, []):
            if kw in msg:
                matched_kw = kw
                break
        if matched_kw is not None:
            key = (field, matched_kw)
            existing = grouped.get(key)
            if existing is None or len(msg) > len(existing.get('message', '')):
                grouped[key] = issue
        else:
            others.append(issue)
    return [*grouped.values(), *others]


class ValidatorAgent(ClaudeAgent):
    name = 'validator'
    prompt_file = 'validator.md'
    max_tokens = 2048

    def validate(
        self,
        *,
        overview: Overview | None,
        requirements: list[Requirement],
        scoring: list[ScoringItem],
        toc: list[TocItem],
    ) -> ValidationReport:
        # 결정적(determinic) 사전 검증 — LLM 호출 전 빠른 체크
        prelim_issues = self._deterministic_checks(overview, requirements, scoring, toc)

        payload = {
            'overview': overview.to_dict() if overview else None,
            'requirements_summary': {
                'count': len(requirements),
                'ids': [r.id for r in requirements][:50],
                'categories': sorted({r.category for r in requirements if r.category}),
            },
            'scoring_summary': {
                'count': len(scoring),
                'total_score': sum(s.score for s in scoring),
                'items': [
                    {'category': s.category, 'item': s.item, 'score': s.score}
                    for s in scoring
                ],
            },
            'toc_summary': {
                'l1_count': len(toc),
                'l1_titles': [t.title for t in toc],
            },
            'deterministic_issues': prelim_issues,
        }
        user = (
            "다음은 다른 에이전트들이 추출한 RFP 분석 결과 요약입니다. "
            "이를 검증하고 신뢰도와 이슈를 반환하세요.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        data = self.run(user)

        # LLM issues + deterministic issues 합치고 키워드 기반 dedup
        merged = list(data.get('issues', [])) + list(prelim_issues)
        report = ValidationReport(
            confidence=float(data.get('confidence', 0.0)),
            issues=_dedupe_issues(merged),
            retry_targets=list(data.get('retry_targets', [])),
        )
        return report

    @staticmethod
    def _deterministic_checks(
        overview: Overview | None,
        requirements: list[Requirement],
        scoring: list[ScoringItem],
        toc: list[TocItem],
    ) -> list[dict]:
        issues: list[dict] = []

        if overview is None or not overview.project_name:
            issues.append({
                'severity': 'error',
                'field': 'overview',
                'message': 'project_name 누락',
            })

        # 요구사항 ID 중복
        ids = [r.id for r in requirements if r.id]
        duplicates = {x for x in ids if ids.count(x) > 1}
        if duplicates:
            issues.append({
                'severity': 'warning',
                'field': 'requirements',
                'message': f'ID 중복: {sorted(duplicates)[:10]}',
            })

        # 배점 합계
        total = sum(s.score for s in scoring)
        if scoring and total != 100:
            issues.append({
                'severity': 'warning',
                'field': 'scoring',
                'message': f'배점 합계 100점이 아님 (실제: {total})',
            })

        # TOC 비어있음
        if not toc:
            issues.append({
                'severity': 'warning',
                'field': 'toc',
                'message': 'TOC L1 항목이 비어있음',
            })

        return issues
