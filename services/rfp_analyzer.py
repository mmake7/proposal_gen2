"""
RFP 분석 AI 모듈 (Ticket #17)

Claude API를 사용하여 RFP(제안요청서) 텍스트를 분석하고
구조화된 데이터(사업개요, 요구사항, 배점기준, 제안목차)를 추출합니다.

이 모듈은 PDF 파싱 API (Ticket #19)의 app.py에서 사용됩니다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class RfpOverview:
    """사업개요"""
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
        return {
            'project_name': self.project_name,
            'organization': self.organization,
            'period': self.period,
            'budget': self.budget,
            'budget_unit': self.budget_unit,
            'contract_type': self.contract_type,
            'contract_method': self.contract_method,
            'qualifications': self.qualifications,
            'location': self.location,
            'purpose': self.purpose,
        }


@dataclass
class RfpRequirement:
    """요구사항 항목"""
    category: str = '기능'
    id: str = ''
    name: str = ''
    desc: str = ''
    level: str = '선택'

    def to_dict(self) -> dict:
        return {
            'category': self.category,
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'level': self.level,
        }


@dataclass
class RfpScoringItem:
    """배점기준 항목"""
    category: str = ''
    item: str = ''
    criteria: str = ''
    score: int = 0

    def to_dict(self) -> dict:
        return {
            'category': self.category,
            'item': self.item,
            'criteria': self.criteria,
            'score': self.score,
        }


@dataclass
class RfpTocItem:
    """제안목차 항목 (재귀 구조)"""
    level: int = 1
    number: str = ''
    title: str = ''
    description: str = ''
    children: list[RfpTocItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'level': self.level,
            'number': self.number,
            'title': self.title,
            'description': self.description,
            'children': [c.to_dict() for c in self.children],
        }


@dataclass
class RfpAnalysisResult:
    """RFP 분석 전체 결과"""
    overview: RfpOverview | None = None
    requirements: list[RfpRequirement] = field(default_factory=list)
    scoring: list[RfpScoringItem] = field(default_factory=list)
    toc: list[RfpTocItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'overview': self.overview.to_dict() if self.overview else None,
            'requirements': [r.to_dict() for r in self.requirements],
            'scoring': [s.to_dict() for s in self.scoring],
            'toc': [t.to_dict() for t in self.toc],
        }


# ── Prompt Template ──────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 한국 공공기관 RFP(제안요청서) 분석 전문가입니다.
주어진 RFP 텍스트를 분석하여 아래 4가지 항목을 추출해주세요.

## 중요: 출력 규칙

**반드시 순수 JSON만 출력하세요.**
- 마크다운 코드블록(```)을 사용하지 마세요.
- JSON 앞뒤에 설명, 인사말, 요약 등 어떤 텍스트도 추가하지 마세요.
- 응답의 첫 글자는 반드시 `{` 이고, 마지막 글자는 반드시 `}` 여야 합니다.
- 주석(// 또는 /* */)을 포함하지 마세요.

## 출력 형식 (JSON)

{
  "overview": {
    "project_name": "사업명",
    "organization": "발주기관명",
    "period": "사업기간 (예: 2026.04 ~ 2026.12)",
    "budget": "예산 숫자만 (예: 500)",
    "budget_unit": "단위 (백만원, 억원 등)",
    "contract_type": "계약 방식 (예: 제한경쟁입찰, 공개경쟁입찰)",
    "contract_method": "계약 유형 (예: 총액계약, 단가계약)",
    "qualifications": "참가자격 (예: 중소기업, 소프트웨어사업자)",
    "location": "수행장소",
    "purpose": "사업 목적 (1~2문장 요약)"
  },
  "requirements": [
    {
      "category": "기능 또는 비기능",
      "id": "고유ID (예: FR-001, NFR-001)",
      "name": "요구사항명",
      "desc": "요구사항 설명",
      "level": "필수 또는 선택"
    }
  ],
  "scoring": [
    {
      "category": "평가 대분류 (기술, 관리, 가격 등)",
      "item": "평가 항목명",
      "criteria": "평가 기준 설명",
      "score": 배점(정수)
    }
  ],
  "toc": [
    {
      "level": 1,
      "number": "I",
      "title": "대목차 제목",
      "description": "해당 장의 목적을 1줄로 요약",
      "children": [
        {
          "level": 2,
          "number": "1",
          "title": "소목차 제목",
          "description": "해당 절의 목적을 1줄로 요약",
          "children": [
            {
              "level": 3,
              "number": "가",
              "title": "세부 항목 제목",
              "description": "",
              "children": []
            }
          ]
        }
      ]
    }
  ]
}

## 규칙

1. **overview**: 텍스트에서 찾을 수 없는 필드는 빈 문자열("")로 남겨주세요.
2. **requirements**: 기능 요구사항은 "FR-001" 형식, 비기능 요구사항은 "NFR-001" 형식으로 ID를 부여하세요. RFP에 명시된 ID가 있으면 그것을 사용하세요.
3. **scoring**: 배점표가 있으면 그대로 추출하고, 없으면 빈 배열([])로 반환하세요. score는 반드시 정수로 반환하세요.
4. **toc**: RFP 내용을 바탕으로 적합한 제안서 목차를 구성하세요.
   - **번호 체계**: L1(대분류)은 로마숫자(I, II, III, ...), L2(중분류)는 아라비아 숫자(1, 2, 3, ...), L3(소분류)는 한글 가나다(가, 나, 다, ...)를 사용하세요.
   - **L1 대분류** 예시: 사업 이해, 현황 분석, 기술 제안, 수행 방안, 프로젝트 관리, 보안 및 품질 관리 등. RFP 특성에 맞게 구성하세요.
   - **L2 중분류**: 각 L1 아래에 구체적인 세부 주제를 배치하세요. RFP의 요구사항, 배점 항목을 빠짐없이 반영해야 합니다.
   - **L3 소분류**: 필요한 경우에만 작성하세요. 모든 L2에 L3가 필요하지는 않습니다.
   - **description**: 각 항목의 목적이나 다룰 내용을 1줄로 요약하세요. L3는 description을 빈 문자열로 남겨도 됩니다.
   - **배점 반영**: scoring 항목이 있으면, 배점이 높은 평가항목이 목차에 충분히 반영되도록 구성하세요.
   - RFP에 목차가 명시되어 있으면 그것을 기반으로 하되, 누락된 부분은 보완하세요.
   - 단순 인사말, 회사 일반 소개 등 불필요한 항목은 제외하세요 (RFP가 명시적으로 요구하는 경우 제외).
5. 한국어로 작성하세요.

다시 한번 강조: 순수 JSON만 출력하세요. 첫 글자 `{`, 마지막 글자 `}`."""


# ── Analyzer ─────────────────────────────────────────────────

class RfpAnalyzer:
    """
    Claude API를 사용한 RFP 분석기.

    사용법::

        analyzer = RfpAnalyzer()
        result = analyzer.analyze(rfp_text)
        print(result.to_dict())
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 16000,
    ):
        """
        Args:
            api_key: Anthropic API 키. None이면 환경변수 ANTHROPIC_API_KEY 사용.
            model: 사용할 Claude 모델 ID.
            max_tokens: 응답 최대 토큰 수.
        """
        self._api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        self._model = model or os.environ.get('ANTHROPIC_MODEL', 'claude-opus-4-8')
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        """Anthropic 클라이언트를 lazy-초기화합니다."""
        if self._client is None:
            if not self._api_key:
                raise RfpAnalysisError(
                    'ANTHROPIC_API_KEY가 설정되지 않았습니다. '
                    '.env 파일 또는 환경변수에 설정해주세요.'
                )
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise RfpAnalysisError(
                    'anthropic 패키지가 설치되지 않았습니다. '
                    'pip install anthropic 명령으로 설치해주세요.'
                )
        return self._client

    def analyze(self, text: str) -> RfpAnalysisResult:
        """
        RFP 텍스트를 분석하여 구조화된 결과를 반환합니다.

        Args:
            text: PDF에서 추출된 RFP 전체 텍스트.

        Returns:
            RfpAnalysisResult

        Raises:
            RfpAnalysisError: API 호출 실패 또는 응답 파싱 실패 시
        """
        if not text or not text.strip():
            raise RfpAnalysisError('분석할 텍스트가 비어있습니다.')

        # 텍스트가 너무 길면 자르기 (Claude 컨텍스트 윈도우 고려)
        truncated = self._truncate_text(text, max_chars=150_000)

        raw_json = self._call_api(truncated)
        return self._parse_response(raw_json)

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """텍스트를 최대 길이로 자릅니다."""
        if len(text) <= max_chars:
            return text
        logger.warning(
            'RFP 텍스트가 %d자로 최대 %d자를 초과합니다. 앞부분만 사용합니다.',
            len(text), max_chars,
        )
        return text[:max_chars]

    def _call_api(self, text: str) -> str:
        """Claude API를 호출하여 분석 결과 JSON 문자열을 반환합니다."""
        client = self._get_client()

        user_message = f"다음은 RFP(제안요청서) 문서의 전체 텍스트입니다. 분석해주세요.\n\n---\n\n{text}"

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                thinking={'type': 'adaptive'},       # Opus 4.7/4.8: adaptive만 허용
                output_config={'effort': 'high'},    # 구조 추출 품질 우선
                messages=[
                    {'role': 'user', 'content': user_message},
                ],
            )
        except Exception as exc:
            logger.error('Claude API 호출 실패: %s', exc)
            raise RfpAnalysisError(f'AI 분석 중 오류가 발생했습니다: {exc}') from exc

        # 텍스트 블록에서 결과 추출
        result_text = ''
        for block in response.content:
            if block.type == 'text':
                result_text += block.text

        if not result_text.strip():
            raise RfpAnalysisError('AI로부터 빈 응답을 받았습니다.')

        # 디버깅용: 원본 응답을 파일로 저장
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, 'last_api_response.txt')
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(result_text)
            logger.info('API 원본 응답 저장 완료: %s (%d자)', log_path, len(result_text))
        except Exception as exc:
            logger.warning('API 응답 파일 저장 실패: %s', exc)

        return result_text

    def _parse_response(self, raw: str) -> RfpAnalysisResult:
        """Claude 응답 JSON을 RfpAnalysisResult로 파싱합니다.

        5단계 추출을 시도합니다:
        1) 마크다운 코드블록(```json ... ```) 내부 추출 (모든 코드블록 시도)
        2) 응답 전체를 직접 JSON 파싱
        3) 첫 번째 '{' ~ 마지막 '}' 구간 추출
        4) 위 후보들에서 trailing comma 제거 후 재시도
        5) 정규식으로 JSON 객체 패턴 추출 후 재시도
        """
        logger.debug(
            'AI 응답 파싱 시작 (길이: %d자, 첫 200자: %s)',
            len(raw), raw[:200],
        )

        candidates: list[str] = []

        # ── 1단계: 코드블록 내부 JSON 추출 (모든 코드블록) ──
        code_blocks = re.findall(
            r'```(?:json)?\s*\n?(.*?)\n?\s*```',
            raw, re.DOTALL,
        )
        for block in code_blocks:
            stripped = block.strip()
            if stripped:
                candidates.append(stripped)

        # ── 2단계: 원본 앞뒤 공백 제거 후 시도 ──
        candidates.append(raw.strip())

        # ── 3단계: 첫 '{' ~ 마지막 '}' 폴백 ──
        first_brace = raw.find('{')
        last_brace = raw.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            candidates.append(raw[first_brace:last_brace + 1])

        # ── 파싱 시도 (원본 후보) ──
        last_err = None
        for idx, text in enumerate(candidates):
            try:
                data = json.loads(text)
                if idx > 0:
                    logger.info('JSON 파싱 %d번째 후보에서 성공', idx + 1)
                return self._build_result(data)
            except json.JSONDecodeError as exc:
                last_err = exc
                continue

        # ── 4단계: trailing comma 제거 후 재시도 ──
        for idx, text in enumerate(candidates):
            cleaned = self._fix_json_quirks(text)
            if cleaned == text:
                continue  # 변경 없으면 스킵
            try:
                data = json.loads(cleaned)
                logger.info('JSON 파싱 성공 (trailing comma 제거, 후보 %d)', idx + 1)
                return self._build_result(data)
            except json.JSONDecodeError as exc:
                last_err = exc
                continue

        # ── 5단계: 정규식으로 JSON 객체 패턴 추출 ──
        json_objects = re.findall(
            r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}',
            raw, re.DOTALL,
        )
        for obj_str in json_objects:
            if len(obj_str) < 50:  # 너무 짧은 것은 스킵
                continue
            for attempt in (obj_str, self._fix_json_quirks(obj_str)):
                try:
                    data = json.loads(attempt)
                    # overview 또는 toc 키가 있는지 확인하여 유효한 결과인지 검증
                    if isinstance(data, dict) and ('overview' in data or 'toc' in data):
                        logger.info('JSON 파싱 성공 (정규식 객체 추출)')
                        return self._build_result(data)
                except json.JSONDecodeError:
                    continue

        # 모든 단계 실패 — 콘솔에 앞 2000자 출력
        logger.error(
            'JSON 파싱 실패 (모든 단계 실패)\n'
            '── 마지막 에러: %s\n'
            '── 응답 길이: %d자\n'
            '── 응답 앞 2000자:\n%s',
            last_err,
            len(raw),
            raw[:2000],
        )
        raise RfpAnalysisError(
            'AI 응답을 파싱할 수 없습니다. 다시 시도해주세요.'
        ) from last_err

    @staticmethod
    def _fix_json_quirks(text: str) -> str:
        """LLM이 자주 생성하는 JSON 오류를 수정합니다.

        - trailing comma 제거: }, ] 앞의 쉼표
        - 주석 제거: // 한줄 주석
        """
        # // 주석 제거 (문자열 내부가 아닌 것만)
        result = re.sub(r'(?m)^\s*//.*$', '', text)
        result = re.sub(r'(?<=\S)\s*//[^\n]*', '', result)
        # trailing comma 제거: ,\s*} 또는 ,\s*]
        result = re.sub(r',\s*([}\]])', r'\1', result)
        return result

    def _build_result(self, data: dict) -> RfpAnalysisResult:
        """파싱된 dict를 RfpAnalysisResult 객체로 변환합니다."""
        result = RfpAnalysisResult()

        # 사업개요
        ov = data.get('overview')
        if ov and isinstance(ov, dict):
            result.overview = RfpOverview(
                project_name=str(ov.get('project_name', '')),
                organization=str(ov.get('organization', '')),
                period=str(ov.get('period', '')),
                budget=str(ov.get('budget', '')),
                budget_unit=str(ov.get('budget_unit', '백만원')),
                contract_type=str(ov.get('contract_type', '')),
                contract_method=str(ov.get('contract_method', '')),
                qualifications=str(ov.get('qualifications', '')),
                location=str(ov.get('location', '')),
                purpose=str(ov.get('purpose', '')),
            )

        # 요구사항
        reqs = data.get('requirements', [])
        if isinstance(reqs, list):
            for item in reqs:
                if isinstance(item, dict):
                    result.requirements.append(RfpRequirement(
                        category=str(item.get('category', '기능')),
                        id=str(item.get('id', '')),
                        name=str(item.get('name', '')),
                        desc=str(item.get('desc', '')),
                        level=str(item.get('level', '선택')),
                    ))

        # 배점기준
        scores = data.get('scoring', [])
        if isinstance(scores, list):
            for item in scores:
                if isinstance(item, dict):
                    score_val = item.get('score', 0)
                    try:
                        score_val = int(score_val)
                    except (ValueError, TypeError):
                        score_val = 0
                    result.scoring.append(RfpScoringItem(
                        category=str(item.get('category', '')),
                        item=str(item.get('item', '')),
                        criteria=str(item.get('criteria', '')),
                        score=score_val,
                    ))

        # 제안목차
        toc_items = data.get('toc', [])
        if isinstance(toc_items, list):
            result.toc = self._build_toc_items(toc_items)

        return result

    def _build_toc_items(self, items: list) -> list[RfpTocItem]:
        """재귀적으로 TOC 항목을 빌드합니다."""
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            level = item.get('level', 1)
            try:
                level = int(level)
            except (ValueError, TypeError):
                level = 1
            children = item.get('children', [])
            toc_item = RfpTocItem(
                level=level,
                number=str(item.get('number', '')),
                title=str(item.get('title', '')),
                description=str(item.get('description', '')),
                children=self._build_toc_items(children) if isinstance(children, list) else [],
            )
            result.append(toc_item)
        return result


# ── Exception ────────────────────────────────────────────────

class RfpAnalysisError(Exception):
    """RFP 분석 중 발생한 오류"""
