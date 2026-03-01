"""
RFP 분석기 단위 테스트

Claude API 호출을 모킹하여 RfpAnalyzer의 응답 파싱 및
데이터 변환 로직을 테스트합니다.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from services.rfp_analyzer import (
    RfpAnalyzer,
    RfpAnalysisError,
    RfpAnalysisResult,
    RfpOverview,
    RfpRequirement,
    RfpScoringItem,
    RfpTocItem,
)


# ── 테스트용 Claude API 응답 픽스처 ──────────────────────────

SAMPLE_ANALYSIS_JSON = json.dumps({
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
        {
            'category': '기능',
            'id': 'FR-001',
            'name': '데이터 수집',
            'desc': 'IoT 센서 데이터 수집',
            'level': '필수',
        },
        {
            'category': '비기능',
            'id': 'NFR-001',
            'name': '가용성',
            'desc': '99.9% 가용성',
            'level': '필수',
        },
    ],
    'scoring': [
        {
            'category': '기술',
            'item': '아키텍처',
            'criteria': '확장성 설계',
            'score': 20,
        },
    ],
    'toc': [
        {
            'level': 1,
            'title': '사업 이해',
            'children': [
                {'level': 2, 'title': '사업 개요', 'children': []},
            ],
        },
    ],
}, ensure_ascii=False)


def _make_mock_response(text: str):
    """Claude API 응답 객체를 모킹합니다."""
    block = MagicMock()
    block.type = 'text'
    block.text = text

    response = MagicMock()
    response.content = [block]
    return response


# ── 테스트: 정상 분석 ────────────────────────────────────────

class TestRfpAnalyzerParsing:
    """Claude 응답 파싱 및 데이터 변환 테스트"""

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_analyze_success(self, mock_get_client):
        """정상적인 JSON 응답을 올바르게 파싱한다"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(SAMPLE_ANALYSIS_JSON)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트 RFP 텍스트')

        assert isinstance(result, RfpAnalysisResult)
        assert result.overview is not None
        assert result.overview.project_name == '스마트시티 통합플랫폼 구축'
        assert result.overview.organization == '한국정보화진흥원'
        assert result.overview.budget == '500'
        assert result.overview.budget_unit == '백만원'

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_requirements_parsed(self, mock_get_client):
        """요구사항 목록이 올바르게 파싱된다"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(SAMPLE_ANALYSIS_JSON)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert len(result.requirements) == 2
        assert result.requirements[0].category == '기능'
        assert result.requirements[0].id == 'FR-001'
        assert result.requirements[1].category == '비기능'
        assert result.requirements[1].id == 'NFR-001'

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_scoring_parsed(self, mock_get_client):
        """배점기준이 올바르게 파싱된다"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(SAMPLE_ANALYSIS_JSON)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert len(result.scoring) == 1
        assert result.scoring[0].item == '아키텍처'
        assert result.scoring[0].score == 20

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_toc_parsed_recursive(self, mock_get_client):
        """제안목차가 재귀적으로 파싱된다"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(SAMPLE_ANALYSIS_JSON)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert len(result.toc) == 1
        assert result.toc[0].title == '사업 이해'
        assert len(result.toc[0].children) == 1
        assert result.toc[0].children[0].title == '사업 개요'

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_to_dict_format(self, mock_get_client):
        """to_dict()가 프론트엔드 호환 형식을 반환한다"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(SAMPLE_ANALYSIS_JSON)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')
        d = result.to_dict()

        # 프론트엔드 필수 키 확인
        assert 'overview' in d
        assert 'requirements' in d
        assert 'scoring' in d
        assert 'toc' in d

        # overview 필드명 확인
        ov = d['overview']
        assert 'project_name' in ov
        assert 'budget_unit' in ov
        assert 'contract_type' in ov
        assert 'contract_method' in ov

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_markdown_codeblock_stripped(self, mock_get_client):
        """마크다운 코드블록으로 감싼 JSON도 파싱된다"""
        wrapped = f'```json\n{SAMPLE_ANALYSIS_JSON}\n```'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(wrapped)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert result.overview is not None
        assert result.overview.project_name == '스마트시티 통합플랫폼 구축'


# ── 테스트: 에러 처리 ────────────────────────────────────────

class TestRfpAnalyzerErrors:
    """에러 시나리오 테스트"""

    def test_empty_text_raises(self):
        """빈 텍스트로 분석 시 에러 발생"""
        analyzer = RfpAnalyzer(api_key='test-key')
        with pytest.raises(RfpAnalysisError, match='비어있습니다'):
            analyzer.analyze('')

    def test_whitespace_text_raises(self):
        """공백만 있는 텍스트로 분석 시 에러 발생"""
        analyzer = RfpAnalyzer(api_key='test-key')
        with pytest.raises(RfpAnalysisError, match='비어있습니다'):
            analyzer.analyze('   \n\t  ')

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_invalid_json_raises(self, mock_get_client):
        """Claude가 잘못된 JSON을 반환하면 에러 발생"""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response('이것은 JSON이 아닙니다')
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        with pytest.raises(RfpAnalysisError, match='파싱'):
            analyzer.analyze('테스트')

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_api_error_raises(self, mock_get_client):
        """Claude API 호출 실패 시 에러 발생"""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('API rate limit')
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        with pytest.raises(RfpAnalysisError, match='오류가 발생'):
            analyzer.analyze('테스트')

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_empty_api_response_raises(self, mock_get_client):
        """Claude가 빈 응답을 반환하면 에러 발생"""
        block = MagicMock()
        block.type = 'text'
        block.text = ''
        response = MagicMock()
        response.content = [block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        with pytest.raises(RfpAnalysisError, match='빈 응답'):
            analyzer.analyze('테스트')

    def test_missing_api_key_raises(self):
        """API 키 없이 분석 시 에러 발생"""
        analyzer = RfpAnalyzer(api_key='')
        with pytest.raises(RfpAnalysisError, match='ANTHROPIC_API_KEY'):
            analyzer.analyze('테스트')


# ── 테스트: 부분 데이터 처리 ─────────────────────────────────

class TestRfpAnalyzerPartialData:
    """부분적 또는 비정상 데이터 처리 테스트"""

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_missing_overview(self, mock_get_client):
        """overview가 없는 응답도 처리된다"""
        data = json.dumps({
            'requirements': [{'category': '기능', 'id': 'FR-001', 'name': '테스트', 'desc': '', 'level': '필수'}],
            'scoring': [],
            'toc': [],
        })
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(data)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert result.overview is None
        assert len(result.requirements) == 1

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_empty_arrays(self, mock_get_client):
        """빈 배열 응답도 처리된다"""
        data = json.dumps({
            'overview': {'project_name': '테스트 사업'},
            'requirements': [],
            'scoring': [],
            'toc': [],
        })
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(data)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert result.overview.project_name == '테스트 사업'
        assert result.requirements == []
        assert result.scoring == []
        assert result.toc == []

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_score_as_string_converted(self, mock_get_client):
        """score가 문자열로 오면 정수로 변환된다"""
        data = json.dumps({
            'overview': None,
            'requirements': [],
            'scoring': [{'category': '기술', 'item': '테스트', 'criteria': '', 'score': '15'}],
            'toc': [],
        })
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(data)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert result.scoring[0].score == 15

    @patch('services.rfp_analyzer.RfpAnalyzer._get_client')
    def test_invalid_score_defaults_zero(self, mock_get_client):
        """score가 파싱 불가능하면 0으로 기본값 설정"""
        data = json.dumps({
            'overview': None,
            'requirements': [],
            'scoring': [{'category': '기술', 'item': '테스트', 'criteria': '', 'score': 'N/A'}],
            'toc': [],
        })
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_mock_response(data)
        mock_get_client.return_value = mock_client

        analyzer = RfpAnalyzer(api_key='test-key')
        result = analyzer.analyze('테스트')

        assert result.scoring[0].score == 0


# ── 테스트: 데이터 클래스 ────────────────────────────────────

class TestDataClasses:
    """데이터 클래스 직렬화 테스트"""

    def test_overview_to_dict(self):
        ov = RfpOverview(project_name='테스트', budget='100')
        d = ov.to_dict()
        assert d['project_name'] == '테스트'
        assert d['budget'] == '100'
        assert d['budget_unit'] == '백만원'

    def test_requirement_to_dict(self):
        req = RfpRequirement(category='기능', id='FR-001', name='테스트', desc='설명', level='필수')
        d = req.to_dict()
        assert d == {'category': '기능', 'id': 'FR-001', 'name': '테스트', 'desc': '설명', 'level': '필수'}

    def test_scoring_to_dict(self):
        s = RfpScoringItem(category='기술', item='아키텍처', criteria='설계', score=20)
        d = s.to_dict()
        assert d['score'] == 20

    def test_toc_to_dict_recursive(self):
        child = RfpTocItem(level=2, title='소목차')
        parent = RfpTocItem(level=1, title='대목차', children=[child])
        d = parent.to_dict()
        assert d['level'] == 1
        assert len(d['children']) == 1
        assert d['children'][0]['title'] == '소목차'

    def test_result_to_dict_null_overview(self):
        result = RfpAnalysisResult()
        d = result.to_dict()
        assert d['overview'] is None
        assert d['requirements'] == []
        assert d['scoring'] == []
        assert d['toc'] == []
