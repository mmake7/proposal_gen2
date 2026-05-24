"""Fingerprint 라이브러리 단위 테스트 (LLM 미사용)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services_v2.results.fingerprints import (
    extract_fingerprint, format_for_classifier, load_library,
    save_library, update_library,
)
from services_v2.results.rfp_analysis import (
    Overview, Requirement, RfpAnalysisResult, RfpClassification,
    ScoringItem, ValidationReport,
)


def make_result(
    *,
    org='중앙부처', scheme='SFR/PER', fmt='table',
    dialect='정의/세부내용 필드명 사용',
    notes='행정안전부 청원24 RFP. 별표 1~10에 보안특약 포함. 부속서 다수.',
    req_count=55, confidence=0.92,
):
    return RfpAnalysisResult(
        overview=Overview(project_name='테스트'),
        requirements=[Requirement(id=f'FR-{i:03d}') for i in range(req_count)],
        scoring=[ScoringItem(score=5) for _ in range(20)],
        classification=RfpClassification(
            org_type=org, req_id_scheme=scheme, req_format=fmt,
            language_dialect=dialect, notes=notes,
        ),
        validation=ValidationReport(confidence=confidence, issues=[]),
    )


# ── extract_fingerprint ──────────────────────────────────

class TestExtractFingerprint:
    def test_basic_fields(self):
        result = make_result()
        fp = extract_fingerprint(result, filename='cheongwon.hwpx')
        assert fp['org_type'] == '중앙부처'
        assert fp['req_id_scheme'] == 'SFR/PER'
        assert fp['req_format'] == 'table'
        assert fp['filename'] == 'cheongwon.hwpx'
        assert fp['confidence'] == 0.92
        assert fp['requirements_count'] == 55

    def test_notes_keywords_extracted(self):
        result = make_result(
            notes='행정안전부 행정안전부 청원 청원 별표 별표 별표 부속서')
        fp = extract_fingerprint(result, filename='x')
        # 빈도순 상위 키워드
        assert '별표' in fp['notes_keywords']
        assert '청원' in fp['notes_keywords']

    def test_handles_missing_classification(self):
        result = RfpAnalysisResult()
        fp = extract_fingerprint(result, filename='x')
        assert fp['org_type'] == 'unknown'
        assert fp['confidence'] is None

    def test_filters_stopwords(self):
        result = make_result(notes='각종 여러 다양한 별표')
        fp = extract_fingerprint(result, filename='x')
        # 불용어는 제거됨
        assert '각종' not in fp['notes_keywords']
        assert '여러' not in fp['notes_keywords']
        assert '별표' in fp['notes_keywords']


# ── load/save library ───────────────────────────────────

class TestLibraryIO:
    def test_load_missing_returns_empty(self, tmp_path: Path):
        result = load_library(path=tmp_path / 'nope.json')
        assert result == []

    def test_save_then_load(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        sample = [{'org_type': '중앙부처', 'seen_count': 3}]
        save_library(sample, path=path)
        loaded = load_library(path=path)
        assert loaded == sample


# ── update_library ──────────────────────────────────────

class TestUpdateLibrary:
    def test_new_fingerprint_creates_group(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        update_library(make_result(), filename='a.hwpx', path=path)
        lib = load_library(path)
        assert len(lib) == 1
        assert lib[0]['org_type'] == '중앙부처'
        assert lib[0]['seen_count'] == 1

    def test_same_fingerprint_groups(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        update_library(make_result(), filename='a.hwpx', path=path)
        update_library(make_result(), filename='b.hwpx', path=path)
        lib = load_library(path)
        assert len(lib) == 1  # 같은 그룹
        assert lib[0]['seen_count'] == 2
        assert len(lib[0]['examples']) == 2

    def test_different_fingerprint_new_group(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        update_library(make_result(org='중앙부처'), filename='a.hwpx', path=path)
        update_library(make_result(org='지자체'), filename='b.hwpx', path=path)
        lib = load_library(path)
        assert len(lib) == 2

    def test_examples_capped(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        from services_v2.results.fingerprints import MAX_EXAMPLES_PER_FINGERPRINT
        for i in range(MAX_EXAMPLES_PER_FINGERPRINT + 3):
            update_library(make_result(), filename=f'r{i}.hwpx', path=path)
        lib = load_library(path)
        assert len(lib[0]['examples']) == MAX_EXAMPLES_PER_FINGERPRINT
        assert lib[0]['seen_count'] == MAX_EXAMPLES_PER_FINGERPRINT + 3


# ── format_for_classifier ──────────────────────────────

class TestFormatForClassifier:
    def test_empty_library_returns_empty(self):
        assert format_for_classifier([]) == ''

    def test_includes_fingerprint_summary(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        update_library(make_result(), filename='a.hwpx', path=path)
        library = load_library(path)
        text = format_for_classifier(library)
        assert '중앙부처' in text
        assert 'SFR/PER' in text
        assert 'table' in text
        assert '학습된 양식 사례' in text

    def test_max_chars_respected(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        # 큰 라이브러리 만들기
        for i in range(20):
            update_library(
                make_result(org=f'org{i}'),
                filename=f'r{i}.hwpx', path=path,
            )
        library = load_library(path)
        text = format_for_classifier(library, max_chars=500)
        assert len(text) <= 500

    def test_dialect_and_keywords_included(self, tmp_path: Path):
        path = tmp_path / 'fp.json'
        update_library(
            make_result(
                dialect='우리원 자칭, 산출정보 사용',
                notes='별표 별표 별표 부속서 부속서',
            ),
            filename='a.hwpx', path=path,
        )
        text = format_for_classifier(load_library(path))
        assert '우리원' in text
        assert '별표' in text or '부속서' in text
