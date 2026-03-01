"""
Font Preset Manager
폰트 프리셋 CRUD 및 적용 모드 설정을 관리합니다.

핵심 기능:
- 3개 내장 프리셋 (공공기관 표준, 나눔스퀘어, 나눔고딕)
- 커스텀 프리셋 생성/수정/삭제
- 폰트 적용 모드 설정 (template_keep, preset_apply, preset_force)
"""

import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

# 저장 경로 (template_manager.py와 동일 디렉터리 사용)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_STORAGE_DIR = os.path.join(BASE_DIR, 'templates_storage')
PRESETS_FILE = os.path.join(TEMPLATES_STORAGE_DIR, 'font_presets.json')
SETTINGS_FILE = os.path.join(TEMPLATES_STORAGE_DIR, 'font_settings.json')

VALID_MODES = ('template_keep', 'preset_apply', 'preset_force')


class FontManagerError(Exception):
    """폰트 관리 중 발생하는 에러"""


# ── Built-in Presets ────────────────────────────────────────

BUILTIN_PRESETS = [
    {
        'id': 'builtin-gov-standard',
        'name': '공공기관 표준',
        'builtin': True,
        'title_font': {
            'name': '맑은 고딕',
            'size_pt': 28.0,
            'bold': True,
            'color': '#1E293B',
        },
        'body_font': {
            'name': '맑은 고딕',
            'size_pt': 11.0,
            'bold': False,
            'color': '#334155',
        },
        'emphasis_font': {
            'name': '맑은 고딕',
            'size_pt': 13.0,
            'bold': True,
            'color': '#4F46E5',
        },
    },
    {
        'id': 'builtin-nanum-square',
        'name': '나눔스퀘어',
        'builtin': True,
        'title_font': {
            'name': '나눔스퀘어 ExtraBold',
            'size_pt': 28.0,
            'bold': True,
            'color': '#0F172A',
        },
        'body_font': {
            'name': '나눔스퀘어',
            'size_pt': 11.0,
            'bold': False,
            'color': '#334155',
        },
        'emphasis_font': {
            'name': '나눔스퀘어 Bold',
            'size_pt': 13.0,
            'bold': True,
            'color': '#6366F1',
        },
    },
    {
        'id': 'builtin-nanum-gothic',
        'name': '나눔고딕',
        'builtin': True,
        'title_font': {
            'name': '나눔고딕 ExtraBold',
            'size_pt': 28.0,
            'bold': True,
            'color': '#0F172A',
        },
        'body_font': {
            'name': '나눔고딕',
            'size_pt': 11.0,
            'bold': False,
            'color': '#334155',
        },
        'emphasis_font': {
            'name': '나눔고딕 Bold',
            'size_pt': 13.0,
            'bold': True,
            'color': '#4F46E5',
        },
    },
]


# ── Storage Helpers ─────────────────────────────────────────

def _ensure_storage_dir():
    os.makedirs(TEMPLATES_STORAGE_DIR, exist_ok=True)


def _load_presets() -> list[dict]:
    """JSON에서 프리셋 목록을 로드합니다. 내장 프리셋이 없으면 자동 복원."""
    _ensure_storage_dir()
    if not os.path.exists(PRESETS_FILE):
        _save_presets(list(BUILTIN_PRESETS))
        return list(BUILTIN_PRESETS)

    with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    presets = data.get('presets', [])

    # 내장 프리셋 누락 시 자동 복원
    existing_ids = {p['id'] for p in presets}
    restored = False
    for bp in BUILTIN_PRESETS:
        if bp['id'] not in existing_ids:
            presets.insert(0, dict(bp))
            restored = True
    if restored:
        _save_presets(presets)

    return presets


def _save_presets(presets: list[dict]):
    _ensure_storage_dir()
    with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'presets': presets}, f, ensure_ascii=False, indent=2)


def _load_settings() -> dict:
    _ensure_storage_dir()
    if not os.path.exists(SETTINGS_FILE):
        return {'mode': 'template_keep', 'active_preset_id': None}
    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_settings(settings: dict):
    _ensure_storage_dir()
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ── Validation ──────────────────────────────────────────────

def _validate_font_entry(entry: dict, label: str = '') -> dict:
    """폰트 항목(title_font, body_font, emphasis_font)을 검증합니다."""
    if not isinstance(entry, dict):
        raise FontManagerError(f'{label} 폰트 항목은 객체여야 합니다.')

    name = (entry.get('name') or '').strip()
    if not name:
        raise FontManagerError(f'{label} 폰트 이름은 필수입니다.')

    size_pt = entry.get('size_pt', 11.0)
    try:
        size_pt = float(size_pt)
    except (TypeError, ValueError):
        raise FontManagerError(f'{label} 폰트 크기는 숫자여야 합니다.')
    if size_pt <= 0 or size_pt > 200:
        raise FontManagerError(f'{label} 폰트 크기는 0~200 사이여야 합니다.')

    color = (entry.get('color') or '#334155').strip()

    return {
        'name': name,
        'size_pt': round(size_pt, 1),
        'bold': bool(entry.get('bold', False)),
        'color': color,
    }


def _validate_preset_data(data: dict) -> dict:
    """프리셋 전체 데이터를 검증합니다."""
    name = (data.get('name') or '').strip()
    if not name:
        raise FontManagerError('프리셋 이름은 필수입니다.')
    if len(name) > 50:
        raise FontManagerError('프리셋 이름은 50자 이내여야 합니다.')

    return {
        'name': name,
        'title_font': _validate_font_entry(data.get('title_font', {}), '제목'),
        'body_font': _validate_font_entry(data.get('body_font', {}), '본문'),
        'emphasis_font': _validate_font_entry(data.get('emphasis_font', {}), '강조'),
    }


# ── CRUD: Presets ───────────────────────────────────────────

def list_presets() -> list[dict]:
    """모든 프리셋(내장 + 커스텀)을 반환합니다."""
    return _load_presets()


def get_preset(preset_id: str) -> dict | None:
    """특정 프리셋을 반환합니다."""
    for p in _load_presets():
        if p['id'] == preset_id:
            return p
    return None


def create_preset(data: dict) -> dict:
    """커스텀 프리셋을 생성합니다."""
    validated = _validate_preset_data(data)
    preset = {
        'id': str(uuid.uuid4())[:8],
        'builtin': False,
        **validated,
    }
    presets = _load_presets()
    presets.append(preset)
    _save_presets(presets)
    logger.info('폰트 프리셋 생성: %s (%s)', preset['name'], preset['id'])
    return preset


def update_preset(preset_id: str, data: dict) -> dict | None:
    """커스텀 프리셋을 수정합니다. 내장 프리셋은 수정 불가."""
    presets = _load_presets()
    for i, p in enumerate(presets):
        if p['id'] == preset_id:
            if p.get('builtin'):
                raise FontManagerError('내장 프리셋은 수정할 수 없습니다.')
            validated = _validate_preset_data(data)
            presets[i] = {**p, **validated}
            _save_presets(presets)
            logger.info('폰트 프리셋 수정: %s', preset_id)
            return presets[i]
    return None


def delete_preset(preset_id: str) -> bool:
    """커스텀 프리셋을 삭제합니다. 내장 프리셋은 삭제 불가."""
    presets = _load_presets()
    for p in presets:
        if p['id'] == preset_id:
            if p.get('builtin'):
                raise FontManagerError('내장 프리셋은 삭제할 수 없습니다.')
            break

    new_presets = [p for p in presets if p['id'] != preset_id]
    if len(new_presets) == len(presets):
        return False

    _save_presets(new_presets)

    # 활성 프리셋이 삭제된 프리셋이면 초기화
    settings = _load_settings()
    if settings.get('active_preset_id') == preset_id:
        settings['active_preset_id'] = None
        _save_settings(settings)

    logger.info('폰트 프리셋 삭제: %s', preset_id)
    return True


# ── Settings ────────────────────────────────────────────────

def get_font_settings() -> dict:
    """현재 폰트 적용 설정을 반환합니다."""
    return _load_settings()


def update_font_settings(data: dict) -> dict:
    """폰트 적용 설정을 수정합니다."""
    mode = data.get('mode', 'template_keep')
    if mode not in VALID_MODES:
        raise FontManagerError(
            f'유효하지 않은 모드입니다: {mode}. '
            f'가능한 값: {", ".join(VALID_MODES)}'
        )

    active_preset_id = data.get('active_preset_id')

    # 프리셋 적용/강제 모드에서 프리셋 ID 유효성 검증
    if mode != 'template_keep' and active_preset_id:
        if get_preset(active_preset_id) is None:
            raise FontManagerError('존재하지 않는 프리셋입니다.')

    settings = {
        'mode': mode,
        'active_preset_id': active_preset_id,
    }
    _save_settings(settings)
    logger.info('폰트 설정 변경: mode=%s, preset=%s', mode, active_preset_id)
    return settings
