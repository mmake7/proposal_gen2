"""
테스트 공용 픽스처 및 헬퍼

pytest가 자동으로 로드하는 conftest.py에서 공용 픽스처를 정의합니다.
- Flask 테스트 클라이언트
- 샘플 PDF 생성 유틸리티
- 분석 결과 샘플 데이터
"""

import io
import json

import fitz  # PyMuPDF
import pytest

import app as app_module
from app import create_app


# ── Flask 테스트 클라이언트 ─────────────────────────────────

@pytest.fixture
def flask_app():
    """테스트용 Flask 앱 인스턴스"""
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(flask_app):
    """Flask 테스트 클라이언트"""
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_analysis_cache():
    """각 테스트 전후로 분석 결과/세션 전역 캐시 초기화 (테스트 격리)"""
    def _reset():
        app_module._last_analysis = None
        app_module._rfp_full_text = None
        app_module._last_v2_result = None
        app_module._last_v2_filename = ''
    _reset()
    yield
    _reset()


# ── 샘플 PDF 생성 헬퍼 ─────────────────────────────────────

def create_text_pdf(pages_text: list[str]) -> bytes:
    """텍스트가 포함된 PDF를 메모리에서 생성합니다.

    Args:
        pages_text: 각 페이지에 넣을 텍스트 리스트

    Returns:
        PDF 바이트 데이터
    """
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        tw = fitz.TextWriter(page.rect)
        tw.append((72, 72), text, fontsize=12)
        tw.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


def create_rfp_like_pdf() -> bytes:
    """RFP 형태의 텍스트를 포함한 샘플 PDF를 생성합니다.

    실제 RFP 문서와 유사한 구조의 텍스트를 포함하여
    PDF 추출 → AI 분석 통합 테스트에 사용합니다.
    """
    rfp_page1 = (
        "제안요청서 (RFP) - 스마트시티 통합플랫폼 구축 사업 "
        "1. 사업 개요 "
        "가. 사업명: 스마트시티 통합플랫폼 구축 "
        "나. 발주기관: 한국정보화진흥원 "
        "다. 사업기간: 2026.04 ~ 2026.12 (9개월) "
        "라. 사업예산: 500백만원 "
        "마. 계약방식: 제한경쟁입찰 / 총액계약 "
        "바. 참가자격: 중소기업, 소프트웨어사업자 신고업체 "
        "사. 수행장소: 서울특별시 "
        "아. 사업목적: IoT 센서 데이터를 통합 관리하는 스마트시티 플랫폼을 구축하여 "
        "도시 인프라의 효율적 운영 및 시민 편의를 증진한다. "
    )
    rfp_page2 = (
        "2. 요구사항 "
        "2.1 기능 요구사항 "
        "FR-001 데이터 수집: IoT 센서로부터 실시간 데이터 수집 기능 (필수) "
        "FR-002 대시보드: 수집된 데이터를 시각화하는 대시보드 제공 (필수) "
        "FR-003 알림 서비스: 이상 감지 시 알림 발송 기능 (선택) "
        "2.2 비기능 요구사항 "
        "NFR-001 가용성: 시스템 가용성 99.9 percent 이상 보장 (필수) "
        "NFR-002 보안: 개인정보 암호화 및 접근통제 (필수) "
    )
    rfp_page3 = (
        "3. 평가 기준 (배점표) "
        "기술 부문 - 시스템 아키텍처: 확장성 및 안정성 설계 (20점) "
        "기술 부문 - 데이터 처리: 실시간 처리 성능 (15점) "
        "기술 부문 - 보안 설계: 보안 아키텍처 및 대응방안 (15점) "
        "관리 부문 - 사업 관리: 프로젝트 관리 방안 (20점) "
        "가격 부문 - 가격 평가: 적정 가격 제시 (30점) "
        "4. 제안서 목차 "
        "I. 사업 이해 "
        "  1. 사업 배경 및 목적 "
        "  2. 현황 분석 "
        "II. 기술 제안 "
        "  1. 시스템 아키텍처 "
        "  2. 데이터 처리 방안 "
        "III. 수행 계획 "
        "  1. 추진 체계 "
        "  2. 일정 계획 "
    )
    return create_text_pdf([rfp_page1, rfp_page2, rfp_page3])


def create_empty_pdf(page_count: int = 1) -> bytes:
    """텍스트가 없는 빈 PDF를 생성합니다."""
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


# ── 샘플 분석 결과 데이터 ──────────────────────────────────

SAMPLE_ANALYSIS_RESULT = {
    'overview': {
        'project_name': '스마트시티 통합플랫폼 구축',
        'organization': '한국정보화진흥원',
        'period': '2026.04 ~ 2026.12',
        'budget': '500',
        'budget_unit': '백만원',
        'contract_type': '제한경쟁입찰',
        'contract_method': '총액계약',
        'qualifications': '중소기업',
        'location': '서울특별시',
        'purpose': '스마트시티 데이터 통합 관리',
    },
    'requirements': [
        {'category': '기능', 'id': 'FR-001', 'name': '데이터 수집', 'desc': 'IoT 센서 데이터 수집', 'level': '필수'},
        {'category': '기능', 'id': 'FR-002', 'name': '대시보드', 'desc': '데이터 시각화', 'level': '필수'},
        {'category': '비기능', 'id': 'NFR-001', 'name': '가용성', 'desc': '99.9% 가용성', 'level': '필수'},
    ],
    'scoring': [
        {'category': '기술', 'item': '아키텍처', 'criteria': '확장성 설계', 'score': 20},
        {'category': '기술', 'item': '데이터 처리', 'criteria': '실시간 성능', 'score': 15},
        {'category': '관리', 'item': '사업 관리', 'criteria': '관리 방안', 'score': 20},
        {'category': '가격', 'item': '가격 평가', 'criteria': '적정 가격', 'score': 30},
    ],
    'toc': [
        {'level': 1, 'title': '사업 이해', 'children': [
            {'level': 2, 'title': '사업 배경', 'children': []},
            {'level': 2, 'title': '현황 분석', 'children': []},
        ]},
        {'level': 1, 'title': '기술 제안', 'children': [
            {'level': 2, 'title': '시스템 아키텍처', 'children': []},
        ]},
        {'level': 1, 'title': '수행 계획', 'children': []},
    ],
}

SAMPLE_ANALYSIS_JSON = json.dumps(SAMPLE_ANALYSIS_RESULT, ensure_ascii=False)
