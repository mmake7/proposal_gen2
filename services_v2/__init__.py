"""ProposalPro v2 — 멀티에이전트 RFP 분석 파이프라인.

기존 services/ 패키지와 병행 운영. POST /api/parse?engine=v2 로 활성화.
"""

# 환경변수: .env → .env.local(우선) 순으로 로드.
# services_v2를 직접 import하는 스크립트(예: scripts/smoke_v2.py)에서도 유효.
import os as _os
from dotenv import load_dotenv as _load_dotenv

_PKG_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_load_dotenv(_os.path.join(_PKG_ROOT, '.env'))
_load_dotenv(_os.path.join(_PKG_ROOT, '.env.local'), override=True)
