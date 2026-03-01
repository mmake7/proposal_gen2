/* ============================================================
   Flask API Client – RFP 분석 시스템 백엔드 연동
   ============================================================
   API Endpoints:
     POST /api/parse          – PDF 파일 업로드 및 분석
     GET  /api/download/excel – 분석 결과 Excel 다운로드
   ============================================================ */
(function () {
  'use strict';

  /* ── 설정 ── */
  var API_BASE = '';
  var PARSE_ENDPOINT = '/api/parse';
  var DOWNLOAD_ENDPOINT = '/api/download/excel';
  var REQUEST_TIMEOUT_MS = 120000; /* 2분 */

  /* ── 에러 코드 → 사용자 메시지 매핑 ── */
  var ERROR_MESSAGES = {
    NETWORK_ERROR: {
      title: '네트워크 연결 오류',
      desc: '서버에 연결할 수 없습니다. 네트워크 상태를 확인하고 다시 시도해주세요.'
    },
    TIMEOUT: {
      title: '요청 시간 초과',
      desc: '서버 응답 시간이 초과되었습니다. 파일 크기를 확인하고 다시 시도해주세요.'
    },
    SERVER_ERROR: {
      title: '서버 오류가 발생했습니다',
      desc: '서버에서 요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
    },
    INVALID_RESPONSE: {
      title: '응답 데이터 오류',
      desc: '서버 응답을 처리할 수 없습니다. 관리자에게 문의해주세요.'
    },
    PARSE_FAILED: {
      title: 'PDF 분석 실패',
      desc: 'PDF 파일을 분석할 수 없습니다. 파일이 손상되었거나 지원되지 않는 형식일 수 있습니다.'
    },
    FILE_TOO_LARGE: {
      title: '파일 크기 초과',
      desc: '업로드할 수 있는 최대 파일 크기를 초과했습니다.'
    },
    UNSUPPORTED_FILE: {
      title: '지원되지 않는 파일 형식',
      desc: 'PDF 파일만 업로드할 수 있습니다.'
    }
  };

  /* ============================================================
     HTTP 상태코드 기반 에러 메시지 결정
     ============================================================ */
  function getErrorForStatus(status, serverMessage) {
    if (status === 413) return ERROR_MESSAGES.FILE_TOO_LARGE;
    if (status === 415) return ERROR_MESSAGES.UNSUPPORTED_FILE;
    if (status === 422) {
      return {
        title: ERROR_MESSAGES.PARSE_FAILED.title,
        desc: serverMessage || ERROR_MESSAGES.PARSE_FAILED.desc
      };
    }
    if (status >= 500) return ERROR_MESSAGES.SERVER_ERROR;
    return {
      title: '요청 처리 실패 (' + status + ')',
      desc: serverMessage || '알 수 없는 오류가 발생했습니다. 다시 시도해주세요.'
    };
  }

  /* ============================================================
     API 응답 데이터 검증
     ============================================================ */
  function validateParseResponse(data) {
    if (!data || typeof data !== 'object') {
      return { valid: false, error: 'INVALID_RESPONSE' };
    }

    /* 최소 필수 필드 확인 – 하나라도 있으면 유효 */
    var hasOverview = data.overview && typeof data.overview === 'object';
    var hasRequirements = Array.isArray(data.requirements);
    var hasScoring = Array.isArray(data.scoring);
    var hasToc = Array.isArray(data.toc);

    if (!hasOverview && !hasRequirements && !hasScoring && !hasToc) {
      return { valid: false, error: 'INVALID_RESPONSE' };
    }

    return { valid: true };
  }

  /* ============================================================
     RFP PDF 파싱 API 호출
     POST /api/parse (multipart/form-data)

     @param {File} file – 업로드할 PDF 파일
     @param {Object} callbacks
       .onProgress(stepIndex)   – 단계 진행 콜백 (0~3)
       .onSuccess(data)         – 성공 콜백 (파싱된 JSON)
       .onError(title, desc)    – 에러 콜백
     @returns {Object} { abort: Function }
     ============================================================ */
  function parseRfp(file, callbacks) {
    var cb = callbacks || {};
    var aborted = false;

    /* FormData 구성 */
    var formData = new FormData();
    formData.append('file', file);

    /* XMLHttpRequest로 타임아웃 + abort 지원 */
    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_BASE + PARSE_ENDPOINT);
    xhr.timeout = REQUEST_TIMEOUT_MS;
    xhr.responseType = 'json';

    /* 업로드 진행률 → 0단계 (파일 업로드) 표시 */
    xhr.upload.addEventListener('progress', function (e) {
      if (aborted) return;
      if (e.lengthComputable && cb.onUploadProgress) {
        cb.onUploadProgress(e.loaded, e.total);
      }
    });

    /* 업로드 완료 → 1단계 (서버 분석 중) */
    xhr.upload.addEventListener('load', function () {
      if (aborted) return;
      if (cb.onProgress) cb.onProgress(1);
    });

    /* 응답 수신 완료 */
    xhr.addEventListener('load', function () {
      if (aborted) return;

      if (xhr.status >= 200 && xhr.status < 300) {
        var data = xhr.response;

        /* JSON 파싱 실패 시 수동 파싱 시도 */
        if (typeof data === 'string') {
          try {
            data = JSON.parse(data);
          } catch (e) {
            if (cb.onError) {
              cb.onError(
                ERROR_MESSAGES.INVALID_RESPONSE.title,
                ERROR_MESSAGES.INVALID_RESPONSE.desc
              );
            }
            return;
          }
        }

        /* 응답 데이터 검증 */
        var validation = validateParseResponse(data);
        if (!validation.valid) {
          if (cb.onError) {
            var errMsg = ERROR_MESSAGES[validation.error] || ERROR_MESSAGES.INVALID_RESPONSE;
            cb.onError(errMsg.title, errMsg.desc);
          }
          return;
        }

        /* 성공 */
        if (cb.onProgress) cb.onProgress(3);
        if (cb.onSuccess) cb.onSuccess(data);
      } else {
        /* HTTP 에러 */
        var serverMessage = '';
        try {
          var errBody = typeof xhr.response === 'object' ? xhr.response : JSON.parse(xhr.responseText);
          serverMessage = errBody.message || errBody.error || '';
        } catch (e) { /* ignore */ }

        var errInfo = getErrorForStatus(xhr.status, serverMessage);
        if (cb.onError) cb.onError(errInfo.title, errInfo.desc);
      }
    });

    /* 네트워크 에러 */
    xhr.addEventListener('error', function () {
      if (aborted) return;
      if (cb.onError) {
        cb.onError(
          ERROR_MESSAGES.NETWORK_ERROR.title,
          ERROR_MESSAGES.NETWORK_ERROR.desc
        );
      }
    });

    /* 타임아웃 */
    xhr.addEventListener('timeout', function () {
      if (aborted) return;
      if (cb.onError) {
        cb.onError(
          ERROR_MESSAGES.TIMEOUT.title,
          ERROR_MESSAGES.TIMEOUT.desc
        );
      }
    });

    /* 전송 시작 → 0단계 */
    if (cb.onProgress) cb.onProgress(0);
    xhr.send(formData);

    /* abort 핸들 반환 */
    return {
      abort: function () {
        aborted = true;
        xhr.abort();
      }
    };
  }

  /* ============================================================
     API 응답 데이터 정규화
     서버 응답 형식을 프론트엔드 렌더링에 맞게 변환
     ============================================================ */

  /* 사업개요 정규화 */
  function normalizeOverview(raw) {
    if (!raw) return null;
    return {
      projectName:    raw.project_name    || raw.projectName    || '',
      organization:   raw.organization    || raw.org_name       || '',
      period:         raw.period          || '',
      budget:         raw.budget          || '',
      budgetUnit:     raw.budget_unit     || raw.budgetUnit     || '백만원',
      contractType:   raw.contract_type   || raw.contractType   || '',
      contractMethod: raw.contract_method || raw.contractMethod || '',
      qualifications: raw.qualifications  || '',
      location:       raw.location        || '',
      purpose:        raw.purpose         || ''
    };
  }

  /* 요구사항 정규화 */
  function normalizeRequirements(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(function (item) {
      return {
        category: item.category || '기능',
        id:       item.id       || '',
        name:     item.name     || item.title || '',
        desc:     item.desc     || item.description || '',
        level:    item.level    || item.priority || '선택'
      };
    });
  }

  /* 배점기준 정규화 */
  function normalizeScoring(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(function (item) {
      return {
        category: item.category || '',
        item:     item.item     || item.name || '',
        criteria: item.criteria || item.description || '',
        score:    parseInt(item.score, 10) || 0
      };
    });
  }

  /* 제안목차 정규화 (재귀) */
  function normalizeTocItem(item) {
    return {
      level:       item.level       || 1,
      number:      item.number      || '',
      title:       item.title       || '',
      description: item.description || '',
      reqIds:      item.req_ids     || item.reqIds || [],
      children: Array.isArray(item.children)
        ? item.children.map(normalizeTocItem)
        : []
    };
  }

  function normalizeToc(raw) {
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeTocItem);
  }

  /* 전체 응답 정규화 */
  function normalizeResponse(data) {
    return {
      overview:     normalizeOverview(data.overview),
      requirements: normalizeRequirements(data.requirements),
      scoring:      normalizeScoring(data.scoring),
      toc:          normalizeToc(data.toc)
    };
  }

  /* ============================================================
     전역 API 노출
     ============================================================ */
  window.ApiClient = {
    parseRfp:          parseRfp,
    normalizeResponse: normalizeResponse,
    ERROR_MESSAGES:    ERROR_MESSAGES
  };

})();
