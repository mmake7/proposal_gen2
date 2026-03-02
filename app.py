"""
PPROPOSAL – Flask Backend Application
AI 기반 공공기관 제안서 자동 생성 시스템
"""

import io
import logging
import os
import tempfile

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS

from services.pdf_extractor import PdfExtractor, PdfExtractionError
from services.rfp_analyzer import RfpAnalyzer, RfpAnalysisError
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
from services.rfp_requirement_parser import parse_rfp_requirements
from services.toc_template_mapper import (
    map_toc_to_template, get_mapping, update_mapping, MapperError,
)
from services.content_generator import (
    ContentGenerator, get_generated_content, ContentGeneratorError,
)
from services.pptx_filler import fill_template, PptxFillerError

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

logger = logging.getLogger(__name__)

# ── 최근 분석 결과 캐시 (단일 사용자용) ─────────────────────
_last_analysis: dict | None = None
_rfp_full_text: str | None = None

# ── App Factory ──────────────────────────────────────────────
def create_app():
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )

    # ── Configuration ────────────────────────────────────────
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # ── CORS ─────────────────────────────────────────────────
    CORS(app, resources={r'/api/*': {'origins': '*'}})

    # ── Register Routes ──────────────────────────────────────
    register_routes(app)
    register_error_handlers(app)

    return app


# ── 요구사항 파서-AI 병합 헬퍼 ────────────────────────────────
def _merge_parser_into_analysis(result_dict: dict, parser_result: dict) -> dict:
    """파서 결과를 AI 분석 결과에 병합한다.

    전략: 파서 결과(테이블/텍스트 기반)를 우선하고, AI 결과로 빈 필드를 보완.
    overview, scoring, toc 등 AI 전용 필드는 그대로 유지한다.
    """
    parser_reqs = parser_result.get('requirements', [])
    if not parser_reqs:
        return result_dict

    # AI 요구사항을 id 기준으로 인덱싱
    ai_by_id: dict[str, dict] = {}
    for r in result_dict.get('requirements', []):
        rid = r.get('id', '')
        if rid:
            ai_by_id[rid] = r

    merged = []
    seen_ids: set[str] = set()

    for pr in parser_reqs:
        req_id = pr.get('req_id', '')
        if not req_id or req_id in seen_ids:
            continue
        seen_ids.add(req_id)

        # 파서 definition + detail → desc
        definition = (pr.get('definition') or '').strip()
        detail = (pr.get('detail') or '').strip()
        if definition and detail:
            desc = f"{definition}\n{detail}"
        else:
            desc = definition or detail

        item = {
            'id': req_id,
            'name': (pr.get('name') or '').strip(),
            'category': (pr.get('category') or '').strip(),
            'desc': desc,
            'level': '',
            # 파서 전용 필드 보존
            'category_code': pr.get('category_code', ''),
            'definition': definition,
            'detail': detail,
            'output_info': (pr.get('output_info') or '').strip(),
            'related_reqs': (pr.get('related_reqs') or '').strip(),
            'source': (pr.get('source') or '').strip(),
            'parse_method': pr.get('parse_method', ''),
        }

        # AI 결과로 빈 필드 보완
        ai_item = ai_by_id.get(req_id, {})
        if not item['name'] and ai_item.get('name'):
            item['name'] = ai_item['name']
        if not item['category'] and ai_item.get('category'):
            item['category'] = ai_item['category']
        if not item['desc'] and ai_item.get('desc'):
            item['desc'] = ai_item['desc']
        if not item['level'] and ai_item.get('level'):
            item['level'] = ai_item['level']

        merged.append(item)

    # AI에만 있는 요구사항 추가 (파서가 놓친 것)
    for r in result_dict.get('requirements', []):
        rid = r.get('id', '')
        if rid and rid not in seen_ids:
            merged.append(r)
            seen_ids.add(rid)

    result_dict['requirements'] = merged

    # 파서 통계/요약 추가 (프론트엔드에서 참조 가능)
    result_dict['parser_stats'] = parser_result.get('stats', {})
    result_dict['parser_summary'] = parser_result.get('summary', [])

    return result_dict


# ── Routes ───────────────────────────────────────────────────
def register_routes(app):
    @app.route('/')
    def index():
        """메인 페이지 렌더링"""
        return render_template('index.html')

    @app.route('/api/parse', methods=['POST'])
    def api_parse():
        """RFP PDF 업로드 및 분석

        1. multipart/form-data로 PDF 파일 수신
        2. 유효성 검사 (존재, 파일명, 확장자)
        3. PdfExtractor로 텍스트 추출
        4. RfpAnalyzer(Claude API)로 AI 분석
        5. 구조화된 JSON 응답 반환
        """
        # ── 파일 유효성 검사 ──────────────────────────────────
        if 'file' not in request.files:
            return jsonify({'error': '파일이 전송되지 않았습니다.'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'PDF 파일만 업로드할 수 있습니다.'}), 415

        # ── PDF 텍스트 추출 ──────────────────────────────────
        try:
            file_bytes = file.read()
            extractor = PdfExtractor(enable_ocr=True)
            extraction = extractor.extract_from_bytes(
                file_bytes, filename=file.filename
            )
        except PdfExtractionError as exc:
            logger.warning('PDF 추출 실패: %s', exc)
            return jsonify({
                'error': f'PDF 파일을 처리할 수 없습니다: {exc}'
            }), 422

        if not extraction.full_text.strip():
            return jsonify({
                'error': 'PDF에서 텍스트를 추출할 수 없습니다. '
                         '스캔 기반 PDF이거나 이미지만 포함된 문서일 수 있습니다.'
            }), 422

        # ── AI 분석 ──────────────────────────────────────────
        ai_failed = False
        try:
            analyzer = RfpAnalyzer()
            analysis = analyzer.analyze(extraction.full_text)
            result_dict = analysis.to_dict()
        except RfpAnalysisError as exc:
            logger.warning('AI 분석 실패 (파서 폴백 시도): %s', exc)
            ai_failed = True
            # 파서로 폴백하기 위해 빈 구조 생성
            result_dict = {
                'overview': None,
                'requirements': [],
                'scoring': [],
                'toc': [],
            }

        # ── 요구사항 파서 병합 (파서 우선, AI 보완) ─────────
        try:
            # file_bytes를 임시 파일로 저장하여 pdfplumber에 전달
            with tempfile.NamedTemporaryFile(
                suffix='.pdf', delete=False,
            ) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                parser_result = parse_rfp_requirements(tmp_path)
                result_dict = _merge_parser_into_analysis(
                    result_dict, parser_result,
                )
                logger.info(
                    '요구사항 파서 병합 완료: %d건 (completeness %.1f%%)',
                    len(result_dict.get('requirements', [])),
                    parser_result.get('stats', {}).get('completeness_pct', 0),
                )
            finally:
                os.unlink(tmp_path)
        except Exception as exc:
            logger.warning('요구사항 파서 실행/병합 실패: %s', exc)
            # AI도 실패하고 파서도 실패하면 에러 반환
            if ai_failed:
                return jsonify({
                    'error': 'AI 분석과 요구사항 파서 모두 실패했습니다.'
                }), 422

        # 최근 분석 결과 저장 (Excel 다운로드용)
        global _last_analysis, _rfp_full_text
        _last_analysis = result_dict
        _rfp_full_text = extraction.full_text

        # AI가 생성한 TOC를 세션 TOC로 자동 설정
        if result_dict.get('toc'):
            set_current_toc(result_dict['toc'])

        return jsonify(result_dict)

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


# ── Error Handlers ───────────────────────────────────────────
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
    app.run(host='0.0.0.0', port=port, debug=True)
