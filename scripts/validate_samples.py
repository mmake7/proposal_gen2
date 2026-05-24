"""sample/ 디렉토리의 모든 RFP에 대해 결정적 추출 결과를 표로 표시.

LLM 호출 없이 ingest + table_parser + scoring detector만 빠르게 검증.
새 RFP를 sample/에 추가한 후 회귀 빠르게 확인용.

사용법:
    python scripts/validate_samples.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services_v2.agents.requirements.table_parser import (
    _filled_count, parse_tables,
)
from services_v2.agents.scoring import find_scoring_table_candidates
from services_v2.documents import ingest_bytes
from services_v2.results.storage import summarize_gallery


def main(sample_dir: str = 'sample') -> int:
    root = Path(sample_dir)
    if not root.exists():
        print(f'디렉토리 없음: {root}')
        return 1

    rfps = sorted(p for p in root.iterdir()
                  if p.suffix.lower() in ('.pdf', '.hwpx', '.docx'))
    if not rfps:
        print(f'{root}에 RFP 없음 (.pdf/.hwpx)')
        return 1

    print(f'sample/에서 발견된 RFP {len(rfps)}건\n')
    print(f'{"파일명":<42} {"표":>5} {"텍스트":>9} {"챕터":>5} '
          f'{"요구사항":>7} {"카테고리":>8} {"평가표":>7} {"풍부도":>7}')
    print('─' * 100)

    for path in rfps:
        try:
            doc = ingest_bytes(path.read_bytes(), filename=path.name)
        except Exception as exc:
            print(f'{path.name[:42]:<42}  INGEST FAIL: {exc}')
            continue

        reqs = parse_tables(doc)
        cats = Counter(r.category_code or '?' for r in reqs)
        chapter_markers = sum(1 for ln in doc.full_text.split('\n')
                              if ln.startswith('[Chapter '))
        scoring_cands = find_scoring_table_candidates(doc)
        avg_filled = (sum(_filled_count(r) for r in reqs) / max(len(reqs), 1))

        print(
            f'{path.name[:42]:<42} '
            f'{len(doc.table_regions):>5} '
            f'{doc.total_chars:>9,} '
            f'{chapter_markers:>5} '
            f'{len(reqs):>7} '
            f'{len(cats):>8} '
            f'{len(scoring_cands):>7} '
            f'{avg_filled:>7.1f}'
        )

    print()
    print('범례:')
    print('  표        — 추출된 hwpx/pdf 표 개수')
    print('  텍스트    — 본문 텍스트 글자수')
    print('  챕터      — [Chapter ...] 인라인 마커 개수 (TOC 힌트)')
    print('  요구사항  — table_parser 결정적 추출 건수 (LLM 없이)')
    print('  카테고리  — 추출된 요구사항의 카테고리 코드 종류')
    print('  평가표    — scoring detector가 찾은 평가표 후보 개수')
    print('  풍부도    — 요구사항당 평균 채워진 필드 수 (max 7)')

    # 누적 갤러리 요약 (V2_AUTO_SAVE=1로 분석된 결과들)
    gallery = summarize_gallery()
    if gallery.get('total', 0) > 0:
        print()
        print('━' * 100)
        print(f'누적 분석 갤러리 (analyses/): {gallery["total"]}건')
        avg = gallery.get('avg_confidence')
        if avg is not None:
            print(f'  평균 신뢰도: {avg:.2f}')
        print(f'  평균 요구사항: {gallery["avg_requirements"]:.0f}건/RFP')
        if gallery['by_org_type']:
            print(f'  발주기관 분포: {gallery["by_org_type"]}')
        if gallery['by_req_format']:
            print(f'  요구사항 형식: {gallery["by_req_format"]}')
        if gallery['low_confidence_files']:
            print(f'  ⚠️ 신뢰도 낮음 (<0.7): {gallery["low_confidence_files"][:5]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
