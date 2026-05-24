/* ============================================================
   Flask API Client – RFP 분석 시스템 백엔드 연동
   ============================================================
   API Endpoints:
     POST /api/parse[?engine=v2] – RFP(PDF/HWPX) 업로드 및 분석
     GET  /api/download/excel    – v1 분석 결과 Excel 다운로드
     GET  /api/v2/export/excel    – v2 분석 결과 Excel (7시트)
     GET  /api/v2/export/markdown – v2 마크다운 보고서
     GET  /api/v2/export/json     – v2 전체 JSON
   ============================================================ */
(function () {
  'use strict';

  /* ── 설정 ── */
  var API_BASE = '';
  var PARSE_ENDPOINT = '/api/parse';
  var DOWNLOAD_ENDPOINT = '/api/download/excel';
  var V2_EXPORT_ENDPOINTS = {
    excel:    '/api/v2/export/excel',
    markdown: '/api/v2/export/markdown',
    json:     '/api/v2/export/json'
  };
  var REQUEST_TIMEOUT_MS = 180000; /* 3분 (v2는 더 오래 걸림) */

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
    if (status === 404) {
      return {
        title: '데이터 없음',
        desc: serverMessage || '요청한 데이터를 찾을 수 없습니다.'
      };
    }
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
  function parseRfp(file, callbacks, options) {
    var cb = callbacks || {};
    var opts = options || {};
    var aborted = false;

    /* FormData 구성 */
    var formData = new FormData();
    formData.append('file', file);

    /* engine 쿼리 파라미터 — 'v2' 지정 시 v2 파이프라인 사용 */
    var url = API_BASE + PARSE_ENDPOINT;
    if (opts.engine === 'v2') {
      url += '?engine=v2';
    }

    /* XMLHttpRequest로 타임아웃 + abort 지원 */
    var xhr = new XMLHttpRequest();
    xhr.open('POST', url);
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
        category:      item.category || '기능',
        id:            item.id       || '',
        name:          item.name     || item.title || '',
        desc:          item.desc     || item.description || '',
        level:         item.level    || item.priority || '선택',
        /* 파서 전용 필드 (pass-through) */
        category_code: item.category_code || '',
        definition:    item.definition    || '',
        detail:        item.detail        || '',
        output_info:   item.output_info   || '',
        related_reqs:  item.related_reqs  || '',
        source:        item.source        || '',
        parse_method:  item.parse_method  || ''
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
      overview:       normalizeOverview(data.overview),
      requirements:   normalizeRequirements(data.requirements),
      scoring:        normalizeScoring(data.scoring),
      toc:            normalizeToc(data.toc),
      parser_stats:   data.parser_stats   || null,
      parser_summary: data.parser_summary || []
    };
  }

  /* ============================================================
     v2 결과 다운로드 (Excel/Markdown/JSON)
     서버 측에 마지막 v2 분석 결과가 캐시되어 있어야 함.

     @param {string} type – 'excel' | 'markdown' | 'json'
     @returns {Promise} – 성공 시 Blob, 실패 시 Error
     ============================================================ */
  function downloadV2(type) {
    var endpoint = V2_EXPORT_ENDPOINTS[type];
    if (!endpoint) {
      return Promise.reject(new Error('알 수 없는 다운로드 타입: ' + type));
    }
    return fetch(API_BASE + endpoint)
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (body) {
            throw new Error(body.error || ('다운로드 실패 (' + response.status + ')'));
          }, function () {
            throw new Error('다운로드 실패 (' + response.status + ')');
          });
        }
        /* 파일명을 Content-Disposition에서 추출 */
        var disp = response.headers.get('Content-Disposition') || '';
        var match = disp.match(/filename\*?=(?:UTF-8'')?["']?([^;"']+)["']?/i);
        var filename = match ? decodeURIComponent(match[1]) : ('rfp_v2.' + type);
        return response.blob().then(function (blob) {
          return { blob: blob, filename: filename };
        });
      })
      .then(function (result) {
        /* 브라우저 다운로드 트리거 */
        var url = URL.createObjectURL(result.blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = result.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        return result;
      });
  }

  /* ============================================================
     전역 API 노출
     ============================================================ */
  window.ApiClient = {
    parseRfp:          parseRfp,
    downloadV2:        downloadV2,
    normalizeResponse: normalizeResponse,
    ERROR_MESSAGES:    ERROR_MESSAGES
  };

})();
