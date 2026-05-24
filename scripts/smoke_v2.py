"""v2 파이프라인 E2E 스모크 — 단계별 출력.

사용법:
    python scripts/smoke_v2.py <RFP파일>
    python scripts/smoke_v2.py <RFP파일> --excel out.xlsx
    python scripts/smoke_v2.py <RFP파일> --markdown out.md
    python scripts/smoke_v2.py <RFP파일> --excel out.xlsx --markdown out.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# repo root를 sys.path에 추가 (scripts/에서 실행)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-7s %(name)-40s %(message)s',
)

from services_v2.documents import ingest_bytes
from services_v2.orchestrator import analyze_rfp_document
from services_v2.results.exporters import to_excel, to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='v2 RFP 분석 스모크')
    parser.add_argument('doc_path', nargs='?', default='test_rfp.pdf',
                       help='분석할 RFP 파일 (.pdf, .hwpx)')
    parser.add_argument('--excel', metavar='OUT.xlsx',
                       help='Excel 출력 경로')
    parser.add_argument('--markdown', metavar='OUT.md',
                       help='마크다운 보고서 출력 경로')
    parser.add_argument('--json', metavar='OUT.json',
                       help='전체 결과 JSON 경로')
    parser.add_argument('--quiet', action='store_true',
                       help='콘솔 출력 최소화 (출력 파일만)')
    args = parser.parse_args(argv)

    path = Path(args.doc_path)
    data = path.read_bytes()
    if not args.quiet:
        print(f'\n=== Stage 1: Ingest ({args.doc_path}, {len(data)} bytes) ===')
    doc = ingest_bytes(data, filename=path.name)
    if not args.quiet:
        print(json.dumps(doc.to_summary(), ensure_ascii=False, indent=2))
        print(f'본문 첫 300자: {doc.full_text[:300]!r}')
        print('\n=== Stage 2-5: 전체 파이프라인 ===')

    result = analyze_rfp_document(doc)

    # 출력 파일 저장
    if args.excel:
        buf = to_excel(result)
        Path(args.excel).write_bytes(buf.read())
        print(f'\nExcel 저장: {args.excel}')
    if args.markdown:
        md = to_markdown(result, filename=path.name)
        Path(args.markdown).write_text(md, encoding='utf-8')
        print(f'마크다운 저장: {args.markdown}')
    if args.json:
        Path(args.json).write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        print(f'JSON 저장: {args.json}')

    if args.quiet:
        return 0

    print('\n--- classification ---')
    print(json.dumps(result.classification.to_dict() if result.classification else None,
                     ensure_ascii=False, indent=2))

    print(f'\n--- overview ---')
    print(json.dumps(result.overview.to_dict() if result.overview else None,
                     ensure_ascii=False, indent=2))

    print(f'\n--- requirements ({len(result.requirements)}건) ---')
    for r in result.requirements[:5]:
        print(json.dumps(r.to_dict(), ensure_ascii=False))

    print(f'\n--- scoring ({len(result.scoring)}건, 합계={sum(s.score for s in result.scoring)}) ---')
    for s in result.scoring[:5]:
        print(json.dumps(s.to_dict(), ensure_ascii=False))

    print(f'\n--- toc ({len(result.toc)}개 L1) ---')
    for t in result.toc:
        print(f'  [{t.number}] {t.title}  (L1 자식: {len(t.children)})')

    print(f'\n--- validation ---')
    print(json.dumps(result.validation.to_dict() if result.validation else None,
                     ensure_ascii=False, indent=2))

    print(f'\n--- agent_trace ({len(result.agent_trace)} calls) ---')
    total_ms = sum(c.get('duration_ms', 0) for c in result.agent_trace)
    total_in = sum(c.get('input_chars', 0) for c in result.agent_trace)
    total_out = sum(c.get('output_chars', 0) for c in result.agent_trace)
    print(f'총 소요: {total_ms}ms, 입력 {total_in:,}자, 출력 {total_out:,}자')
    for c in result.agent_trace:
        status = 'OK' if c['success'] else f'FAIL: {c["error"]}'
        print(f'  {c["agent"]:>25s} | {c["model"]:>22s} | '
              f'{c["duration_ms"]:>6}ms | in {c["input_chars"]:>7,} | out {c["output_chars"]:>5,} | {status}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
