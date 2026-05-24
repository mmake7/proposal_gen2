"""v2 파이프라인 오케스트레이터.

5단계 흐름:
  1. Ingest          → RfpDocument
  2. Classify        → RfpClassification
  3. 전문 에이전트 병렬 실행 (Overview / Requirements / Scoring / TOC)
  4. Validate        → ValidationReport (필요 시 재시도)
  5. Synthesize      → RfpAnalysisResult (v1 호환)
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import asdict

from services_v2.agents.base import AgentError
from services_v2.agents.classifier import ClassifierAgent
from services_v2.agents.overview import OverviewAgent
from services_v2.agents.requirements.coordinator import RequirementsCoordinator
from services_v2.agents.scoring import ScoringAgent
from services_v2.agents.toc import TocAgent
from services_v2.agents.validator import ValidatorAgent
from services_v2.documents import IngestError, ingest_bytes
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import RfpAnalysisResult

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """파이프라인 실행 중 발생하는 에러."""


RETRY_THRESHOLD = 0.7
MAX_RETRIES = 1


def analyze_rfp_bytes(data: bytes, filename: str = 'upload.pdf') -> dict:
    """진입점: 바이트 문서(PDF/HWPX/DOCX) → v1 호환 dict.

    Flask 라우트에서 `?engine=v2`로 호출. 확장자로 자동 분기.
    V2_AUTO_SAVE=1 환경변수 설정 시 analyses/에 자동 저장.
    """
    try:
        doc = ingest_bytes(data, filename=filename)
    except IngestError as exc:
        raise OrchestratorError(f'문서 인제스트 실패: {exc}') from exc

    result = analyze_rfp_document(doc)

    from services_v2.results.storage import auto_save_enabled, save_result
    if auto_save_enabled():
        try:
            save_result(result, filename)
        except Exception as exc:
            logger.warning('자동 저장 실패 (계속 진행): %s', exc)

    return result.to_dict()


def analyze_rfp_document(doc: RfpDocument) -> RfpAnalysisResult:
    """RfpDocument를 받아 전체 파이프라인 실행."""
    classifier = ClassifierAgent()
    overview_agent = OverviewAgent()
    req_coordinator = RequirementsCoordinator()
    scoring_agent = ScoringAgent()
    toc_agent = TocAgent()
    validator = ValidatorAgent()

    # ── Stage 2: Classify ────────────────────────────────────
    try:
        classification = classifier.classify(doc)
    except AgentError as exc:
        logger.warning('Classifier 실패 — 기본값으로 진행: %s', exc)
        from services_v2.results.rfp_analysis import RfpClassification
        classification = RfpClassification(
            req_format='mixed', scoring_format='mixed', toc_location='back',
            notes=f'classifier 실패 폴백: {exc}',
        )

    # ── Stage 3: 전문가 병렬 실행 ────────────────────────────
    overview, requirements, scoring, toc_items = _run_specialists_parallel(
        doc, classification,
        overview_agent, req_coordinator, scoring_agent, toc_agent,
    )

    # ── Stage 4: Validate (+ 1회 재시도) ────────────────────
    report = _safe_validate(validator, overview, requirements, scoring, toc_items)

    # 재시도 트리거: (a) confidence 미달 + retry_targets,
    # 또는 (b) critical 필드가 비어있음 (overview/requirements/toc 중 하나라도)
    critical_empty = _critical_empty(overview, requirements, toc_items)
    confidence_low = (
        report.confidence < RETRY_THRESHOLD and report.retry_targets
    )

    if critical_empty or confidence_low:
        targets = list({*(report.retry_targets or []), *critical_empty})
        logger.info(
            '재시도 트리거 — confidence=%.2f, critical_empty=%s, targets=%s',
            report.confidence, critical_empty, targets,
        )
        overview, requirements, scoring, toc_items = _retry(
            doc, classification, targets,
            overview, requirements, scoring, toc_items,
            overview_agent, req_coordinator, scoring_agent, toc_agent,
        )
        report = _safe_validate(validator, overview, requirements, scoring, toc_items)

    # ── Stage 5: Synthesize ─────────────────────────────────
    # 모든 에이전트의 누적 calls를 한 번에 trace로 수집 (중복·누락 방지).
    trace = _collect_trace(
        classifier, overview_agent, req_coordinator, scoring_agent, toc_agent, validator,
    )

    result = RfpAnalysisResult(
        overview=overview,
        requirements=requirements,
        scoring=scoring,
        toc=toc_items,
        classification=classification,
        validation=report,
        agent_trace=trace,
    )

    # 견적 산정 (결정적 휴리스틱, LLM 없이 비용 0)
    try:
        from services_v2.estimation import estimate_from_analysis
        result.estimation = estimate_from_analysis(result)
    except Exception as exc:
        logger.warning('견적 산정 실패 (계속 진행): %s', exc)

    # 양식 fingerprint 라이브러리 항상 갱신 (Classifier 자기학습용, 비용 0)
    try:
        from services_v2.results.fingerprints import update_library
        update_library(result, filename=doc.filename)
    except Exception as exc:
        logger.warning('fingerprint 갱신 실패 (계속 진행): %s', exc)

    return result


def _run_specialists_parallel(
    doc, classification,
    overview_agent, req_coordinator, scoring_agent, toc_agent,
):
    """4개 전문가를 ThreadPoolExecutor로 병렬 실행 (I/O 바운드)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fut_overview = pool.submit(
            overview_agent.extract, doc, classification.notes,
        )
        fut_requirements = pool.submit(
            req_coordinator.extract, doc, classification,
        )
        fut_scoring = pool.submit(
            scoring_agent.extract, doc, classification.scoring_format,
        )
        fut_toc = pool.submit(
            toc_agent.extract, doc, classification.toc_location,
        )

        overview = _safe_get(fut_overview, 'overview', None)
        requirements = _safe_get(fut_requirements, 'requirements', [])
        scoring = _safe_get(fut_scoring, 'scoring', [])
        toc_items = _safe_get(fut_toc, 'toc', [])

    return overview, requirements, scoring, toc_items


def _safe_get(fut, name, default):
    try:
        return fut.result()
    except Exception as exc:
        logger.error('%s 에이전트 실패: %s', name, exc)
        return default


def _safe_validate(validator, overview, requirements, scoring, toc_items):
    try:
        return validator.validate(
            overview=overview, requirements=requirements,
            scoring=scoring, toc=toc_items,
        )
    except AgentError as exc:
        logger.warning('Validator 실패 — 검증 건너뜀: %s', exc)
        from services_v2.results.rfp_analysis import ValidationReport
        return ValidationReport(confidence=0.5, issues=[{
            'severity': 'warning', 'field': 'validator',
            'message': f'검증기 실패: {exc}',
        }])


def _retry(
    doc, classification, targets,
    overview, requirements, scoring, toc_items,
    overview_agent, req_coordinator, scoring_agent, toc_agent,
):
    """validator가 지정한 대상만 재실행. 재실행 호출도 각 에이전트 .calls에 누적."""
    if 'overview' in targets:
        try:
            overview = overview_agent.extract(doc, classification.notes)
        except AgentError as exc:
            logger.warning('overview 재시도 실패: %s', exc)
    if 'requirements' in targets:
        try:
            requirements = req_coordinator.extract(doc, classification)
        except AgentError as exc:
            logger.warning('requirements 재시도 실패: %s', exc)
    if 'scoring' in targets:
        try:
            scoring = scoring_agent.extract(doc, classification.scoring_format)
        except AgentError as exc:
            logger.warning('scoring 재시도 실패: %s', exc)
    if 'toc' in targets:
        try:
            toc_items = toc_agent.extract(doc, classification.toc_location)
        except AgentError as exc:
            logger.warning('toc 재시도 실패: %s', exc)
    return overview, requirements, scoring, toc_items


def _critical_empty(overview, requirements, toc_items) -> list[str]:
    """비어있으면 결과를 못 쓰는 필드. confidence와 무관하게 재시도."""
    empty: list[str] = []
    if overview is None or not getattr(overview, 'project_name', ''):
        empty.append('overview')
    if not requirements:
        empty.append('requirements')
    if not toc_items:
        empty.append('toc')
    return empty


def _collect_trace(*agents) -> list[dict]:
    """모든 에이전트의 누적 calls를 한 번에 dict 리스트로 수집.

    중복·누락 없음 — 각 에이전트의 .calls 리스트는 호출마다 append되므로
    파이프라인 끝에서 한 번만 모으면 됨.
    """
    trace: list[dict] = []
    for agent in agents:
        calls = getattr(agent, 'calls', [])
        trace.extend(asdict(c) for c in calls)
    return trace
