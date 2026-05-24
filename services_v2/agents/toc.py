"""TOC Agent — 제안목차 추출."""

from __future__ import annotations

from services_v2.agents.base import ClaudeAgent
from services_v2.documents.rfp_document import RfpDocument
from services_v2.results.rfp_analysis import TocItem


class TocAgent(ClaudeAgent):
    name = 'toc'
    prompt_file = 'toc.md'
    max_tokens = 8192  # 깊은 트리 추출 시 4096 한도 초과 사례 방지

    def extract(self, doc: RfpDocument, toc_location: str = '') -> list[TocItem]:
        # 목차 위치 힌트에 따라 샘플링 영역 결정.
        if toc_location == 'back':
            text = self._tail_sample(doc, 40_000)
        elif toc_location == 'front':
            text = doc.full_text[:30_000]
        else:
            text = self._head_and_tail(doc, head=20_000, tail=15_000)

        user_parts = [f"파일명: {doc.filename}"]
        if toc_location:
            user_parts.append(f"목차 예상 위치: {toc_location}")
        user_parts.append(f"\n--- RFP 본문 ---\n{text}")
        data = self.run('\n'.join(user_parts))
        return [self._to_item(t) for t in data.get('toc', [])]

    @classmethod
    def _to_item(cls, raw: dict) -> TocItem:
        return TocItem(
            level=int(raw.get('level', 1)),
            number=raw.get('number', ''),
            title=raw.get('title', ''),
            description=raw.get('description', ''),
            children=[cls._to_item(c) for c in raw.get('children', [])],
        )

    @staticmethod
    def _tail_sample(doc: RfpDocument, max_chars: int) -> str:
        return doc.full_text[-max_chars:] if doc.total_chars > max_chars else doc.full_text

    @staticmethod
    def _head_and_tail(doc: RfpDocument, head: int, tail: int) -> str:
        if doc.total_chars <= head + tail:
            return doc.full_text
        return doc.full_text[:head] + '\n\n... [중략] ...\n\n' + doc.full_text[-tail:]
