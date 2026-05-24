"""TableRequirementParser — 표 기반 요구사항 추출.

LLM 호출 없이 RfpDocument.table_regions를 분석.
필드명 alias 사전으로 다양한 RFP 양식에 대응.
"""

from __future__ import annotations

import re

from services_v2.documents.rfp_document import RfpDocument, TableRegion
from services_v2.results.rfp_analysis import Requirement


# 필드명 alias — RFP마다 표 헤더 표기가 다름
FIELD_ALIASES: dict[str, list[str]] = {
    'id': ['요구사항 고유번호', '요구사항고유번호', '고유번호',
           '요구사항 번호', '요구사항번호', '식별번호', 'ID',
           '요구사항 No.', '요구사항No.', '요구사항 No', '요구사항No'],
    'name': ['요구사항 명칭', '요구사항명칭', '요구사항 명', '요구사항명', '항목명', '명칭'],
    'category': ['요구사항 분류', '요구사항분류', '분류', '구분', '카테고리'],
    'definition': ['정의', '개요', '개념'],
    'detail': ['세부내용', '세부 내용', '세부\n내용', '상세', '상세내용', '내용',
               '요구사항 내용', '요구사항내용', '요구사항 상세', '요구사항상세',
               '요구사항 상세설명', '요구사항상세설명', '상세설명',
               '요건 상세', '요건상세', '상세 요구사항', '상세요구사항',
               '상 세 요 구 사 항'],
    'output_info': ['산출정보', '산출 정보', '산출물', '산출자료'],
    'related_reqs': ['관련요구사항', '관련 요구사항', '연관'],
    'source': ['요구사항 출처', '요구사항출처', '출처', '근거'],
}

REQ_ID_PATTERN = re.compile(r'([A-Z]{2,3})-(\d{2,3})')

# 카테고리 코드 → 한국어 분류명 (실 RFP 3종에서 수집된 매핑)
CATEGORY_BY_CODE: dict[str, str] = {
    # 표준 분류 (전자정부 SI)
    'SFR': '기능 요구사항',
    'PER': '성능 요구사항',
    'SIR': '인터페이스 요구사항',
    'TER': '테스트 요구사항',
    'QUR': '품질 요구사항',
    'PSR': '프로젝트 지원 요구사항',
    'PMR': '프로젝트 관리 요구사항',
    'SER': '보안 요구사항',
    'DAR': '데이터 요구사항',
    'ECR': '시스템 장비구성 요구사항',
    # 유지보수·운영 분류 (실 RFP에서 자주 등장)
    'MAR': '유지보수 수행 요구사항',
    'MHR': '유지보수 인력 요구사항',
    'MPR': '유지관리 수행 요구사항',
    'OMR': '운영 및 유지관리 요구사항',
    'TSR': '테스트/시험 요구사항',
    # 컨설팅·제약
    'COR': '제약사항',
    'CSR': '컨설팅 요구사항',
}


def parse_tables(doc: RfpDocument) -> list[Requirement]:
    """문서의 모든 table_regions에서 요구사항을 추출.

    같은 ID가 여러 표에서 등장하면(예: 인덱스 표와 본문 세로형 표),
    채워진 필드가 많은 쪽을 유지. ID 없는 결과는 별도 보존.
    """
    by_id: dict[str, Requirement] = {}
    order: list[str] = []
    extras: list[Requirement] = []

    for table in doc.table_regions:
        for req in _parse_one_table(table):
            if req.id:
                existing = by_id.get(req.id)
                if existing is None:
                    by_id[req.id] = req
                    order.append(req.id)
                elif _filled_count(req) > _filled_count(existing):
                    by_id[req.id] = req  # 풍부한 쪽으로 교체 (순서는 유지)
            else:
                extras.append(req)

    return [by_id[i] for i in order] + extras


def _filled_count(req: Requirement) -> int:
    """채워진 필드 수 — 결과 품질 비교용."""
    fields = ('name', 'category', 'definition', 'detail',
              'output_info', 'related_reqs', 'source')
    return sum(1 for f in fields if getattr(req, f))


def _parse_one_table(table: TableRegion) -> list[Requirement]:
    if not table.rows or len(table.rows) < 2:
        return []

    # 우선순위 1: 세로형 (한 표 = 한 요구사항, 첫 컬럼=필드명)
    # KIAT/한국 공공 SI 표준 양식. 가로형보다 더 흔함.
    vertical = _try_vertical(table.rows)
    if vertical is not None:
        return [vertical]

    # 우선순위 2: 가로형 (한 행 = 한 요구사항, 첫 행=헤더)
    header_row = table.rows[0]
    field_map = _map_headers(header_row)
    if 'id' not in field_map and not _has_req_id(header_row):
        # 첫 행이 헤더 아닐 수도 — 두 번째 행 시도
        if len(table.rows) > 1:
            alt = _map_headers(table.rows[1])
            if 'id' in alt:
                field_map = alt
                data_rows = table.rows[2:]
            else:
                # ID alias 없지만 (category + detail) 또는 (name + detail) 매핑되면 처리
                # 예: [구분, 요건 상세] — 아이부자 양식
                if _has_id_free_match(field_map) and len(table.rows) > 1:
                    data_rows = table.rows[1:]
                else:
                    return []
        else:
            return []
    else:
        data_rows = table.rows[1:]

    if 'id' in field_map and len(data_rows) > 0:
        return _parse_horizontal(field_map, data_rows)
    if _has_id_free_match(field_map) and len(data_rows) > 0:
        return _parse_horizontal(field_map, data_rows)

    return []


def _has_id_free_match(field_map: dict[str, int]) -> bool:
    """ID alias 없지만 (category|name) + detail 매핑이 있으면 ID-free 요구사항 표로 인정."""
    has_detail = 'detail' in field_map or 'definition' in field_map
    has_label = 'category' in field_map or 'name' in field_map
    return has_detail and has_label


def _try_vertical(rows: list[list[str]]) -> Requirement | None:
    """세로형 표 인식: 첫 컬럼 = 필드명, 두 번째+ 컬럼 = 값.

    한국 공공 SI RFP의 표준 요구사항 양식. 한 표가 한 요구사항을 표현.
    예:
        | 요구사항 분류    | 보안요구사항(SER) |
        | 요구사항 고유번호 | SER-001          |
        | 요구사항 명칭    | 보안 일반사항    |
        | 정의             | ...              |
        | 세부내용         | ...              |
    """
    field_values: dict[str, str] = {}

    # Step 1: 단독 셀(병합셀 헤더 등)에서 ID 패턴 추출
    for row in rows:
        if len(row) == 1 and row[0]:
            cell = row[0].strip()
            if REQ_ID_PATTERN.search(cell):
                field_values['id'] = cell
                break

    # 세로형 판정: 첫 컬럼에 필드명이 ≥2개 행에서 매칭되어야 진짜 세로형
    # (가로형 헤더가 우연히 alias와 겹치는 false positive 방지)
    first_col_matches = sum(
        1 for row in rows
        if len(row) >= 2 and _resolve_alias((row[0] or '').strip()) is not None
    )
    if first_col_matches < 2:
        return None

    for row in rows:
        if len(row) < 2:
            continue
        field_name_0 = (row[0] or '').strip()
        field_name_1 = (row[1] or '').strip() if len(row) > 1 else ''
        std_key_0 = _resolve_alias(field_name_0)
        std_key_1 = _resolve_alias(field_name_1) if field_name_1 else None

        if std_key_0 and std_key_1 and len(row) >= 3:
            # ISP 양식: [메인필드, 서브필드, 값] — 서브필드 우선 매핑
            # 예: ['요구사항 내용', '정의', '국유재산 관리 체계 분석']
            #     → definition='국유재산 관리 체계 분석' (메인 '요구사항 내용'은 건너뜀)
            if std_key_1 not in field_values:
                field_values[std_key_1] = (row[2] or '').strip()
        elif std_key_0:
            # 기본: row[0]/[1] 페어
            if std_key_0 not in field_values:
                field_values[std_key_0] = (row[1] or '').strip()

        # 보조: row[2]/[3] 추가 페어 (전자인장 RFP처럼 한 행에 2 페어 펼쳐진 양식)
        # 단, ISP 양식(row[1]이 alias)에선 row[2]를 이미 값으로 썼으므로 skip
        if len(row) >= 4 and not (std_key_0 and std_key_1):
            field_name2 = (row[2] or '').strip()
            std_key2 = _resolve_alias(field_name2)
            if std_key2 and std_key2 not in field_values:
                field_values[std_key2] = (row[3] or '').strip()

    # 요구사항 표 신뢰 조건: id 또는 name 중 하나 + 최소 2개 표준 필드
    matched = {k for k, v in field_values.items() if v}
    if 'id' not in matched and 'name' not in matched:
        return None
    if len(matched) < 2:
        return None

    req = Requirement(parse_method='table')
    for key, value in field_values.items():
        setattr(req, key, value)
    if req.id:
        m = REQ_ID_PATTERN.search(req.id)
        if m:
            req.category_code = m.group(1)
            # category 컬럼이 표에 없을 때 prefix로 자동 채움
            if not req.category and req.category_code in CATEGORY_BY_CODE:
                req.category = CATEGORY_BY_CODE[req.category_code]
    parts = [p for p in (req.definition, req.detail) if p]
    req.desc = '\n'.join(parts)
    return req


def _resolve_alias(field_name: str) -> str | None:
    """공백/줄바꿈 무시하고 alias 사전에서 표준 키 찾기."""
    if not field_name:
        return None
    normalized = re.sub(r'\s+', '', field_name)
    if not normalized:
        return None
    for std_key, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if re.sub(r'\s+', '', alias) == normalized:
                return std_key
    return None


def _map_headers(row: list[str]) -> dict[str, int]:
    """헤더 셀 → 표준 키 매핑."""
    result: dict[str, int] = {}
    for col_idx, cell in enumerate(row):
        if not cell:
            continue
        normalized = re.sub(r'\s+', '', cell.strip())
        for std_key, aliases in FIELD_ALIASES.items():
            if std_key in result:
                continue
            for alias in aliases:
                if re.sub(r'\s+', '', alias) == normalized:
                    result[std_key] = col_idx
                    break
    return result


def _has_req_id(row: list[str]) -> bool:
    return any(cell and REQ_ID_PATTERN.search(cell) for cell in row)


def _parse_horizontal(
    field_map: dict[str, int],
    data_rows: list[list[str]],
) -> list[Requirement]:
    results: list[Requirement] = []
    for row in data_rows:
        if not row or not any(cell.strip() if cell else '' for cell in row):
            continue
        req = Requirement(parse_method='table')
        for key, col_idx in field_map.items():
            if col_idx < len(row):
                value = (row[col_idx] or '').strip()
                setattr(req, key, value)

        # 컬럼 시프트 가드: id 값이 ID 패턴이 아니고 name도 없으면 신뢰 못 함
        # (병합셀로 데이터 행 컬럼이 밀려 들어간 케이스)
        id_looks_real = bool(req.id and REQ_ID_PATTERN.search(req.id))
        if req.id and not id_looks_real and not req.name:
            continue

        # ID에서 분류 코드 추출 + category 자동 매핑
        if id_looks_real:
            req.category_code = REQ_ID_PATTERN.search(req.id).group(1)
            if not req.category and req.category_code in CATEGORY_BY_CODE:
                req.category = CATEGORY_BY_CODE[req.category_code]

        # desc 합성 (v1 호환)
        parts = [p for p in (req.definition, req.detail) if p]
        req.desc = '\n'.join(parts)

        # 행 유효성: id/name 있거나, ID-free 양식이면 category+detail 페어로 인정
        if req.id or req.name or (req.category and req.detail):
            results.append(req)
    return results
