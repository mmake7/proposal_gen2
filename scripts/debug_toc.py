"""TOC agent 단독 호출 — 회귀 원인 추적용."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services_v2.documents import ingest_bytes
from services_v2.agents.toc import TocAgent


def main(doc_path: str = 'sample/제안요청서 (2).hwpx') -> int:
    path = Path(doc_path)
    doc = ingest_bytes(path.read_bytes(), filename=path.name)

    agent = TocAgent()

    # toc.py extract 흐름 재현 (toc_location='front' — KIAT 분류 결과)
    text = doc.full_text[:30_000]
    user_parts = [f'파일명: {doc.filename}']
    user_parts.append('목차 예상 위치: front')
    user_parts.append(f'\n--- RFP 본문 ---\n{text}')
    user_message = '\n'.join(user_parts)

    system_prompt = agent._load_prompt()
    print(f'system 길이: {len(system_prompt)}자')
    print(f'user 길이: {len(user_message)}자')
    print(f'max_tokens: {agent.max_tokens}')
    print()

    raw = agent._call_api(system_prompt, user_message)
    print(f'=== RAW ({len(raw)}자) ===')
    print(raw)
    print()

    print('=== PARSED ===')
    try:
        data = agent._parse_json(raw)
        print(f'type: {type(data).__name__}')
        if isinstance(data, dict):
            print(f'keys: {list(data.keys())}')
            toc = data.get('toc', [])
            print(f'toc length: {len(toc)}')
            if toc:
                print(f'first item: {json.dumps(toc[0], ensure_ascii=False)}')
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    except Exception as exc:
        print(f'PARSE FAILED: {exc}')

    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
