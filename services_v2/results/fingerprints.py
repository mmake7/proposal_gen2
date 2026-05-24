"""Classifier 메모리 학습 — 누적된 양식 특성을 다음 분석에 활용.

핵심 데이터 흐름:
  1. 분석 결과 → extract_fingerprint() → Fingerprint dict
  2. update_library() → analyses/_fingerprints.json에 누적
  3. load_library() → 다음 Classifier 호출 시 hint로 동봉

라이브러리가 커질수록 새 RFP 분류가 정확해짐 — 지속적 자기학습.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from services_v2.results.rfp_analysis import RfpAnalysisResult
from services_v2.results.storage import ANALYSES_DIR

logger = logging.getLogger(__name__)

LIBRARY_PATH = ANALYSES_DIR / '_fingerprints.json'

# 라이브러리 크기 제한 — 너무 많으면 prompt 비대화
MAX_FINGERPRINTS = 30
MAX_EXAMPLES_PER_FINGERPRINT = 5


def extract_fingerprint(
    result: RfpAnalysisResult,
    filename: str = '',
) -> dict[str, Any]:
    """분석 결과에서 양식 fingerprint 추출."""
    cls = result.classification
    val = result.validation

    notes_keywords = _extract_notes_keywords(cls.notes if cls else '')

    return {
        'org_type': (cls.org_type if cls else '') or 'unknown',
        'req_id_scheme': (cls.req_id_scheme if cls else '') or 'unknown',
        'req_format': (cls.req_format if cls else '') or 'unknown',
        'scoring_format': (cls.scoring_format if cls else '') or 'unknown',
        'language_dialect': (cls.language_dialect if cls else '') or '',
        'notes_keywords': notes_keywords,
        'filename': filename,
        'requirements_count': len(result.requirements),
        'scoring_count': len(result.scoring),
        'scoring_total': sum(s.score for s in result.scoring),
        'toc_l1_count': len(result.toc),
        'confidence': val.confidence if val else None,
        'recorded_at': datetime.now().isoformat(),
    }


def _extract_notes_keywords(notes: str, top_n: int = 5) -> list[str]:
    """notes 텍스트에서 짧은 키워드 추출 (한국어 명사 패턴)."""
    if not notes:
        return []
    # 한글 2~10자 단어 (느슨한 휴리스틱)
    words = re.findall(r'[가-힣]{2,10}', notes)
    # 빈도순
    freq: dict[str, int] = {}
    for w in words:
        if w in ('각종', '여러', '다양한', '있다', '있음', '없음'):
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])][:top_n]


def load_library(path: Path | None = None) -> list[dict]:
    """저장된 fingerprint 라이브러리 로드."""
    p = path or LIBRARY_PATH
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data.get('fingerprints', [])
    except Exception as exc:
        logger.warning('fingerprint 라이브러리 로드 실패: %s', exc)
        return []


def save_library(fingerprints: list[dict], path: Path | None = None) -> None:
    p = path or LIBRARY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'fingerprints': fingerprints[-MAX_FINGERPRINTS:],
        'updated_at': datetime.now().isoformat(),
    }
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def update_library(
    result: RfpAnalysisResult,
    filename: str = '',
    path: Path | None = None,
) -> dict:
    """분석 결과를 라이브러리에 추가. 동일 fingerprint(org+id_scheme+req_format) 그룹화."""
    fp = extract_fingerprint(result, filename=filename)
    library = load_library(path)

    # 같은 (org_type, req_id_scheme, req_format) 그룹 찾기
    key = (fp['org_type'], fp['req_id_scheme'], fp['req_format'])
    existing = None
    for entry in library:
        if (entry.get('org_type'), entry.get('req_id_scheme'),
                entry.get('req_format')) == key:
            existing = entry
            break

    if existing is None:
        # 새 그룹 — 라이브러리에 추가
        library.append({
            'org_type': fp['org_type'],
            'req_id_scheme': fp['req_id_scheme'],
            'req_format': fp['req_format'],
            'seen_count': 1,
            'examples': [fp],
        })
    else:
        existing['seen_count'] = existing.get('seen_count', 0) + 1
        examples = existing.setdefault('examples', [])
        examples.append(fp)
        existing['examples'] = examples[-MAX_EXAMPLES_PER_FINGERPRINT:]

    save_library(library, path)
    return fp


def format_for_classifier(
    library: list[dict] | None = None,
    *,
    max_chars: int = 2500,
) -> str:
    """라이브러리를 Classifier에 hint로 동봉할 텍스트로 직렬화.

    라이브러리가 비어있으면 빈 문자열 반환.
    """
    library = library if library is not None else load_library()
    if not library:
        return ''

    lines = [
        '## 이전 분석에서 학습된 양식 사례 (참고용)',
        '아래는 과거에 분석된 RFP들의 양식 특성입니다. 이번 RFP가 유사하다면',
        '같은 분류값을 사용하세요. 유사하지 않으면 무시하세요.',
        '',
    ]
    # seen_count 많은 순서로 (자주 본 양식 우선)
    sorted_lib = sorted(library, key=lambda x: -x.get('seen_count', 0))

    for entry in sorted_lib:
        seen = entry.get('seen_count', 1)
        org = entry.get('org_type', 'unknown')
        scheme = entry.get('req_id_scheme', 'unknown')
        fmt = entry.get('req_format', 'unknown')
        examples = entry.get('examples', [])

        lines.append(
            f'- **{org} / ID={scheme} / 형식={fmt}** ({seen}회 관찰)'
        )
        if examples:
            # 가장 최근 예시의 language_dialect 노출
            last = examples[-1]
            dialect = last.get('language_dialect', '')
            kws = last.get('notes_keywords', [])
            if dialect:
                lines.append(f'  - 어휘 특이점: {dialect[:120]}')
            if kws:
                lines.append(f'  - 자주 등장 키워드: {", ".join(kws)}')
            avg_reqs = sum(e.get('requirements_count', 0) for e in examples) // len(examples)
            lines.append(f'  - 평균 요구사항: {avg_reqs}건')

    text = '\n'.join(lines)
    return text[:max_chars]
