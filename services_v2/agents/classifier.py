"""Classifier Agent — Stage 2.

RFP 양식·구조를 분류하여 후속 에이전트 라우팅에 사용할 메타정보 산출.
누적된 fingerprint 라이브러리를 hint로 동봉해 지속적으로 자기학습.
"""

from __future__ import annotations

from services_v2.agents.base import ClaudeAgent
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import RfpClassification


class ClassifierAgent(ClaudeAgent):
    name = 'classifier'
    prompt_file = 'classifier.md'
    max_tokens = 4096

    def classify(self, doc: RfpDocument) -> RfpClassification:
        # 분류는 문서 전체 컨텍스트가 필요하나, 너무 길면 앞·뒤 일부만.
        text = self._sample_text(doc)

        # 누적된 양식 라이브러리를 hint로 동봉 (있을 때만)
        from services_v2.results.fingerprints import format_for_classifier
        library_hint = format_for_classifier()

        parts = [
            f"파일명: {doc.filename}",
            f"총 페이지: {doc.total_pages}",
            f"총 글자수: {doc.total_chars}",
            f"표가 있는 페이지: {doc.pages_with_tables()[:20]}",
        ]
        if library_hint:
            parts.append('')
            parts.append(library_hint)
        parts.append('')
        parts.append(f'--- RFP 본문 샘플 ---\n{text}')
        user = '\n'.join(parts)

        data = self.run(user)
        return RfpClassification(
            org_type=data.get('org_type', ''),
            req_id_scheme=data.get('req_id_scheme', ''),
            req_format=data.get('req_format', ''),
            scoring_format=data.get('scoring_format', ''),
            toc_location=data.get('toc_location', ''),
            doc_size_tier=data.get('doc_size_tier', ''),
            language_dialect=data.get('language_dialect', ''),
            notes=data.get('notes', ''),
        )

    @staticmethod
    def _sample_text(doc: RfpDocument, head: int = 20_000, tail: int = 10_000) -> str:
        if doc.total_chars <= head + tail:
            return doc.full_text
        return (
            doc.full_text[:head]
            + '\n\n... [중략] ...\n\n'
            + doc.full_text[-tail:]
        )
