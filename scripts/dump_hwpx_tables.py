"""HWPX 파일의 표를 모두 덤프하여 구조 분석.

table_parser 디버깅용. 일회용 진단 스크립트.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services_v2.documents import ingest_bytes


def main(doc_path: str) -> int:
    path = Path(doc_path)
    doc = ingest_bytes(path.read_bytes(), filename=path.name)
    print(f'파일: {doc.filename}')
    print(f'표 개수: {len(doc.table_regions)}')
    print()

    for idx, table in enumerate(doc.table_regions):
        n_rows = len(table.rows)
        n_cols = max(len(r) for r in table.rows) if table.rows else 0
        header = table.rows[0] if table.rows else []
        print(f'--- 표 #{idx:03d} ({n_rows}행 × {n_cols}열) ---')
        # 헤더 후보 (첫 3행)
        for row_idx, row in enumerate(table.rows[:3]):
            preview = [c.replace('\n', '⏎')[:30] for c in row]
            print(f'  R{row_idx}: {preview}')
        if n_rows > 3:
            print(f'  ... +{n_rows - 3} more rows')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
