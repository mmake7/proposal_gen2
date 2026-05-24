"""NarrativeRequirementParser — 서술 기반 요구사항 추출 (LLM).

표 파서가 추출한 결과를 컨텍스트로 받아 일관된 양식으로 추가 요구사항을 추출.
새 양식·비표준 양식 대응 강화 — Classifier 메타 + 표 파서 양식 샘플을 동봉.
"""

from __future__ import annotations

from services_v2.agents.base import ClaudeAgent
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import Requirement, RfpClassification


class NarrativeRequirementAgent(ClaudeAgent):
    name = 'requirement_narrative'
    prompt_file = 'requirement_narrative.md'
    max_tokens = 8192

    def extract(
        self,
        doc: RfpDocument,
        *,
        existing_reqs: list[Requirement] | None = None,
        existing_ids: set[str] | None = None,  # backward compat
        classification: RfpClassification | None = None,
        language_dialect: str = '',  # backward compat
    ) -> list[Requirement]:
        """본문에서 서술형 요구사항을 추출.

        Args:
            doc: 분석 대상 문서.
            existing_reqs: 표 파서가 추출한 Requirement 전체 — 양식 샘플 제공용.
            existing_ids: (legacy) ID set만 전달하는 옛 인터페이스.
            classification: Classifier 결과 — 양식 특이점 전체 전달.
            language_dialect: (legacy) classification 미전달 시 fallback.
        """
        if existing_reqs is None:
            existing_reqs = []
        ids_to_exclude = (existing_ids or set()) | {r.id for r in existing_reqs if r.id}

        text = self._sample(doc, max_chars=120_000)
        user_parts: list[str] = [f"파일명: {doc.filename}"]

        # Classifier 메타 — 새 양식 적응을 위한 핵심 컨텍스트
        if classification:
            ctx_lines = ['## RFP 양식 메타 (Classifier 분석)']
            if classification.org_type:
                ctx_lines.append(f'- 발주기관 유형: {classification.org_type}')
            if classification.req_id_scheme:
                ctx_lines.append(f'- ID 체계: {classification.req_id_scheme}')
            if classification.req_format:
                ctx_lines.append(f'- 요구사항 형식: {classification.req_format}')
            if classification.language_dialect:
                ctx_lines.append(f'- 어휘 특이점: {classification.language_dialect}')
            if classification.notes:
                ctx_lines.append(f'- 분류 메모: {classification.notes}')
            user_parts.append('\n'.join(ctx_lines))
        elif language_dialect:
            user_parts.append(f'어휘 특이점: {language_dialect}')

        # 표 파서가 잡은 양식 샘플 — narrative가 같은 형식을 따르도록
        if existing_reqs:
            sample = existing_reqs[:5]
            sample_lines = [
                f'## 표 파서가 추출한 샘플 ({len(existing_reqs)}건 중 앞 {len(sample)}건)',
                '같은 양식으로 본문에서 표가 놓친 추가 요구사항을 찾으세요.',
                '',
            ]
            for r in sample:
                cat = r.category or r.category_code or '?'
                sample_lines.append(f'- [{r.id}] [{cat}] {r.name}')
            user_parts.append('\n'.join(sample_lines))
            user_parts.append(
                f'제외할 ID: {sorted(ids_to_exclude)[:50]}'
            )

        user_parts.append(f'\n--- RFP 본문 ---\n{text}')

        data = self.run('\n'.join(user_parts))
        results: list[Requirement] = []
        for r in data.get('requirements', []):
            req_id = r.get('id', '')
            if req_id and req_id in ids_to_exclude:
                continue
            req = Requirement(
                id=req_id,
                name=r.get('name', ''),
                category=r.get('category', ''),
                category_code=r.get('category_code', ''),
                definition=r.get('definition', ''),
                detail=r.get('detail', ''),
                output_info=r.get('output_info', ''),
                related_reqs=r.get('related_reqs', ''),
                source=r.get('source', ''),
                parse_method='narrative',
            )
            parts = [p for p in (req.definition, req.detail) if p]
            req.desc = '\n'.join(parts)
            results.append(req)
        return results

    @staticmethod
    def _sample(doc: RfpDocument, max_chars: int) -> str:
        if doc.total_chars <= max_chars:
            return doc.full_text
        # 요구사항은 보통 RFP 중반 — 중앙 부분 발췌
        half = max_chars // 2
        mid = doc.total_chars // 2
        return doc.full_text[max(0, mid - half):mid + half]
