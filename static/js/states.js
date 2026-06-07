/* ============================================================
   Error / Empty / Warning State UI Manager
   ============================================================
   다양한 상태에 대한 UI를 관리합니다:
   - 분석 실패 시 에러 상태 화면 (API 오류, 네트워크 오류, 타임아웃)
   - PDF 파싱 일부 항목 추출 실패 시 경고 배너
   - 신뢰도 점수 기반 '검토 필요' 표시
   - 빈 상태 화면 (안내 일러스트 + 메시지)
   ============================================================ */
(function () {
  'use strict';

  /* ── DOM 요소 캐시 ── */
  var errorCard        = document.getElementById('analysis-error');
  var errorInner       = document.getElementById('analysis-error-inner');
  var errorIcon        = document.getElementById('error-state-icon');
  var errorTitle       = document.getElementById('error-state-title');
  var errorDesc        = document.getElementById('error-state-desc');
  var errorCode        = document.getElementById('error-state-code');
  var errorCodeText    = document.getElementById('error-state-code-text');
  var errorRetryBtn    = document.getElementById('error-retry-btn');
  var errorReuploadBtn = document.getElementById('error-reupload-btn');
  var retryCountdown   = document.getElementById('error-retry-countdown');
  var retryCountText   = document.getElementById('error-retry-countdown-text');
  var warningsArea     = document.getElementById('parsing-warnings-area');

  if (!errorCard) return;

  /* ── SVG 아이콘 ── */
  var STATE_ICONS = {
    api: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    network: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 1l22 22"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>',
    timeout: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    parse: '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>',
    warning: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>',
    info: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/></svg>',
    reviewRequired: '<svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>',
    checkCircle: '<svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.06l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/></svg>'
  };

  /* ── 에러 타입 자동 판별 ── */
  var ERROR_TYPES = {
    NETWORK_ERROR: 'network',
    TIMEOUT: 'timeout',
    PARSE_FAILED: 'parse',
    SERVER_ERROR: 'api',
    INVALID_RESPONSE: 'api',
    FILE_TOO_LARGE: 'api',
    UNSUPPORTED_FILE: 'api'
  };

  /* 타이머 */
  var retryTimer = null;
  var countdownTimer = null;
  var retryCallback = null;

  /* ============================================================
     에러 타입 감지 (제목 기반)
     ============================================================ */
  function detectErrorType(title) {
    if (!title) return 'api';
    if (title.indexOf('네트워크') !== -1) return 'network';
    if (title.indexOf('시간 초과') !== -1 || title.indexOf('타임아웃') !== -1) return 'timeout';
    if (title.indexOf('PDF 분석') !== -1 || title.indexOf('파싱') !== -1) return 'parse';
    return 'api';
  }

  /* ============================================================
     에러 상태 화면 표시
     @param {string} title – 에러 제목
     @param {string} desc  – 에러 설명
     @param {Object} [opts]
       .errorCode    – 에러 코드 표시 (예: 'ERR_NETWORK')
       .type         – 강제 에러 타입 (api | network | timeout | parse)
       .autoRetry    – 자동 재시도 활성화 (network 에러 시)
       .retryDelay   – 자동 재시도 딜레이 (ms, 기본 5000)
       .onRetry      – 재시도 콜백
       .onReupload   – 다른 파일 업로드 콜백
     ============================================================ */
  function showErrorState(title, desc, opts) {
    opts = opts || {};

    clearAutoRetry();

    var type = opts.type || detectErrorType(title);

    /* 카드 클래스 변경 */
    errorInner.className = 'state-error is-' + type;

    /* 아이콘 변경 */
    errorIcon.innerHTML = STATE_ICONS[type] || STATE_ICONS.api;

    /* 텍스트 변경 */
    errorTitle.textContent = title;
    errorDesc.textContent = desc;

    /* 에러 코드 */
    if (opts.errorCode) {
      errorCode.hidden = false;
      errorCodeText.textContent = opts.errorCode;
    } else {
      errorCode.hidden = true;
    }

    /* 콜백 저장 */
    retryCallback = opts.onRetry || null;

    /* 카드 표시 */
    errorCard.hidden = false;
    errorCard.classList.remove('is-visible');
    void errorCard.offsetHeight;
    errorCard.classList.add('is-visible');

    /* 접근성: 에러 카드로 포커스 이동 */
    errorCard.setAttribute('tabindex', '-1');
    errorCard.focus();

    /* 네트워크 에러 시 자동 재시도 */
    if (type === 'network' && opts.autoRetry && retryCallback) {
      startAutoRetry(opts.retryDelay || 5000);
    } else {
      retryCountdown.hidden = true;
    }
  }

  /* ============================================================
     에러 상태 숨기기
     ============================================================ */
  function hideErrorState() {
    clearAutoRetry();
    errorCard.hidden = true;
    errorCard.classList.remove('is-visible');
  }

  /* ============================================================
     자동 재시도 카운트다운 (네트워크 오류)
     ============================================================ */
  function startAutoRetry(delay) {
    var remaining = Math.ceil(delay / 1000);
    retryCountdown.hidden = false;
    retryCountText.textContent = '자동 재시도까지 ' + remaining + '초...';

    countdownTimer = setInterval(function () {
      remaining--;
      if (remaining > 0) {
        retryCountText.textContent = '자동 재시도까지 ' + remaining + '초...';
      } else {
        clearAutoRetry();
        if (retryCallback) {
          retryCallback();
        }
      }
    }, 1000);
  }

  function clearAutoRetry() {
    if (countdownTimer) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    if (retryCountdown) retryCountdown.hidden = true;
  }

  /* ── 재시도 버튼 클릭 ── */
  if (errorRetryBtn) {
    errorRetryBtn.addEventListener('click', function () {
      clearAutoRetry();
      if (retryCallback) {
        retryCallback();
      }
    });
  }

  /* ── 다른 파일 업로드 버튼 → 업로드 화면으로 돌아가기 ── */
  if (errorReuploadBtn) {
    errorReuploadBtn.addEventListener('click', function () {
      clearAutoRetry();
      hideErrorState();
      /* 업로드 카드 복원 */
      var uploadCard = document.querySelector('.upload-card');
      if (uploadCard) uploadCard.hidden = false;
    });
  }

  /* ============================================================
     파싱 경고 배너 표시
     PDF 파싱 중 일부 항목 추출 실패 시 표시

     @param {Array} warnings – 경고 메시지 배열
       각 항목: { field: '사업기간', message: '추출 실패' }
     ============================================================ */
  function showParsingWarnings(warnings) {
    if (!warningsArea || !warnings || warnings.length === 0) return;

    var html = '<div class="parsing-warning" role="alert" aria-live="polite">';
    html += '<div class="parsing-warning-icon">' + STATE_ICONS.warning + '</div>';
    html += '<div class="parsing-warning-body">';
    html += '<p class="parsing-warning-title">일부 항목을 추출하지 못했습니다</p>';
    html += '<p class="parsing-warning-desc">다음 항목의 추출 결과가 불완전하거나 누락되었습니다. 해당 항목은 수동으로 확인해주세요.</p>';
    html += '<ul class="parsing-warning-list">';
    for (var i = 0; i < warnings.length; i++) {
      var w = warnings[i];
      html += '<li><strong>' + escapeHtml(w.field) + '</strong>: ' + escapeHtml(w.message) + '</li>';
    }
    html += '</ul>';
    html += '</div>';
    html += '<button type="button" class="parsing-warning-close" aria-label="경고 닫기">';
    html += '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>';
    html += '</button>';
    html += '</div>';

    warningsArea.innerHTML = html;
    warningsArea.hidden = false;

    /* 닫기 버튼 */
    var closeBtn = warningsArea.querySelector('.parsing-warning-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        hideParsingWarnings();
      });
    }
  }

  function hideParsingWarnings() {
    if (warningsArea) {
      warningsArea.hidden = true;
      warningsArea.innerHTML = '';
    }
  }

  /* ============================================================
     탭 패널 내부 파싱 알림 (경고/에러/정보)
     특정 탭의 데이터 추출 실패 시 탭 내부에 표시

     @param {string} tabKey   – 탭 키 (overview | requirements | scoring | toc)
     @param {string} type     – 알림 타입 (warning | error | info)
     @param {string} message  – 알림 메시지
     ============================================================ */
  function showTabAlert(tabKey, type, message) {
    var contentEl = document.getElementById('tabpanel-' + tabKey + '-content');
    if (!contentEl) return;

    /* 기존 알림 제거 */
    var existing = contentEl.querySelector('.parsing-alert');
    if (existing) existing.parentNode.removeChild(existing);

    var iconSvg = type === 'warning' ? STATE_ICONS.warning
                : type === 'error'   ? STATE_ICONS.api
                :                      STATE_ICONS.info;

    var alertHtml = '<div class="parsing-alert is-' + type + '" role="alert">' +
      '<div class="parsing-alert-icon">' + iconSvg + '</div>' +
      '<span class="parsing-alert-text">' + escapeHtml(message) + '</span>' +
      '</div>';

    contentEl.insertAdjacentHTML('afterbegin', alertHtml);
  }

  /* ============================================================
     신뢰도 배지 생성
     @param {number} score – 0~100 신뢰도 점수
     @returns {string} HTML
     ============================================================ */
  function buildConfidenceBadge(score) {
    var level, label, icon;

    if (score >= 80) {
      level = 'high';
      label = '신뢰';
      icon = STATE_ICONS.checkCircle;
    } else if (score >= 60) {
      level = 'medium';
      label = '보통';
      icon = STATE_ICONS.info;
    } else if (score >= 40) {
      level = 'low';
      label = '검토 필요';
      icon = STATE_ICONS.reviewRequired;
    } else {
      level = 'critical';
      label = '검토 필수';
      icon = STATE_ICONS.reviewRequired;
    }

    return '<span class="confidence-badge is-' + level + '" title="신뢰도 ' + score + '%">' +
      icon + ' ' + escapeHtml(label) +
      '</span>';
  }

  /* ============================================================
     파싱 결과 분석 – 누락/불완전 항목 자동 감지
     @param {Object} normalized – 정규화된 API 응답
     @returns {Object} { warnings: Array, fieldScores: Object }
     ============================================================ */
  function analyzeParsingQuality(normalized) {
    var warnings = [];
    var fieldScores = {};

    /* 사업개요 필수 필드 검사 */
    if (normalized.overview) {
      var ov = normalized.overview;
      var overviewFields = {
        projectName:    { label: '사업명',     weight: 100 },
        organization:   { label: '발주기관',    weight: 90 },
        period:         { label: '사업기간',    weight: 80 },
        budget:         { label: '사업비(예산)', weight: 85 },
        contractType:   { label: '입찰방식',    weight: 70 },
        contractMethod: { label: '계약방식',    weight: 70 },
        qualifications: { label: '참가자격',    weight: 60 },
        location:       { label: '수행장소',    weight: 50 },
        purpose:        { label: '사업 목적',   weight: 75 }
      };

      for (var key in overviewFields) {
        var val = ov[key];
        var meta = overviewFields[key];

        if (!val || (typeof val === 'string' && val.trim() === '')) {
          warnings.push({ field: meta.label, message: '값을 추출하지 못했습니다' });
          fieldScores[key] = 0;
        } else if (typeof val === 'string' && val.length < 3) {
          fieldScores[key] = 40;
        } else {
          fieldScores[key] = meta.weight;
        }
      }
    } else {
      warnings.push({ field: '사업개요', message: '전체 섹션을 추출하지 못했습니다' });
    }

    /* 요구사항 검사 */
    if (!normalized.requirements || normalized.requirements.length === 0) {
      warnings.push({ field: '요구사항', message: '요구사항을 추출하지 못했습니다' });
    } else {
      /* 개별 요구사항 품질 체크 */
      var noDescCount = 0;
      var noIdCount = 0;
      for (var r = 0; r < normalized.requirements.length; r++) {
        var req = normalized.requirements[r];
        if (!req.desc || req.desc.trim() === '') noDescCount++;
        if (!req.id || req.id.trim() === '') noIdCount++;
      }
      if (noDescCount > 0) {
        warnings.push({
          field: '요구사항 상세설명',
          message: noDescCount + '건의 상세설명이 누락되었습니다'
        });
      }
      if (noIdCount > 0) {
        warnings.push({
          field: '요구사항 ID',
          message: noIdCount + '건의 ID가 누락되었습니다'
        });
      }
    }

    /* 배점기준 검사 */
    if (!normalized.scoring || normalized.scoring.length === 0) {
      warnings.push({ field: '배점기준', message: '배점기준을 추출하지 못했습니다' });
    }

    /* 제안목차 검사 */
    if (!normalized.toc || normalized.toc.length === 0) {
      warnings.push({ field: '제안목차', message: '제안목차를 추출하지 못했습니다' });
    }

    return {
      warnings: warnings,
      fieldScores: fieldScores
    };
  }

  /* ============================================================
     빈 탭 상태를 풍부한 일러스트로 업그레이드
     분석 후 데이터가 없는 탭에 개선된 빈 상태 표시

     @param {string} tabKey – 탭 키
     @param {Object} config – { icon, badgeIcon, title, desc }
     ============================================================ */
  var EMPTY_STATE_CONFIGS = {
    overview: {
      icon: '<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
      badgeIcon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
      title: '사업개요를 추출하지 못했습니다',
      desc: 'PDF 문서에서 사업 목적, 범위, 예산 등의 기본 정보를 찾을 수 없습니다. 문서 형식을 확인하거나 다른 RFP를 업로드해주세요.'
    },
    requirements: {
      icon: '<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
      badgeIcon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
      title: '요구사항을 추출하지 못했습니다',
      desc: 'PDF 문서에서 기능/비기능 요구사항 목록을 찾을 수 없습니다. RFP 문서에 요구사항 섹션이 포함되어 있는지 확인해주세요.'
    },
    scoring: {
      icon: '<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
      badgeIcon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
      title: '배점기준을 추출하지 못했습니다',
      desc: '평가 항목별 배점과 기준을 찾을 수 없습니다. RFP에 평가기준표가 포함되어 있는지 확인해주세요.'
    },
    toc: {
      icon: '<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
      badgeIcon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
      title: '제안서 목차를 구성해주세요',
      desc: '표준 템플릿을 선택하거나, 직접 목차를 작성할 수 있습니다. 목차 탭에서 편집을 시작하세요.'
    }
  };

  function upgradeEmptyState(tabKey) {
    var emptyEl = document.getElementById('tabpanel-' + tabKey + '-empty');
    if (!emptyEl) return;

    /* 이미 hidden이면 데이터가 있는 탭이므로 스킵 */
    if (emptyEl.hidden) return;

    var cfg = EMPTY_STATE_CONFIGS[tabKey];
    if (!cfg) return;

    var html = '<div class="state-empty">' +
      '<div class="state-empty-illustration">' +
        '<div class="state-empty-illustration-bg"></div>' +
        '<div class="state-empty-illustration-icon">' + cfg.icon + '</div>' +
        '<div class="state-empty-illustration-badge">' + cfg.badgeIcon + '</div>' +
      '</div>' +
      '<h4 class="state-empty-title">' + cfg.title + '</h4>' +
      '<p class="state-empty-desc">' + cfg.desc + '</p>' +
      '</div>';

    emptyEl.innerHTML = html;
  }

  /* ============================================================
     HTML 이스케이프
     ============================================================ */
  /* escapeHtml·esc·toast → util.js 전역 사용 */

  /* ============================================================
     전역 API 노출
     ============================================================ */
  window.StateUI = {
    showErrorState:        showErrorState,
    hideErrorState:        hideErrorState,
    showParsingWarnings:   showParsingWarnings,
    hideParsingWarnings:   hideParsingWarnings,
    showTabAlert:          showTabAlert,
    buildConfidenceBadge:  buildConfidenceBadge,
    analyzeParsingQuality: analyzeParsingQuality,
    upgradeEmptyState:     upgradeEmptyState
  };

})();
