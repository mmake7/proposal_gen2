"""
Content Generator
확정된 TOC 항목별로 Claude API를 호출하여 제안서 콘텐츠를 생성합니다.

각 L2 섹션에 대해 RFP 분석 결과, 배점기준, 요구사항을 컨텍스트로 제공하여
맞춤형 제안서 내용을 생성합니다.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ContentGeneratorError(Exception):
    """콘텐츠 생성 중 발생하는 에러"""


# ── Session State ─────────────────────────────────────────
_generated_content: dict[tuple, dict] = {}
_generation_progress: dict = {'total': 0, 'completed': 0, 'current': ''}


_SYSTEM_PROMPT = """당신은 한국 공공기관 제안서 작성 전문가입니다.
주어진 RFP 분석 결과와 목차 항목을 기반으로 제안서 본문 내용을 작성해주세요.

## 작성 원칙
1. **제안서 문체**: 공식적이지만 설득력 있는 제안서 톤으로 작성하세요.
2. **구체성**: 추상적 표현 대신 구체적인 기술 방안, 수행 전략을 제시하세요.
3. **배점 반영**: 제공된 배점기준 항목을 반드시 반영하여 작성하세요.
4. **요구사항 반영**: 관련 요구사항을 본문에서 직접 다루세요.
5. **분량**: 각 섹션별 500~1000자(한국어 기준)로 작성하세요.

## 출력 형식 (JSON)
```json
{
  "title": "섹션 제목",
  "content_text": "본문 내용 (마크다운 없이 순수 텍스트)",
  "bullet_points": ["핵심 포인트 1", "핵심 포인트 2", ...],
  "key_phrases": ["키워드1", "키워드2", ...]
}
```

반드시 유효한 JSON만 출력하세요. 추가 설명 없이 순수 JSON만 반환하세요."""


class ContentGenerator:
    """Claude API를 사용한 제안서 콘텐츠 생성기."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 8192,
    ):
        self._api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        self._model = model or os.environ.get('ANTHROPIC_MODEL', 'claude-opus-4-8')
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise ContentGeneratorError(
                    'ANTHROPIC_API_KEY가 설정되지 않았습니다.'
                )
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ContentGeneratorError(
                    'anthropic 패키지가 설치되지 않았습니다.'
                )
        return self._client

    def generate_section(
        self,
        toc_item: dict,
        context: dict,
    ) -> dict:
        """단일 TOC 섹션의 콘텐츠를 생성합니다.

        Args:
            toc_item: TOC 항목 {level, number, title, description, children}
            context: 컨텍스트 정보
                - rfp_text: RFP 전체 텍스트 (truncated)
                - overview: 사업 개요
                - requirements: 관련 요구사항
                - scoring: 관련 배점기준
                - parent_title: 부모 L1 제목
                - sibling_titles: 형제 섹션 제목 리스트

        Returns:
            {title, content_text, bullet_points, key_phrases}
        """
        user_message = self._build_user_message(toc_item, context)

        client = self._get_client()

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                thinking={'type': 'adaptive'},       # Opus 4.7/4.8: adaptive만 허용
                output_config={'effort': 'high'},    # 제안서 콘텐츠 품질 우선
                messages=[
                    {'role': 'user', 'content': user_message},
                ],
            )
        except Exception as exc:
            logger.error('콘텐츠 생성 API 호출 실패: %s', exc)
            raise ContentGeneratorError(
                f'콘텐츠 생성 중 오류가 발생했습니다: {exc}'
            ) from exc

        result_text = ''
        for block in response.content:
            if block.type == 'text':
                result_text += block.text

        if not result_text.strip():
            raise ContentGeneratorError('AI로부터 빈 응답을 받았습니다.')

        return self._parse_section_response(result_text, toc_item.get('title', ''))

    def _build_user_message(self, toc_item: dict, context: dict) -> str:
        """Claude에 보낼 사용자 메시지를 구성합니다."""
        parts = []

        # 사업 개요
        overview = context.get('overview')
        if overview:
            parts.append('## 사업 개요')
            parts.append(f"- 사업명: {overview.get('project_name', '')}")
            parts.append(f"- 발주기관: {overview.get('organization', '')}")
            parts.append(f"- 사업목적: {overview.get('purpose', '')}")
            parts.append(f"- 사업기간: {overview.get('period', '')}")
            parts.append('')

        # 관련 배점기준
        scoring = context.get('scoring', [])
        if scoring:
            parts.append('## 관련 배점기준')
            for s in scoring:
                parts.append(f"- [{s.get('category', '')}] {s.get('item', '')} ({s.get('score', 0)}점): {s.get('criteria', '')}")
            parts.append('')

        # 관련 요구사항
        requirements = context.get('requirements', [])
        if requirements:
            parts.append('## 관련 요구사항')
            for r in requirements:
                parts.append(f"- [{r.get('id', '')}] {r.get('name', '')}: {r.get('desc', '')}")
            parts.append('')

        # 목차 컨텍스트
        parent_title = context.get('parent_title', '')
        siblings = context.get('sibling_titles', [])
        parts.append('## 작성할 섹션 정보')
        if parent_title:
            parts.append(f"- 상위 장: {parent_title}")
        parts.append(f"- 섹션 번호: {toc_item.get('number', '')}")
        parts.append(f"- 섹션 제목: {toc_item.get('title', '')}")
        if toc_item.get('description'):
            parts.append(f"- 섹션 설명: {toc_item.get('description', '')}")
        if siblings:
            parts.append(f"- 동일 장 내 형제 섹션: {', '.join(siblings)}")

        # RFP 텍스트 (축약)
        rfp_text = context.get('rfp_text', '')
        if rfp_text:
            truncated = rfp_text[:30000]
            parts.append('')
            parts.append('## RFP 원문 (일부)')
            parts.append(truncated)

        parts.append('')
        parts.append('위 정보를 바탕으로 해당 섹션의 제안서 내용을 작성해주세요.')

        return '\n'.join(parts)

    def _parse_section_response(self, raw: str, default_title: str) -> dict:
        """AI 응답을 파싱합니다."""
        import json
        import re

        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning('콘텐츠 JSON 파싱 실패, 원본 텍스트 사용')
            return {
                'title': default_title,
                'content_text': raw.strip(),
                'bullet_points': [],
                'key_phrases': [],
            }

        return {
            'title': data.get('title', default_title),
            'content_text': data.get('content_text', ''),
            'bullet_points': data.get('bullet_points', []),
            'key_phrases': data.get('key_phrases', []),
        }

    def generate_all(
        self,
        toc_items: list[dict],
        rfp_text: str,
        analysis_result: dict,
    ) -> dict:
        """전체 TOC에 대해 콘텐츠를 생성합니다.

        L2 레벨 항목에 대해 콘텐츠를 생성합니다.
        L1은 챕터 구분자로, L3는 L2에 포함됩니다.

        Returns:
            {
                "sections": {
                    "0-0": {title, content_text, bullet_points, key_phrases},
                    "0-1": {...},
                    ...
                },
                "progress": {total, completed, current}
            }
        """
        global _generated_content, _generation_progress

        _generated_content = {}
        overview = analysis_result.get('overview', {})
        requirements = analysis_result.get('requirements', [])
        scoring = analysis_result.get('scoring', [])

        # L2 항목 수 계산
        sections_to_generate = []
        for l1_idx, l1_item in enumerate(toc_items):
            children = l1_item.get('children', [])
            if not children:
                # L1에 자식이 없으면 L1 자체를 생성
                sections_to_generate.append({
                    'key': str(l1_idx),
                    'toc_item': l1_item,
                    'parent_title': '',
                    'sibling_titles': [],
                })
            else:
                sibling_titles = [c.get('title', '') for c in children]
                for l2_idx, l2_item in enumerate(children):
                    sections_to_generate.append({
                        'key': f'{l1_idx}-{l2_idx}',
                        'toc_item': l2_item,
                        'parent_title': l1_item.get('title', ''),
                        'sibling_titles': [t for i, t in enumerate(sibling_titles) if i != l2_idx],
                    })

        total = len(sections_to_generate)
        _generation_progress = {'total': total, 'completed': 0, 'current': ''}

        for sec in sections_to_generate:
            _generation_progress['current'] = sec['toc_item'].get('title', '')

            context = {
                'rfp_text': rfp_text,
                'overview': overview,
                'requirements': requirements,
                'scoring': scoring,
                'parent_title': sec['parent_title'],
                'sibling_titles': sec['sibling_titles'],
            }

            try:
                content = self.generate_section(sec['toc_item'], context)
                _generated_content[sec['key']] = content
            except ContentGeneratorError as exc:
                logger.warning('섹션 "%s" 생성 실패: %s', sec['key'], exc)
                _generated_content[sec['key']] = {
                    'title': sec['toc_item'].get('title', ''),
                    'content_text': f'[생성 실패: {exc}]',
                    'bullet_points': [],
                    'key_phrases': [],
                }

            _generation_progress['completed'] += 1

        _generation_progress['current'] = ''

        return {
            'sections': _generated_content,
            'progress': _generation_progress,
        }


def get_generated_content() -> dict:
    """생성된 전체 콘텐츠를 반환합니다."""
    return {
        'sections': _generated_content,
        'progress': _generation_progress,
    }


def get_section_content(key: str) -> dict | None:
    """특정 섹션의 생성된 콘텐츠를 반환합니다."""
    return _generated_content.get(key)


def get_progress() -> dict:
    """현재 생성 진행 상황을 반환합니다."""
    return _generation_progress
