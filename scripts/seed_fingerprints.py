"""저장된 분석 결과 JSON으로 fingerprint 라이브러리를 시드.

기존 sample_outputs/*.json 또는 analyses/*.json을 읽어 라이브러리에 누적.
LLM 호출 없이 학습 데이터 부트스트랩.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services_v2.results.fingerprints import (
    load_library, save_library, update_library,
)
from services_v2.results.rfp_analysis import (
    Overview, Requirement, RfpAnalysisResult, RfpClassification,
    ScoringItem, TocItem, ValidationReport,
)


def _toc_from_dict(items: list[dict]) -> list[TocItem]:
    """재귀 TOC 복원."""
    return [
        TocItem(
            level=int(t.get('level', 1)),
            number=t.get('number', ''),
            title=t.get('title', ''),
            description=t.get('description', ''),
            children=_toc_from_dict(t.get('children', [])),
        )
        for t in items
    ]


def result_from_json(data: dict) -> RfpAnalysisResult:
    """v2 to_dict() 출력 JSON → RfpAnalysisResult 복원."""
    ov_dict = data.get('overview')
    overview = Overview(**ov_dict) if ov_dict else None

    requirements = [Requirement(**r) for r in data.get('requirements', [])]
    scoring = [ScoringItem(**s) for s in data.get('scoring', [])]
    toc = _toc_from_dict(data.get('toc', []))

    cls_dict = data.get('_classification')
    classification = RfpClassification(**cls_dict) if cls_dict else None

    val_dict = data.get('_validation')
    validation = ValidationReport(**val_dict) if val_dict else None

    return RfpAnalysisResult(
        overview=overview,
        requirements=requirements,
        scoring=scoring,
        toc=toc,
        classification=classification,
        validation=validation,
        agent_trace=data.get('_agent_trace', []),
    )


def main(*src_dirs: str) -> int:
    if not src_dirs:
        src_dirs = ('sample_outputs', 'analyses')

    added = 0
    for src_dir in src_dirs:
        path = Path(src_dir)
        if not path.exists():
            continue
        for json_path in sorted(path.glob('*.json')):
            if json_path.name.startswith('_'):
                continue
            try:
                data = json.loads(json_path.read_text(encoding='utf-8'))
            except Exception as exc:
                print(f'  스킵 ({json_path.name}): {exc}')
                continue

            # storage.save_result 형식 ({meta, result}) 또는 raw to_dict()
            if 'result' in data and 'meta' in data:
                result_data = data['result']
                filename = data['meta'].get('filename', json_path.stem)
            else:
                result_data = data
                filename = json_path.stem

            try:
                result = result_from_json(result_data)
                update_library(result, filename=filename)
                added += 1
                cls = result.classification
                org = cls.org_type if cls else 'unknown'
                print(f'  + {filename[:50]:<52} ({org})')
            except Exception as exc:
                print(f'  실패 ({json_path.name}): {exc}')

    lib = load_library()
    print()
    print(f'시드 완료. 라이브러리: {len(lib)} 그룹')
    for entry in lib:
        print(f'  - {entry["org_type"]} / {entry["req_id_scheme"]} / '
              f'{entry["req_format"]} ({entry["seen_count"]}회)')
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
