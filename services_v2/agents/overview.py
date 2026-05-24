"""Overview Agent — 사업개요 추출."""

from __future__ import annotations

from services_v2.agents.base import ClaudeAgent
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import Overview


class OverviewAgent(ClaudeAgent):
    name = 'overview'
    prompt_file = 'overview.md'
    max_tokens = 1024

    def extract(self, doc: RfpDocument, classification_notes: str = '') -> Overview:
        # 사업개요는 보통 문서 앞 5~10페이지에 집중.
        text = self._head_sample(doc, max_chars=30_000)
        user_parts = [f"파일명: {doc.filename}"]
        if classification_notes:
            user_parts.append(f"분류 메모: {classification_notes}")
        user_parts.append(f"\n--- RFP 본문 (앞부분) ---\n{text}")
        data = self.run('\n'.join(user_parts))
        return Overview(
            project_name=data.get('project_name', ''),
            organization=data.get('organization', ''),
            period=data.get('period', ''),
            budget=data.get('budget', ''),
            budget_unit=data.get('budget_unit', '백만원'),
            contract_type=data.get('contract_type', ''),
            contract_method=data.get('contract_method', ''),
            qualifications=data.get('qualifications', ''),
            location=data.get('location', ''),
            purpose=data.get('purpose', ''),
        )

    @staticmethod
    def _head_sample(doc: RfpDocument, max_chars: int) -> str:
        return doc.full_text[:max_chars]
