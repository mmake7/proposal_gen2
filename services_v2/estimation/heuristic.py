"""결정적 견적 추출 — 분석 결과에서 인력·기간·WBS 도출.

전략:
  - 기간: overview.period 파싱 (예: "2024.01.01 ~ 2024.12.31" → 12개월)
  - 조직도: requirements 중 MHR/인력 요구사항에서 "PM 1명, 개발자 5명" 패턴 추출
  - WBS: TOC L1 챕터를 단계로 매핑 + 표준 SI 4단계 폴백
  - M/M: 조직도 × 기간

LLM 없이 작동. 추출 정확도는 RFP에 인력 정보가 명시되어야 높음.
한도 회복 후 LLM 에이전트로 보강 가능 (services_v2/estimation/llm.py 추후).
"""

from __future__ import annotations

import re
from datetime import date

from services_v2.results.rfp_analysis import (
    EstimationResult, ManMonthLine, OrgRole, RfpAnalysisResult, WbsPhase,
)


# ── 기간 파싱 ─────────────────────────────────────────────

PERIOD_PATTERNS = [
    # "12개월", "(12개월)", "24개월", "5개월"
    re.compile(r'(\d{1,3})\s*개월'),
    # "120일", "180일"
    re.compile(r'(\d{2,4})\s*일'),
]

DATE_RANGE_PATTERNS = [
    # "2024.01.01 ~ 2024.12.31"
    re.compile(
        r'(\d{4})[./\-](\d{1,2})[./\-]?(\d{1,2})?\s*[~∼\-]\s*'
        r'(\d{4})[./\-](\d{1,2})[./\-]?(\d{1,2})?'
    ),
    # "2024.01 ~ 2024.12"
    re.compile(r'(\d{4})[.\-](\d{1,2})\s*[~∼\-]\s*(\d{4})[.\-](\d{1,2})'),
]


def parse_project_months(period_text: str) -> float:
    """overview.period 텍스트에서 사업 기간을 개월 단위로 산정."""
    if not period_text:
        return 0.0
    text = period_text.strip()

    # 1) 명시적 N개월
    for pat in PERIOD_PATTERNS[:1]:  # '개월' 패턴 우선
        m = pat.search(text)
        if m:
            return float(m.group(1))
    # 1b) N일 → /30
    m = PERIOD_PATTERNS[1].search(text)
    if m:
        return round(int(m.group(1)) / 30, 1)

    # 2) 날짜 범위 → diff
    for pat in DATE_RANGE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if len(m.groups()) == 6:
                y1, mo1, _, y2, mo2, _ = m.groups()
            else:
                y1, mo1, y2, mo2 = m.groups()
            months = (int(y2) - int(y1)) * 12 + (int(mo2) - int(mo1)) + 1
            return float(max(months, 0))
        except (TypeError, ValueError):
            continue
    return 0.0


# ── 인력 패턴 추출 ────────────────────────────────────────

# "PM 1명", "응용SW개발자 : 15명", "사업관리자 1명" 등
ROLE_HEADCOUNT_PATTERN = re.compile(
    r'(?:^|\s|[•○◯❍■◆▪▫\-])\s*'
    r'([A-Za-z가-힣/\s]+?)'
    r'\s*[:\s]\s*'
    r'(\d{1,3})\s*명'
)

# 직무 정규화 — 다양한 표기를 표준으로
ROLE_ALIASES: dict[str, str] = {
    'IT PM': 'PM',
    'PM': 'PM',
    '사업관리자': 'PM',
    '프로젝트 관리자': 'PM',
    '응용SW개발자': '응용SW 개발자',
    'SW개발자': '응용SW 개발자',
    'SW 개발자': '응용SW 개발자',
    '개발자': '응용SW 개발자',
    'UI/UX 디자이너': 'UI/UX 디자이너',
    'UI/UX': 'UI/UX 디자이너',
    'IT지원기술자': 'IT 지원기술자',
    'IT 지원기술자': 'IT 지원기술자',
    '기술지원': 'IT 지원기술자',
    '품질관리': '품질관리자',
    'QA': '품질관리자',
}

# 자주 등장하는 직무 키워드 (alias에 없어도 통과)
KNOWN_ROLE_KEYWORDS = (
    'PM', '개발자', '디자이너', '관리자', '기술자', '지원',
    '컨설턴트', '분석가', '설계자', '엔지니어', '운영자',
)


def _normalize_role(raw: str) -> str:
    """직무명 정규화."""
    cleaned = raw.strip().strip(':').strip()
    if not cleaned:
        return ''
    # 정확 매칭
    if cleaned in ROLE_ALIASES:
        return ROLE_ALIASES[cleaned]
    # 부분 매칭
    for alias, std in ROLE_ALIASES.items():
        if alias in cleaned:
            return std
    # 직무 키워드 포함이면 그대로
    if any(kw in cleaned for kw in KNOWN_ROLE_KEYWORDS):
        return cleaned
    return ''


def extract_org_from_requirements(requirements: list) -> list[OrgRole]:
    """requirements에서 직무·인원 패턴을 누적 추출."""
    role_counts: dict[str, int] = {}
    for req in requirements:
        text = ' '.join(filter(None, [
            getattr(req, 'detail', ''),
            getattr(req, 'definition', ''),
            getattr(req, 'desc', ''),
        ]))
        if not text:
            continue
        for m in ROLE_HEADCOUNT_PATTERN.finditer(text):
            raw_role = m.group(1)
            count = int(m.group(2))
            if count < 1 or count > 50:  # 비현실적 값 제외
                continue
            std_role = _normalize_role(raw_role)
            if not std_role:
                continue
            # 같은 역할 여러 번 — 최대값 채택 (한 곳에 1명, 다른 곳에 5명이면 5)
            role_counts[std_role] = max(role_counts.get(std_role, 0), count)

    return [
        OrgRole(role=role, headcount=count)
        for role, count in sorted(role_counts.items(), key=lambda x: -x[1])
    ]


# ── WBS ─────────────────────────────────────────────────

# 표준 SI 4단계 (기간 비율 — 합 1.0)
STANDARD_WBS = [
    ('분석/설계', 0.25, ['요구사항 분석', '아키텍처 설계', 'DB 설계'],
     ['요구사항 정의서', '시스템 설계서', 'DB 설계서']),
    ('구축/개발', 0.45, ['응용 SW 개발', '인프라 구축', '연계 개발'],
     ['소스코드', '시스템 매뉴얼', '연계 명세서']),
    ('테스트', 0.15, ['단위/통합 테스트', '성능 테스트', '보안 점검'],
     ['테스트 계획서', '테스트 결과서']),
    ('이행/안정화', 0.15, ['데이터 이관', '교육', '안정화 운영'],
     ['이행 계획서', '교육 자료', '운영 매뉴얼']),
]


def build_wbs_from_toc(
    toc_items: list,
    project_months: float,
) -> list[WbsPhase]:
    """TOC L1을 단계로 매핑. TOC가 없거나 약하면 표준 4단계 폴백."""
    total_weeks = max(int(project_months * 4), 1) if project_months > 0 else 0

    # TOC 기반 추출은 약함 (TOC는 제안서 챕터, WBS는 사업 단계로 다름) → 폴백 우선
    phases: list[WbsPhase] = []
    cur_week = 1
    accumulated = 0
    for idx, (name, ratio, acts, dels) in enumerate(STANDARD_WBS):
        if not total_weeks:
            weeks = 0
        elif idx == len(STANDARD_WBS) - 1:
            # 마지막 단계는 잔여를 흡수해 비율 절삭으로 인한 합계 불일치 방지
            weeks = max(total_weeks - accumulated, 1)
        else:
            weeks = max(int(total_weeks * ratio), 1)
        accumulated += weeks
        phases.append(WbsPhase(
            name=name,
            activities=acts,
            deliverables=dels,
            duration_weeks=weeks,
            week_start=cur_week if weeks else 0,
            week_end=(cur_week + weeks - 1) if weeks else 0,
        ))
        cur_week += weeks
    return phases


# ── 통합 진입점 ───────────────────────────────────────────

def estimate_from_analysis(result: RfpAnalysisResult) -> EstimationResult:
    """분석 결과 → 견적 (WBS/조직도/M/M)."""
    period_text = result.overview.period if result.overview else ''
    project_months = parse_project_months(period_text)

    organization = extract_org_from_requirements(result.requirements or [])

    wbs = build_wbs_from_toc(result.toc or [], project_months)

    # M/M = 직무별 headcount × 사업 기간(개월)
    man_months: list[ManMonthLine] = []
    total = 0.0
    for org in organization:
        mm = round(org.headcount * project_months, 1) if project_months else 0.0
        total += mm
        man_months.append(ManMonthLine(
            role=org.role,
            headcount=org.headcount,
            months=project_months,
            total_mm=mm,
            grade=org.grade,
        ))

    notes_parts = []
    if not period_text:
        notes_parts.append('사업 기간 정보 없음 — overview.period 미설정')
    elif project_months == 0:
        notes_parts.append(f'기간 텍스트 파싱 실패: "{period_text[:60]}"')
    if not organization:
        notes_parts.append('인력 요건 미발견 — RFP에 직무·인원 표기 부족 가능')
    if not notes_parts:
        notes_parts.append(
            f'기간 {project_months:.0f}개월, '
            f'직무 {len(organization)}종, 총 {total:.1f} M/M로 산정 '
            '(결정적 휴리스틱 — RFP 명시 인력 기준)'
        )

    return EstimationResult(
        project_months=project_months,
        wbs=wbs,
        organization=organization,
        man_months=man_months,
        total_mm=round(total, 1),
        notes=' / '.join(notes_parts),
    )
