"""영업 견적 산정 — WBS / 조직도 / Man-Month.

기본은 결정적 휴리스틱 (LLM 없이). 추후 LLM 보강 가능.
"""

from __future__ import annotations

from services_v2.estimation.heuristic import estimate_from_analysis

__all__ = ['estimate_from_analysis']
