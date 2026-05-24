"""services_v2.agents.requirements.table_parser 단위 테스트.

LLM 미사용 — API 키 없이도 실행 가능.
"""

from __future__ import annotations

import pytest

from services_v2.agents.requirements.table_parser import (
    FIELD_ALIASES, _has_req_id, _map_headers, parse_tables,
)
from services_v2.documents.rfp_document import RfpDocument, TableRegion


def make_doc(*tables: TableRegion) -> RfpDocument:
    return RfpDocument(
        filename='unit.pdf',
        full_text='',
        pages=[],
        table_regions=list(tables),
    )


# ── _map_headers ────────────────────────────────────────────

class TestMapHeaders:
    def test_standard_headers(self):
        row = ['요구사항 고유번호', '요구사항 명칭', '요구사항 분류', '정의', '세부내용']
        result = _map_headers(row)
        assert result == {'id': 0, 'name': 1, 'category': 2, 'definition': 3, 'detail': 4}

    def test_alias_no_space(self):
        # 공백 없는 변형
        row = ['요구사항고유번호', '요구사항명칭', '요구사항분류']
        result = _map_headers(row)
        assert result == {'id': 0, 'name': 1, 'category': 2}

    def test_alias_short_form(self):
        # 짧은 변형
        row = ['고유번호', '항목명', '분류', '내용']
        result = _map_headers(row)
        assert result == {'id': 0, 'name': 1, 'category': 2, 'detail': 3}

    def test_alias_with_newline(self):
        # 셀 안 줄바꿈 ("세부\n내용")
        row = ['고유번호', '항목명', '세부\n내용']
        result = _map_headers(row)
        assert result == {'id': 0, 'name': 1, 'detail': 2}

    def test_empty_cells_ignored(self):
        row = ['', '고유번호', None, '항목명']
        result = _map_headers(row)
        assert result == {'id': 1, 'name': 3}

    def test_unknown_header_ignored(self):
        row = ['고유번호', '비고', '담당자']
        result = _map_headers(row)
        assert result == {'id': 0}

    def test_each_alias_in_dict_resolves(self):
        # 사전에 등록된 alias들이 모두 자기 표준 키로 매핑되는지
        for std_key, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                result = _map_headers([alias])
                assert result == {std_key: 0}, (
                    f'alias "{alias}" → expected {std_key}, got {result}'
                )


# ── _has_req_id ─────────────────────────────────────────────

class TestHasReqId:
    def test_three_digit_id(self):
        assert _has_req_id(['FR-001', '로그인', '기능'])

    def test_two_digit_id(self):
        assert _has_req_id(['SFR-01', '대시보드'])

    def test_no_id(self):
        assert not _has_req_id(['로그인 기능', '본인인증'])

    def test_empty_row(self):
        assert not _has_req_id([])
        assert not _has_req_id(['', '', None])


# ── parse_tables: 단일 표 ───────────────────────────────────

class TestSingleTable:
    def test_standard_horizontal_table(self):
        table = TableRegion(
            page_number=10,
            rows=[
                ['요구사항 고유번호', '요구사항 명칭', '요구사항 분류', '정의', '세부내용'],
                ['SFR-001', '사용자 인증', '기능', '로그인 기능', '아이디/비번 + 2FA'],
                ['SFR-002', '대시보드', '기능', '주요 지표 표시', '카드 6종, 차트 3종'],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 2

        r1 = reqs[0]
        assert r1.id == 'SFR-001'
        assert r1.name == '사용자 인증'
        assert r1.category == '기능'
        assert r1.definition == '로그인 기능'
        assert r1.detail == '아이디/비번 + 2FA'
        assert r1.category_code == 'SFR'
        assert r1.desc == '로그인 기능\n아이디/비번 + 2FA'  # definition + detail
        assert r1.parse_method == 'table'

    def test_two_digit_id_scheme(self):
        table = TableRegion(
            page_number=1,
            rows=[
                ['고유번호', '명칭', '내용'],
                ['FR-01', '메뉴', '상단 메뉴 노출'],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'FR-01'
        assert reqs[0].category_code == 'FR'
        assert reqs[0].detail == '상단 메뉴 노출'
        assert reqs[0].desc == '상단 메뉴 노출'  # definition 비어있을 때

    def test_header_in_second_row(self):
        # 첫 행이 표 제목/병합셀, 두 번째 행이 진짜 헤더
        table = TableRegion(
            page_number=1,
            rows=[
                ['기능 요구사항 목록', '', '', ''],
                ['요구사항번호', '요구사항명', '분류', '세부내용'],
                ['SFR-100', '결제', '기능', '카드결제 연동'],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'SFR-100'

    def test_rows_with_empty_cells_kept(self):
        # name만 있고 ID 없는 행도 유지
        table = TableRegion(
            page_number=1,
            rows=[
                ['고유번호', '명칭', '내용'],
                ['', '로그아웃', '세션 만료 처리'],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == ''
        assert reqs[0].name == '로그아웃'

    def test_blank_rows_skipped(self):
        table = TableRegion(
            page_number=1,
            rows=[
                ['고유번호', '명칭', '내용'],
                ['', '', ''],
                ['FR-001', '메뉴', '메뉴 노출'],
                [None, None, None],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'FR-001'

    def test_unrelated_table_ignored(self):
        # 헤더에 'id' alias 없고 ID 패턴도 없음 → 빈 결과
        table = TableRegion(
            page_number=1,
            rows=[
                ['일정', '담당', '비고'],
                ['2026-06', '홍길동', '계약'],
            ],
        )
        reqs = parse_tables(make_doc(table))
        assert reqs == []

    def test_single_row_table_ignored(self):
        # 헤더만 있고 데이터 없음
        table = TableRegion(page_number=1, rows=[['고유번호', '명칭']])
        assert parse_tables(make_doc(table)) == []

    def test_empty_table_ignored(self):
        assert parse_tables(make_doc(TableRegion(page_number=1, rows=[]))) == []


# ── parse_tables: 복수 표 ───────────────────────────────────

class TestMultipleTables:
    def test_merges_across_tables(self):
        t1 = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'], ['FR-001', '로그인'],
        ])
        t2 = TableRegion(page_number=5, rows=[
            ['고유번호', '명칭'], ['FR-002', '회원가입'],
        ])
        reqs = parse_tables(make_doc(t1, t2))
        assert [r.id for r in reqs] == ['FR-001', 'FR-002']

    def test_duplicate_id_kept_first_only(self):
        # 같은 ID가 두 표에 등장 — 첫 번째만 유지
        t1 = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'],
            ['FR-001', '로그인 (원본)'],
        ])
        t2 = TableRegion(page_number=5, rows=[
            ['고유번호', '명칭'],
            ['FR-001', '로그인 (별지)'],
        ])
        reqs = parse_tables(make_doc(t1, t2))
        assert len(reqs) == 1
        assert reqs[0].name == '로그인 (원본)'

    def test_empty_doc(self):
        assert parse_tables(make_doc()) == []


# ── category_code 추출 ─────────────────────────────────────

class TestCategoryCode:
    @pytest.mark.parametrize('req_id,code', [
        ('FR-001', 'FR'),
        ('SFR-01', 'SFR'),
        ('PER-100', 'PER'),
        ('SER-99', 'SER'),
        ('DAR-001', 'DAR'),
    ])
    def test_extract_from_id(self, req_id, code):
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'], [req_id, 'x'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs[0].category_code == code

    def test_no_code_when_no_pattern(self):
        # ID 컬럼은 있는데 값에 패턴이 없는 경우
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'], ['custom_id', 'x'],
        ])
        reqs = parse_tables(make_doc(table))
        # ID 값은 그대로, code는 비어있음
        assert reqs[0].id == 'custom_id'
        assert reqs[0].category_code == ''


# ── desc 합성 ──────────────────────────────────────────────

class TestDescSynthesis:
    def test_both_definition_and_detail(self):
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '정의', '세부내용'],
            ['FR-001', '로그인 처리', '아이디·비번 + 2FA + 캡차'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs[0].desc == '로그인 처리\n아이디·비번 + 2FA + 캡차'

    def test_only_definition(self):
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '정의'],
            ['FR-001', '로그인 처리'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs[0].desc == '로그인 처리'

    def test_only_detail(self):
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '세부내용'],
            ['FR-001', '아이디·비번'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs[0].desc == '아이디·비번'

    def test_neither(self):
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'],
            ['FR-001', '로그인'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs[0].desc == ''


# ── 세로형 표 (한 표 = 한 요구사항) ────────────────────────

class TestVerticalTable:
    """KIAT 양식: 첫 컬럼=필드명, 두 번째=값. 한 표가 한 요구사항을 표현."""

    def test_kiat_standard_8_fields(self):
        """KIAT 표준 8행 세로형: 분류/ID/명칭/정의/세부내용/산출정보/관련/출처."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 분류', '보안요구사항(SER)'],
            ['요구사항 고유번호', 'SER-001'],
            ['요구사항 명칭', '보안 일반사항'],
            ['정의', '본 사업 수행 시 준수해야 할 보안 일반 요구사항'],
            ['세부내용', '○ 보안서약서 제출 ○ 보안교육 이수'],
            ['산출 정보', '보안서약서, 교육이수증'],
            ['관련 요구사항', 'SER-002, SER-003'],
            ['요구사항 출처', '정보보안기본법'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        r = reqs[0]
        assert r.id == 'SER-001'
        assert r.name == '보안 일반사항'
        assert r.category == '보안요구사항(SER)'
        assert r.category_code == 'SER'
        assert r.definition.startswith('본 사업 수행')
        assert r.detail.startswith('○ 보안서약서')
        assert r.output_info == '보안서약서, 교육이수증'
        assert r.related_reqs == 'SER-002, SER-003'
        assert r.source == '정보보안기본법'
        assert r.parse_method == 'table'
        # desc는 definition + detail 합성
        assert '본 사업' in r.desc and '보안서약서' in r.desc

    def test_vertical_minimal_id_and_name(self):
        """id + name만 매칭되어도 인정 (최소 2필드)."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 고유번호', 'PMR-001'],
            ['요구사항 명칭', '사업수행조직'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'PMR-001'
        assert reqs[0].name == '사업수행조직'

    def test_vertical_only_one_field_rejected(self):
        """필드 1개만 매칭되면 요구사항 표 아님 — None."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 분류', '기능'],
            ['비고', '없음'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs == []

    def test_vertical_no_id_or_name_rejected(self):
        """id/name 둘 다 없으면 무효 (definition+detail만 있어도 안됨)."""
        table = TableRegion(page_number=1, rows=[
            ['정의', '로그인 처리'],
            ['세부내용', '아이디·비번'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs == []

    def test_vertical_name_only_accepted(self):
        """name만 있어도 OK (id 없음). ID 없는 요구사항을 인정."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 명칭', '시스템 가용성'],
            ['세부내용', '99.9% 이상'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == ''
        assert reqs[0].name == '시스템 가용성'

    def test_vertical_uses_only_second_column(self):
        """row[1]만 값으로 사용 (row[2:]는 다른 필드 페어일 수 있음)."""
        # 한국유학종합 양식: row=['필드명', '값', '필드명2', '값2']
        table = TableRegion(page_number=1, rows=[
            ['요구사항 명', '운영체계 수립', '응낙수준', '필수'],
            ['요구사항 내용', '24/365 안정 운영 체계'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        # name은 row[1]까지만. '응낙수준'/'필수'가 끼어들지 않음
        assert reqs[0].name == '운영체계 수립'
        assert reqs[0].detail == '24/365 안정 운영 체계'


# ── 단독 ID 헤더 (병합셀로 1셀 행) ──────────────────────────

class TestSingleCellIdHeader:
    """한국유학종합 양식: R0이 1셀(병합셀)이고 ID만 들어있는 형태."""

    def test_single_cell_id_extracted(self):
        table = TableRegion(page_number=1, rows=[
            ['COR-001'],
            ['요구사항 명', '운영 향상 방안 수립'],
            ['요구사항 내용', '경제성·효율성 향상 방안'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'COR-001'
        assert reqs[0].category_code == 'COR'
        assert reqs[0].name == '운영 향상 방안 수립'
        assert reqs[0].detail == '경제성·효율성 향상 방안'

    def test_single_cell_non_id_ignored(self):
        """단독 셀이지만 ID 패턴 아니면 무시 (제목 등)."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 목록'],
            ['요구사항 명칭', '인증'],
            ['세부내용', '2FA 적용'],
        ])
        reqs = parse_tables(make_doc(table))
        # ID 없이 name만 매칭 — 인정되지만 id는 비어있음
        assert len(reqs) == 1
        assert reqs[0].id == ''
        assert reqs[0].name == '인증'

    def test_takes_first_id_if_multiple(self):
        """단독 ID 셀이 여러 개여도 첫 번째만 사용."""
        table = TableRegion(page_number=1, rows=[
            ['SFR-001'],
            ['SFR-002'],  # 무시됨
            ['요구사항 명칭', '로그인'],
            ['세부내용', '...'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'SFR-001'


# ── 풍부도 기반 머지 ──────────────────────────────────────

class TestRichMerge:
    """같은 ID가 여러 표에 등장할 때 채워진 필드 많은 쪽 유지."""

    def test_richer_replaces_lean(self):
        # 표 1: 인덱스 표 (id만, 풍부도 낮음)
        thin = TableRegion(page_number=1, rows=[
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '로그인'],
        ])
        # 표 2: 본문 세로형 (8필드, 풍부도 높음)
        rich = TableRegion(page_number=5, rows=[
            ['요구사항 분류', '기능'],
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '로그인 (상세)'],
            ['정의', '사용자 인증 처리'],
            ['세부내용', 'ID/PW + 2FA + 캡차'],
            ['산출 정보', '인증 모듈'],
        ])
        reqs = parse_tables(make_doc(thin, rich))
        assert len(reqs) == 1
        # 풍부한 쪽 유지
        assert reqs[0].name == '로그인 (상세)'
        assert reqs[0].definition == '사용자 인증 처리'
        assert reqs[0].detail == 'ID/PW + 2FA + 캡차'
        assert reqs[0].output_info == '인증 모듈'

    def test_first_wins_when_equal_richness(self):
        t1 = TableRegion(page_number=1, rows=[
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '첫 번째'],
        ])
        t2 = TableRegion(page_number=2, rows=[
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '두 번째'],
        ])
        reqs = parse_tables(make_doc(t1, t2))
        # 풍부도 동률이면 기존(첫 번째) 유지
        assert reqs[0].name == '첫 번째'

    def test_order_preserved_by_first_appearance(self):
        # 풍부 결과가 뒤늦게 와서 교체되더라도 순서는 첫 등장 기준
        first_lean = TableRegion(page_number=1, rows=[
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '결제 (빈약)'],
        ])
        other = TableRegion(page_number=2, rows=[
            ['요구사항 고유번호', 'FR-002'],
            ['요구사항 명칭', '메뉴'],
        ])
        first_rich = TableRegion(page_number=5, rows=[
            ['요구사항 고유번호', 'FR-001'],
            ['요구사항 명칭', '결제 (상세)'],
            ['세부내용', '카드 결제 + 가상계좌'],
            ['정의', '결제 처리'],
        ])
        reqs = parse_tables(make_doc(first_lean, other, first_rich))
        assert [r.id for r in reqs] == ['FR-001', 'FR-002']
        # FR-001은 first_rich 내용으로
        assert reqs[0].name == '결제 (상세)'


# ── 컬럼 시프트 가드 ──────────────────────────────────────

class TestColumnShiftGuard:
    """병합셀로 데이터 행 컬럼이 밀려 들어간 행을 자동 제외."""

    def test_non_id_pattern_no_name_dropped(self):
        """id 컬럼에 비-ID + name 없음 → 깨진 행 제외."""
        # 가로형 표인데 R2가 병합셀 영향으로 컬럼 시프트
        table = TableRegion(page_number=1, rows=[
            ['ID', '명칭', '비고'],
            ['FR-001', '로그인', ''],
            ['엉뚱한 값', '', ''],  # ID 자리에 비-ID, name도 없음 → 제외
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'FR-001'

    def test_non_id_pattern_but_name_present_kept(self):
        """id가 비-ID여도 name이 있으면 정보 보존 (희귀하지만 비표준 RFP 대응)."""
        table = TableRegion(page_number=1, rows=[
            ['고유번호', '명칭'],
            ['custom_id', '커스텀 요구사항'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'custom_id'
        assert reqs[0].name == '커스텀 요구사항'
        assert reqs[0].category_code == ''  # ID 패턴 아니므로 코드 없음

    def test_valid_id_no_name_kept(self):
        """id가 정상 + name 없음 — 유지."""
        table = TableRegion(page_number=1, rows=[
            ['ID', '비고'],
            ['FR-001', '필수'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        assert reqs[0].id == 'FR-001'
        assert reqs[0].category_code == 'FR'


# ── Multi-pair 세로형 (전자인장 양식) ───────────────────────

class TestMultiPairVertical:
    """한 행에 (필드명, 값) 페어가 2개 펼쳐진 세로형."""

    def test_first_row_two_pairs(self):
        """R0: [필드1, 값1, 필드2, 값2] + R1+: [필드, 값]"""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 No.', 'SFR-001', '요구사항 분류', '기능 요구사항'],
            ['요구사항명', '날인 대상 문서 출력 시 책임자 승인'],
            ['요구사항 상세설명', '❍ 적용대상 - 수신, 우리사주'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        r = reqs[0]
        assert r.id == 'SFR-001'
        assert r.category == '기능 요구사항'
        assert r.name == '날인 대상 문서 출력 시 책임자 승인'
        assert r.detail.startswith('❍ 적용대상')
        assert r.category_code == 'SFR'

    def test_multipair_does_not_break_horizontal_header(self):
        """가로형 헤더 [요구사항 고유번호, 요구사항 명칭, ...]은 세로형으로 잘못 인식 안 됨."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 고유번호', '요구사항 명칭', '요구사항 분류', '정의', '세부내용'],
            ['SFR-001', '사용자 인증', '기능', '로그인 기능', '아이디/비번 + 2FA'],
            ['SFR-002', '대시보드', '기능', '주요 지표', '카드 6종'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 2
        assert reqs[0].id == 'SFR-001'
        assert reqs[0].name == '사용자 인증'  # 값이 옆 페어로 흡수되지 않음
        assert reqs[1].id == 'SFR-002'


# ── ID-free 가로형 (아이부자 양식) ────────────────────────

class TestIdFreeHorizontal:
    """ID 컬럼 없는 양식 — category + detail 페어로 인정."""

    def test_category_and_detail_only(self):
        table = TableRegion(page_number=1, rows=[
            ['구분', '요건 상세'],
            ['As-is 기능 구축', '- 아이부자 기존 기능을 퍼블릭 클라우드 內 구축'],
            ['UIUX 전면 개편', '1) 브랜드 컨셉 및 디자인 개선'],
            ['시스템 안정성', '99.9% 가용성 보장'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 3
        assert reqs[0].id == ''  # ID 없음
        assert reqs[0].category == 'As-is 기능 구축'
        assert reqs[0].detail.startswith('- 아이부자')
        assert reqs[0].category_code == ''  # ID 패턴 없음

    def test_irrelevant_table_still_rejected(self):
        """ID-free 허용 후에도 헤더에 detail alias 없는 표는 거부."""
        # [번호, 시스템명, URL] — 일반 데이터 표
        table = TableRegion(page_number=1, rows=[
            ['번호', '시스템명', 'URL'],
            ['1', '메일', 'mail.com'],
            ['2', 'SMS', 'sms.com'],
        ])
        reqs = parse_tables(make_doc(table))
        assert reqs == []

    def test_name_and_detail_also_works(self):
        """category 대신 name + detail 조합도 인정."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항명', '세부내용'],
            ['로그인', 'OAuth + 2FA'],
            ['대시보드', '주요 KPI 표시'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 2
        assert reqs[0].name == '로그인'
        assert reqs[0].detail == 'OAuth + 2FA'


# ── ISP 양식 (3열 sub-field) ─────────────────────────────

class TestIspSubFieldVertical:
    """ISP수립/ISP-BPR 양식: [메인필드, 서브필드, 값] 3열 행."""

    def test_definition_subfield_extracted(self):
        """R3: ['요구사항 내용', '정의', '실제 값'] → definition='실제 값'"""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 분류', '컨설팅 요구사항'],
            ['요구사항 고유번호', 'CNR-001'],
            ['요구사항명', '내·외부 환경 분석'],
            ['요구사항 내용', '정의', '국유재산 관리 체계 내·외부 환경 분석'],
            ['세부\n내용', '○ 시스템 관련 내부 및 외부 환경 분석'],
            ['산출정보', '내·외부 환경 분석 보고서'],
        ])
        reqs = parse_tables(make_doc(table))
        assert len(reqs) == 1
        r = reqs[0]
        assert r.id == 'CNR-001'
        assert r.name == '내·외부 환경 분석'
        assert r.category == '컨설팅 요구사항'
        # 핵심: definition은 sub-field 값으로, '정의' 단어가 아님
        assert r.definition == '국유재산 관리 체계 내·외부 환경 분석'
        # detail은 별도 행에서
        assert r.detail.startswith('○ 시스템')
        assert r.output_info == '내·외부 환경 분석 보고서'

    def test_subfield_value_not_main_field_label(self):
        """서브필드 값이 메인필드 label('정의')로 들어가지 않아야 함."""
        table = TableRegion(page_number=1, rows=[
            ['요구사항 분류', '품질 요구사항'],
            ['요구사항 고유번호', 'QUR-001'],
            ['요구사항명', '품질 보증'],
            ['요구사항 내용', '정의', '품질 관리 및 보증 방안 수립'],
            ['세부내용', '○ 산출물 품질 검토 절차'],
        ])
        reqs = parse_tables(make_doc(table))
        # detail에 '정의' 한 글자만 들어가는 회귀 방지
        assert reqs[0].detail != '정의'
        assert '○' in reqs[0].detail
        assert reqs[0].definition == '품질 관리 및 보증 방안 수립'
