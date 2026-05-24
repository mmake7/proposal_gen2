"""Claude 에이전트 공통 기반.

모든 v2 에이전트가 상속. 책임:
- API 클라이언트 lazy 초기화
- 시스템 프롬프트(.md) 로딩
- JSON 응답 파싱 (3단 폴백)
- 호출 트레이스 기록
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


DEFAULT_MODEL = 'claude-opus-4-7'
PROMPTS_DIR = Path(__file__).resolve().parent.parent / 'prompts'


class AgentError(Exception):
    """에이전트 실행 중 발생하는 에러."""


@dataclass
class AgentCall:
    """단일 API 호출 트레이스."""
    agent: str
    model: str
    duration_ms: int
    input_chars: int
    output_chars: int
    success: bool
    error: str = ''
    stop_reason: str = ''  # 'end_turn' | 'max_tokens' | 'stop_sequence' | 'tool_use'


class ClaudeAgent:
    """v2 에이전트의 공통 부모."""

    name: str = 'base'
    prompt_file: str = ''      # services_v2/prompts/<name>.md (서브클래스에서 지정)
    model: str = DEFAULT_MODEL
    max_tokens: int = 4096

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        if model:
            self.model = model
        self._client = None
        self.calls: list[AgentCall] = []

    # ── Public API ────────────────────────────────────────────
    def run(self, user_message: str) -> dict:
        """동기 실행 — 단일 API 호출 + JSON 파싱."""
        system_prompt = self._load_prompt()
        raw = self._call_api(system_prompt, user_message)
        return self._parse_json(raw)

    # ── Internal ──────────────────────────────────────────────
    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise AgentError(
                    'ANTHROPIC_API_KEY가 설정되지 않았습니다.'
                )
            try:
                import anthropic
            except ImportError as exc:
                raise AgentError('anthropic 패키지가 설치되지 않았습니다.') from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _load_prompt(self) -> str:
        if not self.prompt_file:
            raise AgentError(f'{self.name}: prompt_file이 지정되지 않음')
        path = PROMPTS_DIR / self.prompt_file
        if not path.exists():
            raise AgentError(f'프롬프트 파일 없음: {path}')
        return path.read_text(encoding='utf-8')

    def _call_api(self, system: str, user: str) -> str:
        client = self._get_client()
        start = time.time()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{'role': 'user', 'content': user}],
            )
        except Exception as exc:
            self._record_call(start, len(user), 0, success=False, error=str(exc))
            raise AgentError(f'{self.name} API 호출 실패: {exc}') from exc

        text = ''
        for block in response.content:
            if block.type == 'text':
                text += block.text

        stop_reason = getattr(response, 'stop_reason', '') or ''
        self._record_call(
            start, len(user), len(text),
            success=bool(text.strip()), stop_reason=stop_reason,
        )

        if stop_reason == 'max_tokens':
            logger.warning(
                '%s: 응답이 max_tokens(%d)로 잘렸을 수 있음. JSON 파싱 실패 가능.',
                self.name, self.max_tokens,
            )

        if not text.strip():
            raise AgentError(f'{self.name}: 빈 응답')
        return text

    def _record_call(self, start: float, in_chars: int, out_chars: int,
                     *, success: bool, error: str = '',
                     stop_reason: str = '') -> None:
        self.calls.append(AgentCall(
            agent=self.name,
            model=self.model,
            duration_ms=int((time.time() - start) * 1000),
            input_chars=in_chars,
            output_chars=out_chars,
            success=success,
            error=error,
            stop_reason=stop_reason,
        ))

    @staticmethod
    def _parse_json(text: str) -> Any:
        """3단 폴백: 코드블록 → raw → 중괄호 추출."""
        # 1) ```json ... ``` 블록
        m = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 2) raw
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # 3) 첫 중괄호 ~ 마지막 중괄호
        start = text.find('{')
        if start < 0:
            start = text.find('[')
        end = max(text.rfind('}'), text.rfind(']'))
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError as exc:
                raise AgentError(f'JSON 파싱 실패: {exc}\n원문 일부: {text[:300]}') from exc
        raise AgentError(f'JSON을 찾을 수 없음: {text[:300]}')
