"""
TOC (Table of Contents) Manager
표준 목차 템플릿 CRUD 및 세션 TOC 관리를 담당합니다.

핵심 기능:
- 3개 내장 TOC 템플릿 (SI/SM 사업, 컨설팅 사업, 유지보수 사업)
- 커스텀 TOC 템플릿 생성/삭제
- 세션 TOC 상태 관리 (조회/수정/항목 추가·삭제·이동/확정)
- 표준 템플릿 적용 (기존 TOC에 병합)
"""

import copy
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_STORAGE_DIR = os.path.join(BASE_DIR, 'templates_storage')
TOC_TEMPLATES_FILE = os.path.join(TEMPLATES_STORAGE_DIR, 'toc_templates.json')


class TocManagerError(Exception):
    """TOC 관리 중 발생하는 에러"""


# ── Built-in TOC Templates ────────────────────────────────

def _make_item(level, number, title, description='', children=None):
    return {
        'level': level,
        'number': number,
        'title': title,
        'description': description,
        'children': children or [],
    }


BUILTIN_TOC_TEMPLATES = [
    {
        'id': 'builtin-si-sm',
        'name': 'SI/SM 사업',
        'builtin': True,
        'items': [
            _make_item(1, 'I', '사업 이해', '발주 배경·목적·범위 분석', [
                _make_item(2, '1', '사업 개요', 'RFP 요구사항 및 사업 범위 분석'),
                _make_item(2, '2', '추진 배경 및 목적', '발주기관의 현안 및 기대 효과'),
                _make_item(2, '3', '사업 범위 및 대상', '과업 범위·시스템 대상 정리'),
            ]),
            _make_item(1, 'II', '현황 분석', '현행 시스템 및 환경 진단', [
                _make_item(2, '1', '현행 시스템 분석', '기존 인프라·시스템 현황 파악'),
                _make_item(2, '2', '문제점 및 개선 방향', '현행 문제점 도출 및 개선 전략'),
            ]),
            _make_item(1, 'III', '기술 제안', '핵심 기술 및 아키텍처 제안', [
                _make_item(2, '1', '시스템 아키텍처', '전체 시스템 구성 및 설계 방안'),
                _make_item(2, '2', '핵심 기술 방안', '주요 기술 요소별 구현 전략'),
                _make_item(2, '3', '기능 구현 방안', '기능 요구사항별 구현 계획'),
                _make_item(2, '4', '인터페이스 설계', '시스템 간 연계·통합 방안'),
            ]),
            _make_item(1, 'IV', '수행 방안', '프로젝트 수행 전략 및 일정', [
                _make_item(2, '1', '추진 전략 및 방법론', '개발 방법론 및 추진 체계'),
                _make_item(2, '2', '단계별 수행 계획', '단계별 작업 내용 및 일정'),
                _make_item(2, '3', '투입 인력 계획', '인력 구성 및 역할 배분'),
            ]),
            _make_item(1, 'V', '프로젝트 관리', '품질·일정·위험 관리 체계', [
                _make_item(2, '1', '품질 관리 방안', '품질 보증 체계 및 검증 전략'),
                _make_item(2, '2', '일정 관리 방안', '마일스톤 관리 및 진도 관리'),
                _make_item(2, '3', '위험 관리 방안', '리스크 식별 및 대응 전략'),
            ]),
            _make_item(1, 'VI', '보안 및 품질 관리', '정보보안 및 데이터 보호 방안', [
                _make_item(2, '1', '보안 관리 방안', '정보보안 정책 및 기술적 보호'),
                _make_item(2, '2', '개인정보 보호', '개인정보 처리·보호 방안'),
            ]),
        ],
    },
    {
        'id': 'builtin-consulting',
        'name': '컨설팅 사업',
        'builtin': True,
        'items': [
            _make_item(1, 'I', '사업 이해', '컨설팅 배경 및 목적 파악', [
                _make_item(2, '1', '사업 개요', '발주 배경 및 컨설팅 범위'),
                _make_item(2, '2', '추진 목적 및 기대효과', '컨설팅 목표 및 성과 지표'),
            ]),
            _make_item(1, 'II', '환경 분석', '대내외 환경 및 현황 진단', [
                _make_item(2, '1', '대내 환경 분석', '조직·시스템·프로세스 현황'),
                _make_item(2, '2', '대외 환경 분석', '시장·기술·정책 동향'),
                _make_item(2, '3', '벤치마킹', '우수 사례 분석 및 시사점'),
            ]),
            _make_item(1, 'III', '컨설팅 방법론', '분석 프레임워크 및 접근 전략', [
                _make_item(2, '1', '분석 프레임워크', '컨설팅 분석 체계 및 도구'),
                _make_item(2, '2', '접근 방법', '단계별 컨설팅 접근 전략'),
            ]),
            _make_item(1, 'IV', '수행 전략', '세부 수행 계획 및 산출물', [
                _make_item(2, '1', '단계별 수행 계획', '각 단계 세부 과업 및 일정'),
                _make_item(2, '2', '산출물 계획', '주요 산출물 목록 및 품질 기준'),
                _make_item(2, '3', '투입 인력 계획', '전문 인력 구성 및 역할'),
            ]),
            _make_item(1, 'V', '기대 효과', '정성적·정량적 기대 성과', [
                _make_item(2, '1', '정성적 기대효과', '조직·프로세스 개선 효과'),
                _make_item(2, '2', '정량적 기대효과', '비용·시간·효율 개선 수치'),
            ]),
            _make_item(1, 'VI', '관리 방안', '프로젝트 및 변화 관리', [
                _make_item(2, '1', '프로젝트 관리', '일정·품질·위험 관리 체계'),
                _make_item(2, '2', '변화 관리', '조직 변화 관리 및 교육 계획'),
            ]),
        ],
    },
    {
        'id': 'builtin-maintenance',
        'name': '유지보수 사업',
        'builtin': True,
        'items': [
            _make_item(1, 'I', '사업 이해', '유지보수 배경 및 대상 시스템 파악', [
                _make_item(2, '1', '사업 개요', '유지보수 범위 및 대상 시스템'),
                _make_item(2, '2', '추진 배경 및 목적', '안정적 운영을 위한 목표'),
            ]),
            _make_item(1, 'II', '유지보수 전략', '핵심 전략 및 서비스 모델', [
                _make_item(2, '1', '유지보수 전략', '예방·교정·개선 유지보수 방안'),
                _make_item(2, '2', '서비스 모델', '서비스 데스크 및 지원 체계'),
            ]),
            _make_item(1, 'III', '운영 방안', '일상 운영 및 장애 대응', [
                _make_item(2, '1', '시스템 운영 방안', '일상 점검·모니터링 체계'),
                _make_item(2, '2', '장애 대응 방안', '장애 등급별 대응 프로세스'),
                _make_item(2, '3', '변경 관리', '변경 요청 처리 프로세스'),
            ]),
            _make_item(1, 'IV', 'SLA 관리', '서비스 수준 목표 및 측정', [
                _make_item(2, '1', 'SLA 목표 설정', '가용성·응답시간·처리율 목표'),
                _make_item(2, '2', 'SLA 측정 및 보고', '정기 보고 및 개선 활동'),
            ]),
            _make_item(1, 'V', '인력 및 조직', '투입 인력 및 조직 운영', [
                _make_item(2, '1', '투입 인력 계획', '인력 구성 및 역할'),
                _make_item(2, '2', '교육 및 인수인계', '기술 이전 및 역량 강화'),
            ]),
            _make_item(1, 'VI', '보안 관리', '정보보안 및 접근 관리', [
                _make_item(2, '1', '보안 관리 방안', '접근 통제·로그 관리 체계'),
                _make_item(2, '2', '재해 복구', '백업·복구 전략 및 BCP'),
            ]),
        ],
    },
]


# ── Persistence Helpers ───────────────────────────────────

def _ensure_storage_dir():
    os.makedirs(TEMPLATES_STORAGE_DIR, exist_ok=True)


def _load_custom_templates() -> list[dict]:
    if not os.path.exists(TOC_TEMPLATES_FILE):
        return []
    try:
        with open(TOC_TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('TOC 템플릿 파일 로드 실패: %s', exc)
        return []


def _save_custom_templates(templates: list[dict]):
    _ensure_storage_dir()
    with open(TOC_TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


# ── TOC Template CRUD ─────────────────────────────────────

def list_toc_templates() -> list[dict]:
    """모든 TOC 템플릿 목록을 반환합니다 (내장 + 커스텀)."""
    builtins = copy.deepcopy(BUILTIN_TOC_TEMPLATES)
    customs = _load_custom_templates()
    return builtins + customs


def get_toc_template(template_id: str) -> dict | None:
    """ID로 TOC 템플릿을 조회합니다."""
    for t in BUILTIN_TOC_TEMPLATES:
        if t['id'] == template_id:
            return copy.deepcopy(t)
    for t in _load_custom_templates():
        if t['id'] == template_id:
            return t
    return None


def create_toc_template(data: dict) -> dict:
    """커스텀 TOC 템플릿을 생성합니다."""
    name = (data.get('name') or '').strip()
    if not name:
        raise TocManagerError('템플릿 이름을 입력해주세요.')

    items = data.get('items', [])
    if not isinstance(items, list) or not items:
        raise TocManagerError('목차 항목이 필요합니다.')

    validated_items = _validate_toc_items(items)

    template = {
        'id': 'toc-' + uuid.uuid4().hex[:8],
        'name': name,
        'builtin': False,
        'items': validated_items,
    }

    customs = _load_custom_templates()
    customs.append(template)
    _save_custom_templates(customs)
    return template


def update_toc_template(template_id: str, data: dict) -> dict | None:
    """커스텀 TOC 템플릿을 수정합니다."""
    for t in BUILTIN_TOC_TEMPLATES:
        if t['id'] == template_id:
            raise TocManagerError('내장 템플릿은 수정할 수 없습니다.')

    name = (data.get('name') or '').strip()
    if not name:
        raise TocManagerError('템플릿 이름을 입력해주세요.')

    items = data.get('items', [])
    if not isinstance(items, list) or not items:
        raise TocManagerError('목차 항목이 필요합니다.')

    validated_items = _validate_toc_items(items)

    customs = _load_custom_templates()
    for t in customs:
        if t['id'] == template_id:
            t['name'] = name
            t['items'] = validated_items
            _save_custom_templates(customs)
            return t
    return None


def delete_toc_template(template_id: str) -> bool:
    """커스텀 TOC 템플릿을 삭제합니다."""
    for t in BUILTIN_TOC_TEMPLATES:
        if t['id'] == template_id:
            raise TocManagerError('내장 템플릿은 삭제할 수 없습니다.')

    customs = _load_custom_templates()
    new_list = [t for t in customs if t['id'] != template_id]
    if len(new_list) == len(customs):
        return False
    _save_custom_templates(new_list)
    return True


# ── TOC Item Validation ───────────────────────────────────

def _validate_toc_items(items: list, max_level: int = 3) -> list[dict]:
    """TOC 항목 리스트를 검증하고 정규화합니다."""
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title', '')).strip()
        if not title:
            continue
        level = item.get('level', 1)
        try:
            level = int(level)
        except (ValueError, TypeError):
            level = 1
        level = max(1, min(level, max_level))

        children = item.get('children', [])
        validated_children = []
        if isinstance(children, list) and children:
            validated_children = _validate_toc_items(children, max_level)

        result.append({
            'level': level,
            'number': str(item.get('number', '')),
            'title': title,
            'description': str(item.get('description', '')),
            'children': validated_children,
        })
    return result


# ── Session TOC State ─────────────────────────────────────
# 단일 사용자 세션 기준 — 현재 편집 중인 TOC

_current_toc: list[dict] | None = None
_toc_finalized: bool = False


def get_current_toc() -> dict:
    """현재 세션 TOC 상태를 반환합니다."""
    return {
        'items': _current_toc or [],
        'finalized': _toc_finalized,
    }


def set_current_toc(items: list[dict]):
    """세션 TOC를 설정합니다 (AI 분석 결과 또는 에디터 전체 업데이트)."""
    global _current_toc, _toc_finalized
    _current_toc = _validate_toc_items(items)
    _toc_finalized = False


def apply_toc_template(template_id: str) -> dict:
    """표준 템플릿을 현재 TOC에 적용합니다 (대체)."""
    global _current_toc, _toc_finalized
    template = get_toc_template(template_id)
    if template is None:
        raise TocManagerError('템플릿을 찾을 수 없습니다.')
    _current_toc = copy.deepcopy(template['items'])
    _toc_finalized = False
    return get_current_toc()


def finalize_toc() -> dict:
    """현재 TOC를 확정합니다 (콘텐츠 생성 단계로 진행 가능)."""
    global _toc_finalized
    if not _current_toc:
        raise TocManagerError('확정할 목차가 없습니다.')
    _toc_finalized = True
    return get_current_toc()


def unfinalize_toc() -> dict:
    """확정된 TOC를 다시 편집 가능 상태로 되돌립니다."""
    global _toc_finalized
    _toc_finalized = False
    return get_current_toc()


def _navigate_to_parent(path: list[int]) -> tuple[list[dict], int]:
    """path를 따라 부모 리스트와 마지막 인덱스를 반환합니다."""
    if not _current_toc:
        raise TocManagerError('현재 TOC가 없습니다.')
    items = _current_toc
    for idx in path[:-1]:
        if idx < 0 or idx >= len(items):
            raise TocManagerError('잘못된 경로입니다.')
        items = items[idx].get('children', [])
    last_idx = path[-1]
    return items, last_idx


def update_toc_item(path: list[int], data: dict) -> dict:
    """특정 경로의 TOC 항목을 수정합니다."""
    global _toc_finalized
    items, idx = _navigate_to_parent(path)
    if idx < 0 or idx >= len(items):
        raise TocManagerError('항목을 찾을 수 없습니다.')
    item = items[idx]
    if 'title' in data:
        item['title'] = str(data['title']).strip()
    if 'number' in data:
        item['number'] = str(data['number'])
    if 'description' in data:
        item['description'] = str(data['description'])
    if 'level' in data:
        try:
            item['level'] = max(1, min(int(data['level']), 3))
        except (ValueError, TypeError):
            pass
    _toc_finalized = False
    return get_current_toc()


def add_toc_item(parent_path: list[int] | None, item_data: dict) -> dict:
    """TOC 항목을 추가합니다. parent_path=None이면 최상위에 추가."""
    global _current_toc, _toc_finalized
    if _current_toc is None:
        _current_toc = []

    title = str(item_data.get('title', '')).strip()
    if not title:
        raise TocManagerError('항목 제목을 입력해주세요.')

    new_item = {
        'level': int(item_data.get('level', 1)),
        'number': str(item_data.get('number', '')),
        'title': title,
        'description': str(item_data.get('description', '')),
        'children': [],
    }

    if parent_path is None or len(parent_path) == 0:
        _current_toc.append(new_item)
    else:
        items = _current_toc
        for idx in parent_path:
            if idx < 0 or idx >= len(items):
                raise TocManagerError('잘못된 경로입니다.')
            parent = items[idx]
            if 'children' not in parent:
                parent['children'] = []
            items = parent['children']
        items.append(new_item)

    _toc_finalized = False
    return get_current_toc()


def remove_toc_item(path: list[int]) -> dict:
    """특정 경로의 TOC 항목을 삭제합니다."""
    global _toc_finalized
    if not path:
        raise TocManagerError('삭제할 항목의 경로가 필요합니다.')
    items, idx = _navigate_to_parent(path)
    if idx < 0 or idx >= len(items):
        raise TocManagerError('항목을 찾을 수 없습니다.')
    items.pop(idx)
    _toc_finalized = False
    return get_current_toc()


def move_toc_item(from_path: list[int], to_path: list[int]) -> dict:
    """TOC 항목을 이동합니다 (from에서 제거 후 to에 삽입)."""
    global _toc_finalized
    if not from_path or not to_path:
        raise TocManagerError('이동 경로가 필요합니다.')

    # 원본 항목 추출
    from_items, from_idx = _navigate_to_parent(from_path)
    if from_idx < 0 or from_idx >= len(from_items):
        raise TocManagerError('이동할 항목을 찾을 수 없습니다.')
    item = from_items.pop(from_idx)

    # 대상 위치에 삽입
    to_items, to_idx = _navigate_to_parent(to_path)
    to_idx = max(0, min(to_idx, len(to_items)))
    to_items.insert(to_idx, item)

    _toc_finalized = False
    return get_current_toc()
