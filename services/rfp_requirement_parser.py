"""
RFP 요구사항 테이블 파싱 모듈
==============================
한국 공공부문 RFP PDF에서 요구사항을 구조화하여 추출합니다.

지원 형식:
- 2자리 ID (SFR-01) / 3자리 ID (SFR-001)
- 다양한 필드명 변형 자동 인식
- pdfplumber 테이블 추출 + 텍스트 정규식 하이브리드

사용법:
    from services.rfp_requirement_parser import parse_rfp_requirements
    result = parse_rfp_requirements("path/to/rfp.pdf")
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 모델
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RequirementSummary:
    category: str       # "기능 요구사항"
    code: str           # "SFR"
    description: str
    count: int

@dataclass
class Requirement:
    req_id: str         # "SFR-01" or "SFR-001"
    name: str
    category: str
    category_code: str
    definition: str = ""
    detail: str = ""
    output_info: str = ""
    related_reqs: str = ""
    source: str = ""
    parse_method: str = ""  # table / text / ai / list_only

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수 & 패턴
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REQ_ID_PATTERN = re.compile(r'([A-Z]{2,3})-(\d{2,3})')

KNOWN_CODES = {
    'SFR': '기능 요구사항',
    'PER': '성능 요구사항',
    'SIR': '인터페이스 요구사항',
    'TER': '테스트 요구사항',
    'QUR': '품질 요구사항',
    'PSR': '프로젝트 지원 요구사항',
    'MPR': '유지관리 수행 요구사항',
    'DAR': '데이터 요구사항',
    'PMR': '프로젝트 관리 요구사항',
    'SER': '보안 요구사항',
    'COR': '제약사항',
    'ECR': '시스템 장비구성 요구사항',
    'CSR': '컨설팅 요구사항',
}

# 필드명 매핑 (다양한 변형 → 통합 키)
FIELD_PATTERNS = {
    'req_id': ['요구사항 고유번호', '요구사항고유번호', '고유번호',
               '요구사항 번호', '요구사항번호'],
    'name': ['요구사항 명칭', '요구사항명칭', '요구사항 명', '요구사항명'],
    'category': ['요구사항 분류', '요구사항분류'],
    'definition': ['정의'],
    'detail': ['세부내용', '세부\n내용', '세부 내용'],
    'output_info': ['산출정보', '산출 정보'],
    'related_reqs': ['관련요구사항', '관련 요구사항'],
    'source': ['요구사항 출처', '요구사항출처'],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _norm(text):
    """공백/개행 정규화"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()


def _match_field(label):
    """셀 라벨 → 필드명 매핑"""
    if not label:
        return None
    clean = _norm(label)
    for fld, patterns in FIELD_PATTERNS.items():
        for p in patterns:
            if p in clean:
                return fld
    return None


def _code_from_id(req_id):
    """SFR-01 → SFR"""
    m = REQ_ID_PATTERN.match(str(req_id))
    return m.group(1) if m else ""


def _make_req(data, method):
    """dict → Requirement"""
    rid = data.get('req_id', '')
    code = _code_from_id(rid)
    return Requirement(
        req_id=rid,
        name=data.get('name', ''),
        category=data.get('category', KNOWN_CODES.get(code, '')),
        category_code=code,
        definition=data.get('definition', ''),
        detail=data.get('detail', ''),
        output_info=data.get('output_info', ''),
        related_reqs=data.get('related_reqs', ''),
        source=data.get('source', ''),
        parse_method=method,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 1: pdfplumber 테이블 추출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_all(pdf_path):
    """PDF → 테이블 + 전체 텍스트"""
    import pdfplumber
    tables, full_text = [], ""
    with pdfplumber.open(pdf_path) as pdf:
        for pn, page in enumerate(pdf.pages):
            full_text += f"\n--- PAGE {pn+1} ---\n" + (page.extract_text() or "")
            for tbl in page.extract_tables():
                if tbl and len(tbl) > 0:
                    tables.append({'page': pn+1, 'data': tbl})
    return tables, full_text


def _classify(tbl):
    """테이블 유형: summary / list / detail / unknown"""
    data = tbl['data']
    if not data or len(data) < 2:
        return 'unknown'

    # 개행 포함 원본 + 공백 정규화 양쪽으로 검사
    flat_raw = ' '.join(str(c) for row in data for c in row if c)
    flat = re.sub(r'\s+', ' ', flat_raw)

    # detail: ID필드 + 정의/세부내용 필드 동시 존재
    id_keywords = ['고유번호', '요구사항번호', '요구사항 번호']
    has_id_fld = any(k in flat for k in id_keywords)
    # 개행 포함 변형도 체크 ("요구사항\n고유번호", "세부\n내용")
    if not has_id_fld:
        has_id_fld = any(k in flat_raw for k in id_keywords)

    has_def = '정의' in flat
    has_detail = '세부' in flat and ('내용' in flat or '내용' in flat_raw)
    # 명칭 + 정의만 있어도 detail (세부내용 없이 카드형인 경우)
    has_name_fld = any(k in flat for k in ['요구사항 명칭', '요구사항명칭', '요구사항 명', '요구사항명'])

    if has_id_fld and (has_def or has_detail):
        return 'detail'
    if has_id_fld and has_name_fld and has_def:
        return 'detail'

    # summary: 개수/합계 + 분류 설명
    has_cnt = any(k in flat for k in ['개수', '요구사항수', '합계'])
    if has_cnt and any(k in flat for k in ['설 명', '설명', 'Req']):
        return 'summary'

    # list: ID 패턴 다수 존재
    id_cnt = sum(1 for row in data for c in row if c and REQ_ID_PATTERN.search(str(c)))
    if id_cnt >= 3 and not (has_def and has_detail):
        return 'list'

    return 'unknown'


def _parse_summary(data):
    """요약 테이블 → [RequirementSummary]"""
    results = []
    seen = set()
    total_from_합계 = 0

    for row in data:
        if not row:
            continue
        txt = ' '.join(str(c) for c in row if c)

        # 합계 행에서 전체 카운트 추출
        if '합계' in txt:
            for c in row:
                if c and re.fullmatch(r'\d+', str(c).strip()):
                    total_from_합계 = int(str(c).strip())
            continue

        for code, defname in KNOWN_CODES.items():
            if code in txt and code not in seen:
                # 1차: 셀 단위로 순수 숫자 감지 (코드가 포함된 셀은 제외)
                cnt = 0
                for c in row:
                    if not c:
                        continue
                    cs = str(c).strip()
                    if re.fullmatch(r'\d+', cs):
                        cnt = int(cs)
                # 2차: 전체 행에서 독립 숫자
                if cnt == 0:
                    nums = re.findall(r'(?<![A-Z\-])(\d+)(?![A-Z\-\d])', txt)
                    if nums:
                        cnt = int(nums[-1])

                # 분류명 찾기
                cat = defname
                for c in row:
                    if c:
                        ct = _norm(str(c))
                        if ('요구사항' in ct or '제약' in ct) and code not in ct and len(ct) > 4:
                            cat = ct
                            break
                results.append(RequirementSummary(cat, code, txt[:100], cnt))
                seen.add(code)
                break

    # 개별 카운트가 모두 0이면 합계를 균등 배분
    if results and all(s.count == 0 for s in results) and total_from_합계 > 0:
        logger.info(f"개별 카운트 없음, 합계 {total_from_합계} 사용")
        for s in results:
            s.count = 0  # 개별은 모르지만 합계는 알림
        # 합계를 stats에서 사용할 수 있도록 첫 항목에 메타 저장
        results[0].description = f"합계:{total_from_합계}|" + results[0].description

    return results


def _parse_list(data):
    """목록 테이블 → [{"req_id": ..., "name": ..., "category": ...}]"""
    items = []
    cur_cat = ""
    for row in data:
        if not row:
            continue
        txt = ' '.join(str(c) for c in row if c)
        # 헤더 행 스킵
        if '요구사항 분류' in txt and ('번호' in txt or '명칭' in txt):
            continue

        found_id = None
        for c in row:
            if c and REQ_ID_PATTERN.match(str(c).strip()):
                found_id = str(c).strip()
                break
        if not found_id:
            continue

        # 명칭 = ID가 아닌 가장 긴 텍스트 셀
        name = ""
        for c in row:
            if c:
                ct = str(c).strip()
                if ct != found_id and not REQ_ID_PATTERN.match(ct) and len(ct) > len(name):
                    # 짧은 분류명은 제외
                    if len(ct) > 2:
                        name = ct

        # 분류 업데이트
        for c in row:
            if c:
                ct = str(c).strip()
                if ('요구사항' in ct or '제약' in ct) and len(ct) < 30 and ct != name:
                    cur_cat = _norm(ct)

        items.append({'req_id': found_id, 'name': _norm(name), 'category': cur_cat})
    return items


def _match_field_raw(cell_text):
    """개행 포함 원본 셀에서 필드명 매핑 (정규화 전)"""
    if not cell_text:
        return None
    # 원본 그대로 먼저
    for fld, patterns in FIELD_PATTERNS.items():
        for p in patterns:
            if p in cell_text:
                return fld
    # 공백/개행 정규화 후
    return _match_field(cell_text)


def _split_label_value(cell_text):
    """라벨+값이 동일 셀에 있는 경우 분리. 예: '정의 시스템을 구축한다'"""
    if not cell_text:
        return None, None
    for fld, patterns in FIELD_PATTERNS.items():
        for p in patterns:
            # 정규화된 비교
            norm_cell = _norm(cell_text)
            if norm_cell.startswith(p):
                val = norm_cell[len(p):].strip()
                if val:
                    return fld, val
            # 개행 기준 분리: "세부\n내용\n실제 값..." → fld=detail, val=실제 값
            if '\n' in cell_text and p.replace('\n', ' ') in _norm(cell_text):
                lines = cell_text.split('\n')
                # 라벨 부분 스킵하고 나머지를 값으로
                label_words = set(p.replace('\n', ' ').split())
                val_lines = []
                past_label = False
                for line in lines:
                    stripped = line.strip()
                    if not past_label and any(w in stripped for w in label_words):
                        past_label = True
                        # 라벨 행에 값도 같이 있을 수 있음
                        remainder = stripped
                        for w in label_words:
                            remainder = remainder.replace(w, '', 1)
                        remainder = remainder.strip()
                        if remainder:
                            val_lines.append(remainder)
                        continue
                    if past_label or (not label_words & set(stripped.split())):
                        val_lines.append(stripped)
                val = '\n'.join(val_lines).strip()
                if val:
                    return fld, val
    return None, None


def _parse_detail_tables(tables):
    """상세 카드 테이블들 → [Requirement]"""
    reqs = []
    for tbl in tables:
        if _classify(tbl) != 'detail':
            continue

        cur = {}
        last_fld = None  # 마지막으로 인식된 필드 (연속행 누적용)

        for row in tbl['data']:
            if not row or all(c is None for c in row):
                continue
            cells_raw = [str(c).strip() if c else "" for c in row]
            cells = [_norm(c) for c in cells_raw]

            matched_any = False

            for i, cell_raw in enumerate(cells_raw):
                cell = cells[i]

                # ① 라벨 셀 + 다음 셀이 값인 패턴
                fld = _match_field_raw(cell_raw)
                if fld and i + 1 < len(cells_raw):
                    # 값 = 같은 행에서 라벨이 아닌 뒤쪽 셀 합치기
                    val_parts = []
                    for c in cells_raw[i+1:]:
                        if c and _match_field_raw(c) is None:
                            val_parts.append(c)
                    val = '\n'.join(val_parts).strip() if fld == 'detail' else _norm(' '.join(val_parts))

                    if fld == 'req_id' and REQ_ID_PATTERN.search(val):
                        if cur.get('req_id'):
                            reqs.append(_make_req(cur, 'table'))
                        cur = {'req_id': REQ_ID_PATTERN.search(val).group(0)}
                        last_fld = None
                    else:
                        if fld == 'detail' and cur.get('detail'):
                            cur['detail'] += '\n' + val
                        else:
                            cur[fld] = val
                        last_fld = fld
                    matched_any = True
                    break

                # ② 라벨+값이 동일 셀에 있는 패턴
                fld2, val2 = _split_label_value(cell_raw)
                if fld2 and val2:
                    if fld2 == 'req_id' and REQ_ID_PATTERN.search(val2):
                        if cur.get('req_id'):
                            reqs.append(_make_req(cur, 'table'))
                        cur = {'req_id': REQ_ID_PATTERN.search(val2).group(0)}
                        last_fld = None
                    else:
                        if fld2 == 'detail' and cur.get('detail'):
                            cur['detail'] += '\n' + val2
                        else:
                            cur[fld2] = val2
                        last_fld = fld2
                    matched_any = True
                    break

                # ③ 셀 자체가 ID
                if REQ_ID_PATTERN.match(cell) and len(cell) < 10:
                    if cur.get('req_id'):
                        reqs.append(_make_req(cur, 'table'))
                    cur = {'req_id': REQ_ID_PATTERN.match(cell).group(0)}
                    last_fld = None
                    # 같은 행의 나머지 셀에서 정보 추출
                    for j, oc_raw in enumerate(cells_raw):
                        if j != i and oc_raw:
                            f2 = _match_field_raw(oc_raw)
                            if f2 and j + 1 < len(cells_raw) and cells_raw[j+1]:
                                cur[f2] = _norm(cells_raw[j+1])
                            elif f2:
                                f2s, v2s = _split_label_value(oc_raw)
                                if f2s and v2s:
                                    cur[f2s] = v2s
                    matched_any = True
                    break

            # ④ 라벨 없는 연속 콘텐츠 행 → 직전 필드에 누적
            if not matched_any and cur.get('req_id') and last_fld:
                # 행의 모든 비어있지 않은 셀을 합침
                content_parts = [c for c in cells_raw if c and not _match_field_raw(c)]
                if content_parts:
                    extra = '\n'.join(content_parts).strip() if last_fld == 'detail' else _norm(' '.join(content_parts))
                    if extra and cur.get(last_fld):
                        cur[last_fld] += '\n' + extra
                    elif extra:
                        cur[last_fld] = extra

        if cur.get('req_id'):
            reqs.append(_make_req(cur, 'table'))
    return reqs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 2: 텍스트 기반 정규식 파싱
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_from_text(full_text):
    """전체 텍스트에서 정규식으로 요구사항 블록 추출"""
    reqs = []

    # 모든 ID 출현 위치
    positions = []
    for m in REQ_ID_PATTERN.finditer(full_text):
        ctx = full_text[max(0, m.start()-100):m.start()]
        # 상세 카드 내부의 ID (고유번호/요구사항번호 라벨 근처)
        is_detail = any(k in ctx for k in ['고유번호', '요구사항번호', '요구사항 번호', '요구사항번호'])
        positions.append({'id': m.group(0), 'pos': m.start(), 'detail': is_detail})

    detail_pos = [p for p in positions if p['detail']]
    if not detail_pos:
        # 폴백: 중복 제거 후 첫 출현만
        seen = set()
        for p in positions:
            if p['id'] not in seen:
                detail_pos.append(p)
                seen.add(p['id'])

    for i, info in enumerate(detail_pos):
        start = info['pos']
        end = detail_pos[i+1]['pos'] if i+1 < len(detail_pos) else min(start + 5000, len(full_text))
        block = full_text[start:end]

        data = {'req_id': info['id']}

        # 명칭: "요구사항 명" 라벨 뒤 ~ 다음 라벨까지
        for pat in [
            r'요구사항\s*명칭?\s+(.+?)(?:\n요구사항|\n정의|\n상세)',
            r'요구사항\s*명\s+(.+?)(?:\n)',
        ]:
            m = re.search(pat, block)
            if m:
                data['name'] = _norm(m.group(1))
                break

        # 분류
        m = re.search(r'요구사항\s*분류\s+(.+?)(?:\n)', block)
        if m:
            data['category'] = _norm(m.group(1))

        # 정의: "정의" 라벨 뒤 ~ "세부" 또는 "상세" 앞
        m = re.search(r'(?:^|\n)정의\s+(.+?)(?:\n상세|\n세부|$)', block, re.DOTALL)
        if not m:
            m = re.search(r'정의\s+(.+?)(?:\n상세|\n세부|\nm\s|$)', block, re.DOTALL)
        if m:
            data['definition'] = _norm(m.group(1)[:500])

        # 세부내용: 여러 변형 패턴
        # 패턴1: "세부\n내용" 또는 "세부내용" 뒤
        # 패턴2: "상세\n세부\n설명\n내용" (4행 분리 라벨) 뒤의 콘텐츠
        detail_text = ""
        for pat in [
            r'(?:세부\s*내용|설명\s*\n\s*내용)\s+(.+?)(?:\n산출정보|\n산출 정보|\n관련\s*요구사항|\n요구사항\s*출처|$)',
            r'내용\s+(.+?)(?:\n산출정보|\n산출 정보|\n관련\s*요구사항|\n요구사항\s*출처|$)',
        ]:
            m = re.search(pat, block, re.DOTALL)
            if m and len(m.group(1).strip()) > 5:
                detail_text = m.group(1).strip()[:5000]
                break

        # 패턴3: 정의와 산출정보 사이의 모든 텍스트 (상세/세부 라벨 포함)
        if not detail_text:
            m = re.search(
                r'정의\s+.+?\n((?:상세|세부|설명|내용|m\s).+?)(?:\n산출정보|\n산출 정보|\n관련\s*요구사항|\n요구사항\s*번호|\n요구사항번호|$)',
                block, re.DOTALL,
            )
            if m:
                raw = m.group(1)
                # 라벨 행 제거
                lines = raw.split('\n')
                content_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped in ('상세', '세부', '설명', '내용', '세부내용'):
                        continue
                    if stripped:
                        content_lines.append(stripped)
                detail_text = '\n'.join(content_lines)[:5000]

        if detail_text:
            data['detail'] = detail_text

        # 산출정보
        m = re.search(r'산출\s*정보\s+(.+?)(?:\n관련|\n요구사항\s*출처|$)', block, re.DOTALL)
        if m:
            data['output_info'] = _norm(m.group(1)[:500])

        # 관련 요구사항
        m = re.search(r'관련\s*요구사항\s+(.+?)(?:\n요구사항\s*출처|\n요구사항번호|\n요구사항 번호|$)', block, re.DOTALL)
        if m:
            val = _norm(m.group(1)[:200])
            if val and val != '없음':
                data['related_reqs'] = val

        reqs.append(_make_req(data, 'text'))
    return reqs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 병합 & 보완
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _merge(table_reqs, text_reqs):
    """테이블(우선) + 텍스트 결과 병합"""
    merged = {}
    for r in table_reqs:
        merged[r.req_id] = r
    for r in text_reqs:
        if r.req_id not in merged:
            merged[r.req_id] = r
        else:
            ex = merged[r.req_id]
            if not ex.name and r.name: ex.name = r.name
            if not ex.definition and r.definition: ex.definition = r.definition
            if not ex.detail and r.detail: ex.detail = r.detail
            if not ex.output_info and r.output_info: ex.output_info = r.output_info
            if not ex.related_reqs and r.related_reqs: ex.related_reqs = r.related_reqs
            if not ex.source and r.source: ex.source = r.source
    return sorted(merged.values(), key=lambda r: r.req_id)


def _enrich_from_list(reqs, req_list):
    """목록 테이블 정보로 보완 + 누락 추가"""
    lmap = {i['req_id']: i for i in req_list}
    for r in reqs:
        if r.req_id in lmap:
            if not r.name:
                r.name = lmap[r.req_id].get('name', '')
            if not r.category:
                r.category = lmap[r.req_id].get('category', '')

    existing = {r.req_id for r in reqs}
    for item in req_list:
        if item['req_id'] not in existing:
            code = _code_from_id(item['req_id'])
            reqs.append(Requirement(
                req_id=item['req_id'],
                name=item.get('name', ''),
                category=item.get('category', KNOWN_CODES.get(code, '')),
                category_code=code,
                parse_method='list_only',
            ))
    return sorted(reqs, key=lambda r: r.req_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_rfp_requirements(pdf_path: str) -> dict:
    """
    RFP PDF에서 요구사항을 구조화 추출.

    Returns:
        {
            "summary": [{"category", "code", "description", "count"}, ...],
            "requirements": [{"req_id", "name", "category", ...}, ...],
            "requirement_list": [{"req_id", "name", "category"}, ...],
            "stats": {"expected_total", "parsed_total", "completeness_pct", ...},
            "raw_text": str,
        }
    """
    logger.info(f"RFP 파싱 시작: {pdf_path}")

    try:
        all_tables, full_text = _extract_all(pdf_path)
    except Exception as e:
        logger.error(f"PDF 추출 실패: {e}")
        return {"summary": [], "requirements": [], "requirement_list": [],
                "stats": {"error": str(e)}, "raw_text": ""}

    logger.info(f"테이블 {len(all_tables)}개 추출")

    # 테이블별 분류 & 파싱
    summaries, req_list, table_reqs = [], [], []
    for tbl in all_tables:
        t = _classify(tbl)
        if t == 'summary':
            summaries.extend(_parse_summary(tbl['data']))
        elif t == 'list':
            req_list.extend(_parse_list(tbl['data']))

    table_reqs = _parse_detail_tables(all_tables)
    logger.info(f"테이블: 요약 {len(summaries)}건, 목록 {len(req_list)}건, 상세 {len(table_reqs)}건")

    # 텍스트 보완
    text_reqs = _parse_from_text(full_text)
    logger.info(f"텍스트: {len(text_reqs)}건")

    # 병합
    merged = _merge(table_reqs, text_reqs)
    if req_list:
        merged = _enrich_from_list(merged, req_list)

    # 통계
    expected = sum(s.count for s in summaries)
    # 합계 폴백: 개별 카운트가 0이고 description에 합계가 있는 경우
    if expected == 0 and summaries:
        for s in summaries:
            m = re.match(r'합계:(\d+)\|', s.description)
            if m:
                expected = int(m.group(1))
                s.description = s.description.split('|', 1)[1]
                break
    # req_list 폴백: 여전히 0이면 목록 테이블 기준
    if expected == 0 and req_list:
        expected = len(req_list)

    list_ids = {i['req_id'] for i in req_list}
    parsed_ids = {r.req_id for r in merged}
    missing = sorted(list_ids - parsed_ids) if list_ids else []

    stats = {
        "expected_total": expected,
        "parsed_total": len(merged),
        "table_parsed": sum(1 for r in merged if r.parse_method == 'table'),
        "text_parsed": sum(1 for r in merged if r.parse_method == 'text'),
        "list_only": sum(1 for r in merged if r.parse_method == 'list_only'),
        "missing_detail_ids": missing,
        "completeness_pct": round(len(merged) / expected * 100, 1) if expected else 0,
        "detail_completeness_pct": round(
            sum(1 for r in merged if r.detail) / len(merged) * 100, 1
        ) if merged else 0,
        "categories_found": len(summaries),
    }

    logger.info(f"완료: {stats['parsed_total']}/{stats['expected_total']}건 ({stats['completeness_pct']}%)")

    return {
        "summary": [asdict(s) for s in summaries],
        "requirements": [asdict(r) for r in merged],
        "requirement_list": req_list,
        "stats": stats,
        "raw_text": full_text,
    }


def get_ai_보완_prompt(parse_result: dict) -> str:
    """
    AI에게 누락된 요구사항 추출을 요청하는 프롬프트 생성.
    rfp_analyzer.py에서 Claude API 호출 시 사용.
    """
    stats = parse_result['stats']
    if stats.get('detail_completeness_pct', 0) >= 95:
        return ""

    parsed_ids = [r['req_id'] for r in parse_result['requirements']]
    missing = stats.get('missing_detail_ids', [])
    incomplete = [
        r['req_id'] for r in parse_result['requirements']
        if not r.get('detail') and r.get('parse_method') != 'list_only'
    ]

    target_ids = missing + incomplete

    return f"""다음 RFP 원문에서 아래 요구사항의 상세 정보를 JSON 배열로 추출해주세요.

[추출 대상 ID]
{', '.join(target_ids[:50])}

[이미 완료된 ID] (제외)
{', '.join(parsed_ids)}

[JSON 형식]
[{{"req_id":"SFR-01","name":"명칭","category":"분류","definition":"정의","detail":"세부내용 전문","output_info":"산출정보","related_reqs":"관련 요구사항","source":"출처"}}]

[RFP 원문 (일부)]
{parse_result['raw_text'][:25000]}"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python rfp_requirement_parser.py <rfp.pdf>")
        sys.exit(1)

    result = parse_rfp_requirements(sys.argv[1])

    print("\n" + "=" * 60)
    print("파싱 결과")
    print("=" * 60)

    print(f"\n[분류 요약] {len(result['summary'])}개")
    for s in result['summary']:
        print(f"  {s['code']:5s} {s['category'][:25]:25s} {s['count']}건")

    print(f"\n[요구사항] {len(result['requirements'])}건")
    for r in result['requirements'][:8]:
        d = (r['detail'][:60] + '...') if len(r.get('detail', '')) > 60 else r.get('detail', '-')
        print(f"  {r['req_id']:10s} {r['name'][:30]:30s} [{r['parse_method']:6s}] {d}")
    if len(result['requirements']) > 8:
        print(f"  ... +{len(result['requirements'])-8}건")

    s = result['stats']
    print(f"\n[통계]")
    print(f"  기대: {s['expected_total']} | 파싱: {s['parsed_total']} | 완성도: {s['completeness_pct']}%")
    print(f"  테이블: {s['table_parsed']} | 텍스트: {s['text_parsed']} | 목록만: {s['list_only']}")
    print(f"  세부내용 완성도: {s['detail_completeness_pct']}%")
    if s.get('missing_detail_ids'):
        print(f"  누락: {', '.join(s['missing_detail_ids'][:15])}")

    out = sys.argv[1].replace('.pdf', '_requirements.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({k: v for k, v in result.items() if k != 'raw_text'},
                  f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out}")
