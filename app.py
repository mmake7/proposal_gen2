"""
PPROPOSAL – Flask Backend Application
AI 기반 공공기관 제안서 자동 생성 시스템
"""

from __future__ import annotations

import io
import logging
import os

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

from services.excel_exporter import export_to_excel, generate_filename
from services.template_manager import (
    save_template, list_templates, get_template_detail, delete_template,
    get_slide_thumbnail, TemplateManagerError,
)
from services.font_manager import (
    list_presets, create_preset, update_preset, delete_preset,
    get_font_settings, update_font_settings, FontManagerError,
)
from services.toc_manager import (
    list_toc_templates, get_toc_template, create_toc_template,
    update_toc_template, delete_toc_template, get_current_toc,
    set_current_toc, apply_toc_template, finalize_toc, TocManagerError,
)
from services.toc_template_mapper import (
    map_toc_to_template, get_mapping, update_mapping, MapperError,
)
from services.content_generator import (
    ContentGenerator, get_generated_content, ContentGeneratorError,
)
from services.pptx_filler import fill_template, PptxFillerError
from services_v2.documents import ingest_bytes as v2_ingest_bytes, IngestError
from services_v2.orchestrator import (
    analyze_rfp_document, OrchestratorError,
)
from services_v2.results.exporters import (
    to_excel as v2_to_excel, to_markdown as v2_to_markdown,
)
from services_v2.results.rfp_analysis import RfpAnalysisResult

from config import config

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_APP_DIR, '.env'))
load_dotenv(os.path.join(_APP_DIR, '.env.local'), override=True)  # .env.local이 우선

logger = logging.getLogger(__name__)

# ── 최근 분석 결과 캐시 (단일 사용자용) ─────────────────────
_last_analysis: dict | None = None
_rfp_full_text: str | None = None
# v2 객체 (Export 라우트에서 재사용)
_last_v2_result: RfpAnalysisResult | None = None
_last_v2_filename: str = ''

# ── App Factory ──────────────────────────────────────────────
def create_app(config_name=None):
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )

    # ── Configuration ────────────────────────────────────────
    # FLASK_ENV로 환경 선택. 미설정 시 'production'(안전 기본값: debug off).
    # 로컬에서 Werkzeug 디버거/리로더를 쓰려면 FLASK_ENV=development.
    # SECRET_KEY / MAX_CONTENT_LENGTH는 config.py(Config)에서 일괄 관리.
    config_name = config_name or os.environ.get('FLASK_ENV', 'production')
    app.config.from_object(config.get(config_name, config['default']))

    # ── CORS ─────────────────────────────────────────────────
    CORS(app, resources={r'/api/*': {'origins': '*'}})

    # ── Register Routes ──────────────────────────────────────
    register_routes(app)
    register_error_handlers(app)

    return app


# ── Routes ───────────────────────────────────────────────────
def _register_core_parse(app):
    @app.route('/')
    def index():
        """메인 페이지 렌더링"""
        return render_template('index.html')

    @app.route('/api/parse', methods=['POST'])
    def api_parse():
        """RFP 문서(PDF/HWPX/DOCX) 업로드 및 분석 (v2 멀티에이전트 정본)."""
        global _last_analysis, _rfp_full_text, _last_v2_result, _last_v2_filename

        # ── 파일 유효성 검사 ──────────────────────────────────
        if 'file' not in request.files:
            return jsonify({'error': '파일이 전송되지 않았습니다.'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400
        ext = file.filename.lower().rsplit('.', 1)[-1]
        if ext not in ('pdf', 'hwpx', 'docx'):
            return jsonify({
                'error': 'PDF, HWPX 또는 DOCX 파일만 업로드할 수 있습니다. '
                         '(.hwp/.doc는 변환 후 업로드)',
            }), 415

        file_bytes = file.read()

        # ── v2 멀티에이전트 분석 ──────────────────────────────
        try:
            doc = v2_ingest_bytes(file_bytes, filename=file.filename)
            result_obj = analyze_rfp_document(doc)
        except (OrchestratorError, IngestError) as exc:
            logger.warning('RFP 분석 실패: %s', exc)
            return jsonify({'error': f'분석 실패: {exc}'}), 422

        result_dict = result_obj.to_dict()
        _last_analysis = result_dict
        _last_v2_result = result_obj
        _last_v2_filename = file.filename
        _rfp_full_text = doc.full_text  # content_generator용

        if result_dict.get('toc'):
            set_current_toc(result_dict['toc'])
        return jsonify(result_dict)


def _register_templates(app):
    # ── 템플릿 관리 API ────────────────────────────────────
    @app.route('/api/templates/upload', methods=['POST'])
    def api_templates_upload():
        """PPTX 템플릿 업로드 및 분석"""
        if 'file' not in request.files:
            return jsonify({'error': '파일이 전송되지 않았습니다.'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400

        if not file.filename.lower().endswith('.pptx'):
            return jsonify({'error': 'PPTX 파일만 업로드할 수 있습니다.'}), 415

        try:
            file_bytes = file.read()
            result = save_template(file_bytes, file.filename)
        except TemplateManagerError as exc:
            logger.warning('템플릿 분석 실패: %s', exc)
            return jsonify({'error': f'템플릿 파일을 처리할 수 없습니다: {exc}'}), 422

        return jsonify(result), 201

    @app.route('/api/templates', methods=['GET'])
    def api_templates_list():
        """저장된 템플릿 목록 조회"""
        templates = list_templates()
        return jsonify(templates)

    @app.route('/api/templates/<template_id>', methods=['GET'])
    def api_templates_detail(template_id):
        """템플릿 상세정보 조회"""
        detail = get_template_detail(template_id)
        if detail is None:
            return jsonify({'error': '템플릿을 찾을 수 없습니다.'}), 404
        return jsonify(detail)

    @app.route('/api/templates/<template_id>/slides/<int:slide_num>/thumbnail',
               methods=['GET'])
    def api_templates_thumbnail(template_id, slide_num):
        """슬라이드 썸네일 이미지 반환"""
        width = request.args.get('w', 480, type=int)
        width = max(120, min(width, 1200))

        png_bytes = get_slide_thumbnail(template_id, slide_num, width)
        if png_bytes is None:
            return jsonify({'error': '썸네일을 생성할 수 없습니다.'}), 404

        return send_file(
            io.BytesIO(png_bytes),
            mimetype='image/png',
            download_name=f'slide_{slide_num}.png',
        )

    @app.route('/api/templates/<template_id>', methods=['DELETE'])
    def api_templates_delete(template_id):
        """템플릿 삭제"""
        deleted = delete_template(template_id)
        if not deleted:
            return jsonify({'error': '템플릿을 찾을 수 없습니다.'}), 404
        return jsonify({'message': '템플릿이 삭제되었습니다.'}), 200



def _register_fonts(app):
    # ── 폰트 프리셋 API ────────────────────────────────────
    @app.route('/api/fonts/presets', methods=['GET'])
    def api_fonts_presets_list():
        """폰트 프리셋 목록 조회"""
        presets = list_presets()
        return jsonify(presets)

    @app.route('/api/fonts/presets', methods=['POST'])
    def api_fonts_presets_create():
        """커스텀 폰트 프리셋 생성"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        try:
            preset = create_preset(data)
        except FontManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(preset), 201

    @app.route('/api/fonts/presets/<preset_id>', methods=['PUT'])
    def api_fonts_presets_update(preset_id):
        """폰트 프리셋 수정"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        try:
            preset = update_preset(preset_id, data)
        except FontManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        if preset is None:
            return jsonify({'error': '프리셋을 찾을 수 없습니다.'}), 404
        return jsonify(preset)

    @app.route('/api/fonts/presets/<preset_id>', methods=['DELETE'])
    def api_fonts_presets_delete(preset_id):
        """폰트 프리셋 삭제 (커스텀만 가능)"""
        try:
            deleted = delete_preset(preset_id)
        except FontManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        if not deleted:
            return jsonify({'error': '프리셋을 찾을 수 없습니다.'}), 404
        return jsonify({'message': '프리셋이 삭제되었습니다.'})

    @app.route('/api/fonts/settings', methods=['GET'])
    def api_fonts_settings_get():
        """폰트 적용 설정 조회"""
        settings = get_font_settings()
        return jsonify(settings)

    @app.route('/api/fonts/settings', methods=['PUT'])
    def api_fonts_settings_update():
        """폰트 적용 설정 수정"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        try:
            settings = update_font_settings(data)
        except FontManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(settings)



def _register_toc(app):
    # ── TOC 관리 API ──────────────────────────────────────
    @app.route('/api/toc/templates', methods=['GET'])
    def api_toc_templates_list():
        """TOC 표준 템플릿 목록 조회"""
        templates = list_toc_templates()
        return jsonify(templates)

    @app.route('/api/toc/templates', methods=['POST'])
    def api_toc_templates_create():
        """커스텀 TOC 템플릿 생성"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        try:
            template = create_toc_template(data)
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(template), 201

    @app.route('/api/toc/templates/<template_id>', methods=['PUT'])
    def api_toc_templates_update(template_id):
        """커스텀 TOC 템플릿 수정"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        try:
            updated = update_toc_template(template_id, data)
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        if not updated:
            return jsonify({'error': '템플릿을 찾을 수 없습니다.'}), 404
        return jsonify(updated)

    @app.route('/api/toc/templates/<template_id>', methods=['DELETE'])
    def api_toc_templates_delete(template_id):
        """커스텀 TOC 템플릿 삭제"""
        try:
            deleted = delete_toc_template(template_id)
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        if not deleted:
            return jsonify({'error': '템플릿을 찾을 수 없습니다.'}), 404
        return jsonify({'message': 'TOC 템플릿이 삭제되었습니다.'})

    @app.route('/api/toc/current', methods=['GET'])
    def api_toc_current_get():
        """현재 세션 TOC 조회"""
        return jsonify(get_current_toc())

    @app.route('/api/toc/current', methods=['PUT'])
    def api_toc_current_update():
        """세션 TOC 전체 업데이트 (에디터에서 일괄 저장)"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        items = data.get('items', [])
        if not isinstance(items, list):
            return jsonify({'error': '올바른 목차 데이터가 아닙니다.'}), 400
        try:
            set_current_toc(items)
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(get_current_toc())

    @app.route('/api/toc/current/apply-template', methods=['POST'])
    def api_toc_apply_template():
        """표준 TOC 템플릿을 현재 세션에 적용"""
        data = request.get_json()
        if not data or not data.get('template_id'):
            return jsonify({'error': '템플릿 ID가 필요합니다.'}), 400
        try:
            result = apply_toc_template(data['template_id'])
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(result)

    @app.route('/api/toc/current/finalize', methods=['POST'])
    def api_toc_finalize():
        """현재 TOC를 확정 (콘텐츠 생성 진행 가능)"""
        try:
            result = finalize_toc()
        except TocManagerError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(result)



def _register_proposal(app):
    # ── 제안서 생성 파이프라인 API ─────────────────────────
    @app.route('/api/proposal/map', methods=['POST'])
    def api_proposal_map():
        """TOC↔템플릿 자동 매핑"""
        data = request.get_json()
        if not data or not data.get('template_id'):
            return jsonify({'error': '템플릿 ID가 필요합니다.'}), 400

        template_id = data['template_id']

        # 템플릿 상세정보 로드
        from services.template_manager import get_template_detail
        template_detail = get_template_detail(template_id)
        if template_detail is None:
            return jsonify({'error': '템플릿을 찾을 수 없습니다.'}), 404

        # 현재 TOC 확인
        toc_state = get_current_toc()
        toc_items = toc_state.get('items', [])
        if not toc_items:
            return jsonify({'error': '목차가 없습니다. 먼저 목차를 확정해주세요.'}), 400

        try:
            result = map_toc_to_template(toc_items, template_detail)
        except MapperError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(result)

    @app.route('/api/proposal/map', methods=['PUT'])
    def api_proposal_map_update():
        """매핑 수동 수정"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400

        toc_index = data.get('toc_index')
        chapter_index = data.get('chapter_index')  # None이면 매핑 해제

        if toc_index is None:
            return jsonify({'error': 'toc_index가 필요합니다.'}), 400

        try:
            result = update_mapping(int(toc_index), chapter_index)
        except MapperError as exc:
            return jsonify({'error': str(exc)}), 422
        return jsonify(result)

    @app.route('/api/proposal/generate', methods=['POST'])
    def api_proposal_generate():
        """TOC 기반 콘텐츠 생성"""
        toc_state = get_current_toc()
        toc_items = toc_state.get('items', [])
        if not toc_items:
            return jsonify({'error': '목차가 없습니다.'}), 400

        if _last_analysis is None:
            return jsonify({'error': '분석 결과가 없습니다.'}), 400

        rfp_text = _rfp_full_text or ''

        try:
            generator = ContentGenerator()
            result = generator.generate_all(toc_items, rfp_text, _last_analysis)
        except ContentGeneratorError as exc:
            logger.error('콘텐츠 생성 실패: %s', exc)
            return jsonify({'error': str(exc)}), 422

        return jsonify(result)

    @app.route('/api/proposal/content', methods=['GET'])
    def api_proposal_content():
        """생성된 콘텐츠 조회"""
        content = get_generated_content()
        return jsonify(content)

    @app.route('/api/proposal/export', methods=['POST'])
    def api_proposal_export():
        """PPTX 파일 생성 및 다운로드"""
        data = request.get_json() or {}
        template_id_override = data.get('template_id')

        # 매핑 확인
        mapping = get_mapping()
        if mapping is None:
            return jsonify({'error': '매핑 데이터가 없습니다.'}), 400

        content = get_generated_content()
        if not content.get('sections'):
            return jsonify({'error': '생성된 콘텐츠가 없습니다.'}), 400

        toc_state = get_current_toc()
        toc_items = toc_state.get('items', [])

        # 템플릿 ID 결정
        from services.toc_template_mapper import get_template_id
        used_template_id = template_id_override or get_template_id()
        if not used_template_id:
            return jsonify({'error': '템플릿 ID가 필요합니다.'}), 400

        try:
            buf = fill_template(used_template_id, mapping, content, toc_items)
        except PptxFillerError as exc:
            logger.error('PPTX 생성 실패: %s', exc)
            return jsonify({'error': str(exc)}), 422

        # 파일명 생성
        project_name = ''
        if _last_analysis and _last_analysis.get('overview'):
            project_name = _last_analysis['overview'].get('project_name', '')
        filename = f"{project_name or 'proposal'}_제안서.pptx"

        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            as_attachment=True,
            download_name=filename,
        )



def _register_exports(app):
    @app.route('/api/download/excel', methods=['GET'])
    def api_download_excel():
        """분석 결과 Excel 다운로드

        최근 분석 결과를 4개 시트(사업개요, 요구사항, 배점기준, 제안목차)로
        구성된 Excel 파일로 변환하여 다운로드합니다.
        """
        if _last_analysis is None:
            return jsonify({
                'error': '다운로드할 분석 결과가 없습니다. 먼저 RFP를 분석해주세요.'
            }), 404

        try:
            # 현재 세션 TOC가 있으면 분석 결과 대신 사용
            export_data = dict(_last_analysis)
            current_toc = get_current_toc()
            if current_toc.get('items'):
                export_data['toc'] = current_toc['items']
            buf = export_to_excel(export_data)
            filename = generate_filename(_last_analysis.get('overview'))
        except Exception as exc:
            logger.error('Excel 생성 실패: %s', exc)
            return jsonify({
                'error': f'Excel 파일 생성 중 오류가 발생했습니다: {exc}'
            }), 500

        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename,
        )

    # ── v2 결과 Export ────────────────────────────────────
    def _v2_safe_name(suffix: str) -> str:
        """다운로드 파일명 — v2 결과의 사업명 또는 원본 파일명 기반."""
        if _last_v2_result and _last_v2_result.overview \
                and _last_v2_result.overview.project_name:
            base = _last_v2_result.overview.project_name
        elif _last_v2_filename:
            base = os.path.splitext(_last_v2_filename)[0]
        else:
            base = 'rfp_analysis'
        return f'{base}_v2{suffix}'

    @app.route('/api/v2/export/excel', methods=['GET'])
    def api_v2_export_excel():
        """마지막 v2 분석 결과 → Excel 다운로드 (7시트)."""
        if _last_v2_result is None:
            return jsonify({
                'error': 'v2 분석 결과 없음. /api/parse 먼저 호출하세요.'
            }), 404
        try:
            buf = v2_to_excel(_last_v2_result)
        except Exception as exc:
            logger.error('v2 Excel 생성 실패: %s', exc)
            return jsonify({'error': f'Excel 생성 실패: {exc}'}), 500
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=_v2_safe_name('.xlsx'),
        )

    @app.route('/api/v2/export/markdown', methods=['GET'])
    def api_v2_export_markdown():
        """마지막 v2 분석 결과 → 마크다운 보고서 다운로드."""
        if _last_v2_result is None:
            return jsonify({
                'error': 'v2 분석 결과 없음. /api/parse 먼저 호출하세요.'
            }), 404
        md = v2_to_markdown(_last_v2_result, filename=_last_v2_filename)
        return send_file(
            io.BytesIO(md.encode('utf-8')),
            mimetype='text/markdown; charset=utf-8',
            as_attachment=True,
            download_name=_v2_safe_name('.md'),
        )

    @app.route('/api/v2/export/json', methods=['GET'])
    def api_v2_export_json():
        """마지막 v2 분석 결과 → 전체 JSON 다운로드."""
        if _last_v2_result is None:
            return jsonify({
                'error': 'v2 분석 결과 없음. /api/parse 먼저 호출하세요.'
            }), 404
        import json as _json
        body = _json.dumps(_last_v2_result.to_dict(), ensure_ascii=False, indent=2)
        return send_file(
            io.BytesIO(body.encode('utf-8')),
            mimetype='application/json; charset=utf-8',
            as_attachment=True,
            download_name=_v2_safe_name('.json'),
        )


# ── Error Handlers ───────────────────────────────────────────


def register_routes(app):
    """도메인별 라우트 등록 진입점 (구 단일 거대 함수를 분해)."""
    _register_core_parse(app)
    _register_templates(app)
    _register_fonts(app)
    _register_toc(app)
    _register_proposal(app)
    _register_exports(app)


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': '요청한 리소스를 찾을 수 없습니다.'}), 404
        return render_template('index.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': '파일 크기가 50MB를 초과했습니다.'}), 413

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': '서버 내부 오류가 발생했습니다.'}), 500


# ── Entry Point ──────────────────────────────────────────────
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    # debug는 config(FLASK_ENV)에서 결정 — 운영에서 Werkzeug 디버거(RCE) 노출 방지.
    app.run(host=host, port=port, debug=app.config.get('DEBUG', False))
