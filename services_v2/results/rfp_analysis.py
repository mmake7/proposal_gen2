"""RfpAnalysisResult — 파이프라인 최종 산출물.

v1 (services/rfp_analyzer.py) `to_dict()` 출력 형식과 호환되어
기존 UI/엑셀/PPTX 코드를 변경 없이 재사용 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Overview:
    project_name: str = ''
    organization: str = ''
    period: str = ''
    budget: str = ''
    budget_unit: str = '백만원'
    contract_type: str = ''
    contract_method: str = ''
    qualifications: str = ''
    location: str = ''
    purpose: str = ''

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Requirement:
    """v1 RfpRequirement + v1 파서 확장 필드 통합."""
    id: str = ''
    name: str = ''
    category: str = ''
    desc: str = ''
    level: str = ''
    # 파서 확장
    category_code: str = ''
    definition: str = ''
    detail: str = ''
    output_info: str = ''
    related_reqs: str = ''
    source: str = ''
    parse_method: str = ''  # 'table' | 'narrative' | 'merged'

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ScoringItem:
    category: str = ''
    item: str = ''
    criteria: str = ''
    score: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class TocItem:
    level: int = 1
    number: str = ''
    title: str = ''
    description: str = ''
    children: list['TocItem'] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'level': self.level,
            'number': self.number,
            'title': self.title,
            'description': self.description,
            'children': [c.to_dict() for c in self.children],
        }


@dataclass
class RfpClassification:
    """Classifier Agent 산출물 — 후속 라우팅 결정."""
    org_type: str = ''                  # '행안부' | '지자체' | '공기업' | '교육청' | '기타'
    req_id_scheme: str = ''             # 'FR-NNN' | 'SFR-NN' | 'hierarchical' | 'none'
    req_format: str = ''                # 'table' | 'narrative' | 'mixed'
    scoring_format: str = ''            # 'table' | 'narrative' | 'mixed' | 'none'
    toc_location: str = ''              # 'front' | 'back' | 'scattered' | 'none'
    doc_size_tier: str = ''             # 'small' | 'medium' | 'large'
    language_dialect: str = ''          # 자유 텍스트 (어휘 특이점 메모)
    notes: str = ''

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class WbsPhase:
    """WBS 단계 (분석/설계 → 구축 → 테스트 → 운영)."""
    name: str = ''
    activities: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    duration_weeks: int = 0
    week_start: int = 0
    week_end: int = 0

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'activities': self.activities,
            'deliverables': self.deliverables,
            'duration_weeks': self.duration_weeks,
            'week_start': self.week_start,
            'week_end': self.week_end,
        }


@dataclass
class OrgRole:
    """조직도 직무."""
    role: str = ''         # 'PM', '응용SW개발자', 'UI/UX', 'IT지원' 등
    headcount: int = 0
    grade: str = ''        # '고급', '중급', '초급' (있으면)
    notes: str = ''        # '상주', '비상주' 등

    def to_dict(self) -> dict:
        return {
            'role': self.role,
            'headcount': self.headcount,
            'grade': self.grade,
            'notes': self.notes,
        }


@dataclass
class ManMonthLine:
    """직무별 M/M 산정 한 줄."""
    role: str = ''
    headcount: int = 0
    months: float = 0.0
    total_mm: float = 0.0   # headcount × months
    grade: str = ''

    def to_dict(self) -> dict:
        return {
            'role': self.role,
            'headcount': self.headcount,
            'months': self.months,
            'total_mm': self.total_mm,
            'grade': self.grade,
        }


@dataclass
class EstimationResult:
    """영업 견적 핵심 — WBS / 조직도 / M/M."""
    project_months: float = 0.0
    wbs: list[WbsPhase] = field(default_factory=list)
    organization: list[OrgRole] = field(default_factory=list)
    man_months: list[ManMonthLine] = field(default_factory=list)
    total_mm: float = 0.0
    notes: str = ''         # 산정 근거/가정

    def to_dict(self) -> dict:
        return {
            'project_months': self.project_months,
            'wbs': [w.to_dict() for w in self.wbs],
            'organization': [o.to_dict() for o in self.organization],
            'man_months': [m.to_dict() for m in self.man_months],
            'total_mm': self.total_mm,
            'notes': self.notes,
        }


@dataclass
class ValidationReport:
    confidence: float = 0.0             # 0.0 ~ 1.0
    issues: list[dict] = field(default_factory=list)
    retry_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'confidence': self.confidence,
            'issues': self.issues,
            'retry_targets': self.retry_targets,
        }


@dataclass
class RfpAnalysisResult:
    """v1 호환 + 메타 정보 부가."""
    overview: Overview | None = None
    requirements: list[Requirement] = field(default_factory=list)
    scoring: list[ScoringItem] = field(default_factory=list)
    toc: list[TocItem] = field(default_factory=list)
    classification: RfpClassification | None = None
    validation: ValidationReport | None = None
    estimation: EstimationResult | None = None
    agent_trace: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'overview': self.overview.to_dict() if self.overview else None,
            'requirements': [r.to_dict() for r in self.requirements],
            'scoring': [s.to_dict() for s in self.scoring],
            'toc': [t.to_dict() for t in self.toc],
            # v2 확장 필드 (v1 UI는 무시함)
            '_classification': self.classification.to_dict() if self.classification else None,
            '_validation': self.validation.to_dict() if self.validation else None,
            '_estimation': self.estimation.to_dict() if self.estimation else None,
            '_agent_trace': self.agent_trace,
        }
