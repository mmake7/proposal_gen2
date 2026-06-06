"""분석 결과 누적 저장 — 양식 갤러리.

analyses/{timestamp}_{filename}.json + summary 메타.
누적되면 어떤 RFP 양식이 잘 되는지/약한지 분석 가능.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from services_v2.results.rfp_analysis import RfpAnalysisResult

logger = logging.getLogger(__name__)

ANALYSES_DIR = Path(__file__).resolve().parent.parent.parent / 'data' / 'analyses'


def save_result(
    result: RfpAnalysisResult,
    filename: str,
    *,
    base_dir: Path | None = None,
) -> Path:
    """RfpAnalysisResult를 JSON으로 저장.

    Args:
        result: 분석 결과.
        filename: 원본 RFP 파일명 (저장 파일명에 사용).
        base_dir: 저장 디렉토리. None이면 repo_root/analyses/.

    Returns:
        저장된 JSON 파일 경로.
    """
    base = base_dir or ANALYSES_DIR
    base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[^\w\-가-힣]', '_', Path(filename).stem)[:60]
    out_path = base / f'{timestamp}_{safe_name}.json'

    payload: dict[str, Any] = {
        'meta': {
            'filename': filename,
            'analyzed_at': datetime.now().isoformat(),
            'confidence': (
                result.validation.confidence if result.validation else None
            ),
            'requirements_count': len(result.requirements),
            'scoring_count': len(result.scoring),
            'scoring_total': sum(s.score for s in result.scoring),
            'toc_l1_count': len(result.toc),
            'has_overview': result.overview is not None
                            and bool(result.overview.project_name),
            'classification': (
                result.classification.to_dict() if result.classification else None
            ),
        },
        'result': result.to_dict(),
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info('분석 결과 저장: %s', out_path)
    return out_path


def list_analyses(base_dir: Path | None = None) -> list[Path]:
    """analyses/ 디렉토리의 모든 분석 결과 파일 (최신순)."""
    base = base_dir or ANALYSES_DIR
    if not base.exists():
        return []
    return sorted(base.glob('*.json'), reverse=True)


def load_summary(path: Path) -> dict:
    """저장된 JSON의 meta 부분만 빠르게 로드."""
    data = json.loads(path.read_text(encoding='utf-8'))
    return data.get('meta', {})


def summarize_gallery(base_dir: Path | None = None) -> dict:
    """누적된 분석들의 통계 요약 — 양식 다양성 추적용.

    Returns:
        {
            'total': 5,
            'avg_confidence': 0.82,
            'by_org_type': {'중앙부처': 3, '지자체': 2},
            'by_req_format': {'table': 4, 'mixed': 1},
            'avg_requirements': 38.5,
            'low_confidence_files': ['...'],
        }
    """
    files = list_analyses(base_dir)
    if not files:
        return {'total': 0}

    summaries = [load_summary(p) for p in files]
    valid = [s for s in summaries if s]

    by_org: dict[str, int] = {}
    by_format: dict[str, int] = {}
    conf_sum = 0.0
    conf_count = 0
    req_total = 0
    low_conf_files = []

    for s in valid:
        cls = s.get('classification') or {}
        org = cls.get('org_type') or '(unknown)'
        fmt = cls.get('req_format') or '(unknown)'
        by_org[org] = by_org.get(org, 0) + 1
        by_format[fmt] = by_format.get(fmt, 0) + 1
        conf = s.get('confidence')
        if conf is not None:
            conf_sum += conf
            conf_count += 1
            if conf < 0.7:
                low_conf_files.append(s.get('filename', ''))
        req_total += s.get('requirements_count', 0)

    return {
        'total': len(valid),
        'avg_confidence': (conf_sum / conf_count) if conf_count else None,
        'avg_requirements': (req_total / len(valid)) if valid else 0,
        'by_org_type': dict(sorted(by_org.items(), key=lambda x: -x[1])),
        'by_req_format': dict(sorted(by_format.items(), key=lambda x: -x[1])),
        'low_confidence_files': low_conf_files,
    }


# ── Orchestrator 통합 ────────────────────────────────────────

def auto_save_enabled() -> bool:
    """환경변수 V2_AUTO_SAVE=1이면 자동 저장 활성."""
    return os.environ.get('V2_AUTO_SAVE', '').lower() in ('1', 'true', 'yes')
