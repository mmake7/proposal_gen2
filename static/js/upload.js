/* ============================================================
   RFP PDF Upload – Drag & Drop + File Validation + KRDS UX
   ============================================================ */
(function () {
  'use strict';

  /* ── DOM 요소 캐시 ── */
  var dropzone    = document.getElementById('upload-dropzone');
  var fileInput   = document.getElementById('upload-input');
  var prompt      = document.getElementById('upload-prompt');
  var preview     = document.getElementById('upload-preview');
  var fileName    = document.getElementById('upload-file-name');
  var fileSize    = document.getElementById('upload-file-size');
  var removeBtn   = document.getElementById('upload-remove-btn');
  var reselectBtn = document.getElementById('upload-reselect-btn');
  var analyzeBtn  = document.getElementById('upload-analyze-btn');
  var dragOverlay = document.getElementById('upload-drag-overlay');

  /* 메시지 영역 */
  var messageEl      = document.getElementById('upload-message');
  var messageIcon    = document.getElementById('upload-message-icon');
  var messageTitle   = document.getElementById('upload-message-title');
  var messageDesc    = document.getElementById('upload-message-desc');
  var messageClose   = document.getElementById('upload-message-close');

  if (!dropzone || !fileInput) return;

  /* ── 설정 ── */
  var MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB
  var ALLOWED_EXTENSIONS = ['.pdf'];
  var ALLOWED_MIME = 'application/pdf';
  var MESSAGE_AUTO_DISMISS_MS = 6000;

  var messageDismissTimer = null;

  /* ── SVG 아이콘 템플릿 ── */
  var ICONS = {
    error: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/></svg>',
    warning: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>',
    success: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.06l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/></svg>',
    info: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/></svg>'
  };

  /* ============================================================
     메시지 표시 시스템 (KRDS 인라인 알림)
     ============================================================ */
  function showMessage(type, title, desc) {
    /* 기존 타이머 정리 */
    if (messageDismissTimer) {
      clearTimeout(messageDismissTimer);
      messageDismissTimer = null;
    }

    /* 클래스 초기화 후 타입 적용 */
    messageEl.className = 'upload-message is-' + type;
    messageEl.hidden = false;
    messageIcon.innerHTML = ICONS[type] || '';
    messageTitle.textContent = title;
    messageDesc.textContent = desc || '';
    if (!desc) {
      messageDesc.hidden = true;
    } else {
      messageDesc.hidden = false;
    }

    /* 에러가 아니면 자동 dismiss */
    if (type !== 'error') {
      messageDismissTimer = setTimeout(dismissMessage, MESSAGE_AUTO_DISMISS_MS);
    }
  }

  function dismissMessage() {
    if (messageDismissTimer) {
      clearTimeout(messageDismissTimer);
      messageDismissTimer = null;
    }
    messageEl.hidden = true;
    messageEl.className = 'upload-message';
  }

  if (messageClose) {
    messageClose.addEventListener('click', dismissMessage);
  }

  /* ============================================================
     파일 유효성 검사
     ============================================================ */
  function getFileExtension(name) {
    var idx = name.lastIndexOf('.');
    return idx >= 0 ? name.slice(idx).toLowerCase() : '';
  }

  function validateFile(file) {
    if (!file) return { valid: false, code: 'NO_FILE' };

    /* 1) 확장자 검사 */
    var ext = getFileExtension(file.name);
    if (ALLOWED_EXTENSIONS.indexOf(ext) === -1) {
      return {
        valid: false,
        code: 'INVALID_TYPE',
        title: '허용되지 않는 파일 형식입니다',
        desc: '"' + ext + '" 파일은 업로드할 수 없습니다. PDF(.pdf) 파일만 허용됩니다.'
      };
    }

    /* 2) MIME 타입 검사 (브라우저가 제공하는 경우) */
    if (file.type && file.type !== ALLOWED_MIME) {
      return {
        valid: false,
        code: 'INVALID_MIME',
        title: '올바른 PDF 파일이 아닙니다',
        desc: '파일 형식이 "' + file.type + '"(으)로 감지되었습니다. 유효한 PDF 파일을 선택해주세요.'
      };
    }

    /* 3) 파일 크기 검사 */
    if (file.size > MAX_FILE_SIZE) {
      return {
        valid: false,
        code: 'TOO_LARGE',
        title: '파일 크기가 제한을 초과합니다',
        desc: '현재 파일 크기: ' + formatSize(file.size) + '. 최대 허용 크기는 50MB입니다.'
      };
    }

    /* 4) 빈 파일 검사 */
    if (file.size === 0) {
      return {
        valid: false,
        code: 'EMPTY_FILE',
        title: '빈 파일입니다',
        desc: '내용이 없는 파일은 업로드할 수 없습니다. 유효한 PDF 파일을 선택해주세요.'
      };
    }

    return { valid: true };
  }

  /* ── 파일 크기 포맷 ── */
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  /* ============================================================
     파일 설정 / 제거
     ============================================================ */
  function setFile(file) {
    if (!file) return;

    var result = validateFile(file);

    if (!result.valid) {
      showMessage('error', result.title, result.desc);
      flashError();
      return;
    }

    /* 검증 통과 — 메시지 초기화 후 성공 알림 */
    dismissMessage();

    fileName.textContent = file.name;
    fileSize.textContent = formatSize(file.size);

    prompt.hidden  = true;
    preview.hidden = false;
    dropzone.classList.add('has-file');
    analyzeBtn.disabled = false;
    analyzeBtn.setAttribute('aria-disabled', 'false');

    showMessage('success', '파일이 선택되었습니다', file.name + ' (' + formatSize(file.size) + ')');
  }

  function clearFile() {
    fileInput.value = '';
    prompt.hidden  = false;
    preview.hidden = true;
    dropzone.classList.remove('has-file');
    analyzeBtn.disabled = true;
    analyzeBtn.setAttribute('aria-disabled', 'true');
    fileName.textContent = '';
    fileSize.textContent = '';
    dismissMessage();
  }

  /* 에러 시 드롭존 깜빡임 */
  function flashError() {
    dropzone.classList.add('is-error');
    setTimeout(function () {
      dropzone.classList.remove('is-error');
    }, 600);
  }

  /* ============================================================
     클릭 / 키보드 파일 선택
     ============================================================ */
  dropzone.addEventListener('click', function (e) {
    if (e.target.closest('.upload-preview-remove') || e.target.closest('#upload-reselect-btn')) return;
    if (!dropzone.classList.contains('has-file')) {
      fileInput.click();
    }
  });

  dropzone.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && !dropzone.classList.contains('has-file')) {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener('change', function () {
    if (fileInput.files && fileInput.files[0]) {
      setFile(fileInput.files[0]);
    }
  });

  /* ============================================================
     드래그 앤 드롭
     ============================================================ */
  var dragCounter = 0;

  dropzone.addEventListener('dragenter', function (e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter++;
    if (!dropzone.classList.contains('has-file')) {
      dropzone.classList.add('is-dragover');
    }
  });

  dropzone.addEventListener('dragleave', function (e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter--;
    if (dragCounter === 0) {
      dropzone.classList.remove('is-dragover');
    }
  });

  dropzone.addEventListener('dragover', function (e) {
    e.preventDefault();
    e.stopPropagation();
  });

  dropzone.addEventListener('drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    dragCounter = 0;
    dropzone.classList.remove('is-dragover');

    var files = e.dataTransfer && e.dataTransfer.files;
    if (!files || files.length === 0) return;

    /* 다중 파일 드롭 시 경고 */
    if (files.length > 1) {
      showMessage('warning', '한 번에 하나의 파일만 업로드할 수 있습니다', '첫 번째 파일만 처리됩니다. 나머지 ' + (files.length - 1) + '개 파일은 무시됩니다.');
    }

    setFile(files[0]);
  });

  /* ============================================================
     파일 제거 / 재선택
     ============================================================ */
  removeBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    clearFile();
  });

  if (reselectBtn) {
    reselectBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      clearFile();
      fileInput.click();
    });
  }

  /* ============================================================
     분석 진행률 표시
     ============================================================ */
  var uploadCardEl     = document.querySelector('.upload-card');
  var progressCard     = document.getElementById('analysis-progress');
  var resultCard       = document.getElementById('analysis-result');
  var analysisFileName = document.getElementById('analysis-file-name');
  var barFill          = document.getElementById('analysis-bar-fill');
  var barEl            = document.getElementById('analysis-bar');
  var percentEl        = document.getElementById('analysis-percent');
  var analysisSteps    = document.querySelectorAll('.analysis-step');
  var retryBtn         = document.getElementById('analysis-retry-btn');

  /* 현재 API 요청 핸들 (abort 가능) */
  var currentRequest = null;

  /* 진행률 애니메이션용 타이머 */
  var progressTimer = null;
  var currentPct = 0;

  analyzeBtn.addEventListener('click', function () {
    if (analyzeBtn.disabled) return;
    startAnalysis();
  });

  function startAnalysis() {
    dismissMessage();

    var file = fileInput.files && fileInput.files[0];
    if (!file) {
      showMessage('error', '파일을 선택해주세요', 'PDF 파일을 업로드한 후 분석을 시작해주세요.');
      return;
    }

    /* 에러 상태 / 경고 숨기기 */
    var analysisErrorCard = document.getElementById('analysis-error');
    if (analysisErrorCard) {
      analysisErrorCard.hidden = true;
      analysisErrorCard.classList.remove('is-visible');
    }
    if (typeof window.StateUI !== 'undefined') {
      window.StateUI.hideErrorState();
      window.StateUI.hideParsingWarnings();
    }

    /* UI 전환: 업로드 카드 → 진행률 카드 */
    uploadCardEl.hidden = true;
    resultCard.hidden = true;
    progressCard.hidden = false;
    progressCard.classList.remove('is-visible');
    void progressCard.offsetHeight;
    progressCard.classList.add('is-visible');

    /* 접근성: 진행 카드로 포커스 이동 (스크린 리더 알림) */
    progressCard.setAttribute('tabindex', '-1');
    progressCard.focus();

    analysisFileName.textContent = fileName.textContent;

    /* 상태 초기화 */
    barFill.style.width = '0%';
    barFill.classList.remove('is-complete');
    percentEl.textContent = '0%';
    if (barEl) barEl.setAttribute('aria-valuenow', '0');

    for (var i = 0; i < analysisSteps.length; i++) {
      analysisSteps[i].className = 'analysis-step is-pending';
    }

    currentPct = 0;

    /* ApiClient가 로드되지 않았을 경우 에러 */
    if (typeof window.ApiClient === 'undefined') {
      handleAnalysisError('시스템 오류', 'API 클라이언트가 로드되지 않았습니다. 페이지를 새로고침해주세요.');
      return;
    }

    /* Flask API 호출 */
    currentRequest = window.ApiClient.parseRfp(file, {
      onUploadProgress: function (loaded, total) {
        /* 업로드 진행률 → 0~20% */
        var uploadPct = Math.round((loaded / total) * 20);
        updateProgressBar(uploadPct);
      },

      onProgress: function (stepIndex) {
        /* 단계 진행 표시 */
        activateStep(stepIndex);
      },

      onSuccess: function (data) {
        currentRequest = null;
        stopProgressAnimation();

        /* 모든 단계 완료 표시 */
        for (var i = 0; i < analysisSteps.length; i++) {
          analysisSteps[i].className = 'analysis-step is-done';
        }
        updateProgressBar(100);
        barFill.classList.add('is-complete');

        /* 응답 정규화 */
        var normalized = window.ApiClient.normalizeResponse(data);

        setTimeout(function () {
          progressCard.hidden = true;
          progressCard.classList.remove('is-visible');

          populateResult(normalized);

          resultCard.hidden = false;
          resultCard.classList.remove('is-visible');
          void resultCard.offsetHeight;
          resultCard.classList.add('is-visible');

          /* 접근성: 결과 카드로 포커스 이동 */
          resultCard.setAttribute('tabindex', '-1');
          resultCard.focus();
        }, 800);
      },

      onError: function (title, desc) {
        currentRequest = null;
        handleAnalysisError(title, desc);
      }
    });

    /* 서버 분석 대기 중 진행률 애니메이션 시작 (20% ~ 90%) */
    activateStep(0);
    startProgressAnimation();
  }

  /* ── 진행률 애니메이션 (서버 응답 대기 중) ── */
  function startProgressAnimation() {
    var stepThresholds = [20, 45, 70, 90];
    var currentStepIdx = 0;

    progressTimer = setInterval(function () {
      if (currentPct >= 90) {
        clearInterval(progressTimer);
        progressTimer = null;
        return;
      }

      currentPct += 1;
      updateProgressBar(currentPct);

      /* 단계 전환 */
      if (currentStepIdx < stepThresholds.length - 1 &&
          currentPct >= stepThresholds[currentStepIdx + 1]) {
        currentStepIdx++;
        activateStep(currentStepIdx);
      }
    }, 800);
  }

  function stopProgressAnimation() {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  /* ── 단계 활성화 ── */
  function activateStep(stepIndex) {
    for (var i = 0; i < analysisSteps.length; i++) {
      if (i < stepIndex) {
        analysisSteps[i].className = 'analysis-step is-done';
      } else if (i === stepIndex) {
        analysisSteps[i].className = 'analysis-step is-active';
      } else {
        analysisSteps[i].className = 'analysis-step is-pending';
      }
    }
  }

  /* ── 분석 에러 처리 ── */
  function handleAnalysisError(title, desc) {
    stopProgressAnimation();

    progressCard.hidden = true;
    progressCard.classList.remove('is-visible');

    /* StateUI 에러 화면 사용 (있으면) */
    if (typeof window.StateUI !== 'undefined') {
      var analysisErrorCard = document.getElementById('analysis-error');
      uploadCardEl.hidden = true;

      window.StateUI.showErrorState(title, desc, {
        autoRetry: title.indexOf('네트워크') !== -1,
        retryDelay: 5000,
        onRetry: function () {
          if (analysisErrorCard) {
            analysisErrorCard.hidden = true;
            analysisErrorCard.classList.remove('is-visible');
          }
          window.StateUI.hideErrorState();
          startAnalysis();
        },
        onReupload: function () {
          if (analysisErrorCard) {
            analysisErrorCard.hidden = true;
            analysisErrorCard.classList.remove('is-visible');
          }
          window.StateUI.hideErrorState();
          uploadCardEl.hidden = false;
        }
      });
    } else {
      /* 폴백: 기존 인라인 메시지 */
      uploadCardEl.hidden = false;
      showMessage('error', title, desc);
    }

    /* 토스트로도 표시 */
    if (typeof window.showToast === 'function') {
      window.showToast('error', title, desc);
    }
  }

  function updateProgressBar(pct) {
    currentPct = pct;
    barFill.style.width = pct + '%';
    percentEl.textContent = pct + '%';
    if (barEl) barEl.setAttribute('aria-valuenow', String(pct));
  }

  function populateResult(apiData) {
    var overview     = apiData.overview;
    var requirements = apiData.requirements || [];
    var scoring      = apiData.scoring || [];
    var toc          = apiData.toc || [];

    /* 결과 요약 카드 채우기 */
    var summaryData = {
      'result-project-name': overview ? overview.projectName : '(프로젝트명 없음)',
      'result-org-name':     overview ? overview.organization : '(발주기관 없음)',
      'result-req-count':    requirements.length + '건',
      'result-toc-count':    toc.length + '개 항목'
    };
    for (var id in summaryData) {
      var el = document.getElementById(id);
      if (el) el.textContent = summaryData[id];
    }

    /* 파싱 품질 분석 (StateUI가 있을 때) */
    var qualityResult = null;
    if (typeof window.StateUI !== 'undefined') {
      qualityResult = window.StateUI.analyzeParsingQuality(apiData);

      /* 파싱 경고 표시 */
      if (qualityResult.warnings.length > 0) {
        window.StateUI.showParsingWarnings(qualityResult.warnings);
      }

      /* 빈 탭 상태 업그레이드 */
      var tabKeys = ['overview', 'requirements', 'scoring', 'toc'];
      for (var t = 0; t < tabKeys.length; t++) {
        window.StateUI.upgradeEmptyState(tabKeys[t]);
      }
    }

    /* 사업개요 탭 콘텐츠 채우기 */
    populateOverviewTab(overview, qualityResult ? qualityResult.fieldScores : null);

    /* 요구사항 탭 콘텐츠 채우기 */
    populateRequirementsTab(requirements);

    /* 배점기준 탭 콘텐츠 채우기 */
    populateScoringTab(scoring);

    /* 제안목차 탭 콘텐츠 채우기 */
    populateTocTab(toc);

    /* 빈 탭에 경고 알림 표시 */
    if (typeof window.StateUI !== 'undefined') {
      if (!overview) {
        window.StateUI.showTabAlert('overview', 'error', '사업개요 데이터를 추출하지 못했습니다. PDF 문서의 형식을 확인해주세요.');
      }
      if (requirements.length === 0) {
        window.StateUI.showTabAlert('requirements', 'warning', '요구사항을 추출하지 못했습니다. RFP에 요구사항 섹션이 포함되어 있는지 확인해주세요.');
      }
      if (scoring.length === 0) {
        window.StateUI.showTabAlert('scoring', 'warning', '배점기준을 추출하지 못했습니다. 평가기준표가 포함된 PDF인지 확인해주세요.');
      }
      if (toc.length === 0) {
        window.StateUI.showTabAlert('toc', 'info', '제안목차를 자동 생성하지 못했습니다. 요구사항 분석 후 수동으로 구성할 수 있습니다.');
      }
    }

    /* 탭 배지 카운트 업데이트 */
    if (typeof window.updateTabBadge === 'function') {
      var overviewFieldCount = overview ? Object.keys(overview).filter(function (k) { return overview[k]; }).length : 0;
      window.updateTabBadge('overview', overviewFieldCount);
      window.updateTabBadge('requirements', requirements.length);
      window.updateTabBadge('scoring', scoring.length);
      window.updateTabBadge('toc', toc.length);
    }

    /* 탭 카드 표시 */
    if (typeof window.showAnalysisTabs === 'function') {
      window.showAnalysisTabs();
    }
  }

  /* ============================================================
     사업개요 탭 콘텐츠 렌더링
     ============================================================ */
  function populateOverviewTab(overview, fieldScores) {
    var overviewContent = document.getElementById('tabpanel-overview-content');
    var overviewEmpty   = document.getElementById('tabpanel-overview-empty');
    if (!overviewContent) return;

    /* 데이터가 없으면 빈 상태 표시 */
    if (!overview) {
      if (overviewEmpty) overviewEmpty.hidden = false;
      return;
    }

    /* 신뢰도 배지 헬퍼 */
    var hasBadge = fieldScores && typeof window.StateUI !== 'undefined';
    function badge(fieldKey) {
      if (!hasBadge || fieldScores[fieldKey] === undefined) return '';
      if (fieldScores[fieldKey] >= 60) return '';
      return ' ' + window.StateUI.buildConfidenceBadge(fieldScores[fieldKey]);
    }

    /* 사업명 헤더 */
    var html = '' +
      '<div class="overview-header">' +
        '<div class="overview-header-icon" aria-hidden="true">' +
          '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>' +
            '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>' +
          '</svg>' +
        '</div>' +
        '<div class="overview-header-body">' +
          '<p class="overview-header-label">사업명' + badge('projectName') + '</p>' +
          '<p class="overview-header-value">' + escapeHtml(overview.projectName) + '</p>' +
        '</div>' +
      '</div>';

    /* 정보 테이블 */
    html += '<div class="overview-info-table">';
    html += buildInfoRow('발주기관', escapeHtml(overview.organization) + badge('organization'));
    html += buildInfoRow('사업기간', escapeHtml(overview.period) + badge('period'));
    html += buildInfoRow('사업비(예산)',
      '<span class="overview-budget-badge">' +
        '<span class="overview-budget-amount">' + escapeHtml(overview.budget) + '</span>' +
        '<span class="overview-budget-unit">' + escapeHtml(overview.budgetUnit) + '</span>' +
      '</span>' + badge('budget'),
      true
    );
    html += buildInfoRow('입찰방식',
      '<span class="overview-tag is-blue">' + escapeHtml(overview.contractType) + '</span>' + badge('contractType')
    );
    html += buildInfoRow('계약방식',
      '<span class="overview-tag is-green">' + escapeHtml(overview.contractMethod) + '</span>' + badge('contractMethod')
    );
    html += buildInfoRow('참가자격', escapeHtml(overview.qualifications) + badge('qualifications'));
    html += buildInfoRow('수행장소', escapeHtml(overview.location) + badge('location'));
    html += '</div>';

    /* 사업 목적 */
    html += '' +
      '<div class="overview-desc-section">' +
        '<h4 class="overview-desc-title">사업 목적' + badge('purpose') + '</h4>' +
        '<div class="overview-desc-body">' +
          '<p>' + escapeHtml(overview.purpose) + '</p>' +
        '</div>' +
      '</div>';

    overviewContent.innerHTML = html;

    /* 빈 상태 숨기기 */
    if (overviewEmpty) overviewEmpty.hidden = true;
  }

  function buildInfoRow(label, valueHtml, isHighlight) {
    return '' +
      '<div class="overview-info-row">' +
        '<div class="overview-info-label">' + escapeHtml(label) + '</div>' +
        '<div class="overview-info-value' + (isHighlight ? ' is-highlight' : '') + '">' +
          valueHtml +
        '</div>' +
      '</div>';
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* ============================================================
     요구사항 탭 콘텐츠 렌더링
     ============================================================ */
  function populateRequirementsTab(requirements) {
    var reqContent = document.getElementById('tabpanel-requirements-content');
    var reqEmpty   = document.getElementById('tabpanel-requirements-empty');
    if (!reqContent) return;

    /* 데이터가 없거나 빈 배열이면 빈 상태 표시 */
    if (!requirements || requirements.length === 0) {
      if (reqEmpty) reqEmpty.hidden = false;
      return;
    }

    /* 분류 → CSS 클래스 매핑 */
    var categoryClassMap = {
      '기능': 'is-func',
      '비기능': 'is-nonfunc',
      '성능': 'is-perf',
      '보안': 'is-security',
      '데이터': 'is-data',
      '인터페이스': 'is-interface'
    };

    /* 분류 목록 추출 */
    var categories = [];
    for (var i = 0; i < requirements.length; i++) {
      if (categories.indexOf(requirements[i].category) === -1) {
        categories.push(requirements[i].category);
      }
    }

    /* 통계 계산 */
    var mandatoryCount = 0;
    var optionalCount = 0;
    for (var s = 0; s < requirements.length; s++) {
      if (requirements[s].level === '필수') mandatoryCount++;
      else optionalCount++;
    }

    /* ── 툴바 HTML ── */
    var html = '<div class="req-toolbar">';
    html += '<div class="req-filter-group">';
    html += '<span class="req-filter-label">분류</span>';
    html += '<select class="req-filter-select" id="req-category-filter" aria-label="분류 필터">';
    html += '<option value="all">전체 (' + requirements.length + ')</option>';
    for (var c = 0; c < categories.length; c++) {
      var catCount = 0;
      for (var cc = 0; cc < requirements.length; cc++) {
        if (requirements[cc].category === categories[c]) catCount++;
      }
      html += '<option value="' + escapeHtml(categories[c]) + '">' + escapeHtml(categories[c]) + ' (' + catCount + ')</option>';
    }
    html += '</select>';
    html += '</div>';
    html += '<div class="req-search-box">';
    html += '<input type="text" class="req-search-input" id="req-search-input" placeholder="ID 또는 요구사항명 검색" aria-label="요구사항 검색">';
    html += '</div>';
    html += '</div>';

    /* ── 통계 요약 ── */
    html += '<div class="req-summary">';
    html += '<span class="req-summary-item">전체 <span class="req-summary-count">' + requirements.length + '</span>건</span>';
    html += '<span class="req-summary-item"><span class="req-summary-dot is-mandatory"></span> 필수 <span class="req-summary-count">' + mandatoryCount + '</span></span>';
    html += '<span class="req-summary-item"><span class="req-summary-dot is-optional"></span> 선택 <span class="req-summary-count">' + optionalCount + '</span></span>';
    html += '<span class="req-summary-item" id="req-filtered-count" hidden>검색 결과: <span class="req-summary-count" id="req-filtered-num">0</span>건</span>';
    html += '</div>';

    /* ── 테이블 ── */
    html += '<div class="req-table-wrap">';
    html += '<table class="req-table" id="req-table">';
    html += '<caption class="sr-only">RFP 요구사항 목록 – 총 ' + requirements.length + '건</caption>';
    html += '<thead><tr>';
    html += '<th scope="col" class="req-col-category">분류</th>';
    html += '<th scope="col" class="req-col-id">ID</th>';
    html += '<th scope="col" class="req-col-name">요구사항명</th>';
    html += '<th scope="col" class="req-col-desc">상세설명</th>';
    html += '<th scope="col" class="req-col-level">응낙수준</th>';
    html += '</tr></thead>';
    html += '<tbody id="req-table-body">';
    for (var r = 0; r < requirements.length; r++) {
      html += buildReqRow(requirements[r], categoryClassMap);
    }
    html += '</tbody>';
    html += '</table>';
    html += '</div>';

    /* ── 검색 결과 없음 ── */
    html += '<div class="req-empty-result" id="req-empty-result" hidden>';
    html += '<svg class="req-empty-result-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
    html += '<p class="req-empty-result-text">검색 결과가 없습니다</p>';
    html += '</div>';

    reqContent.innerHTML = html;
    if (reqEmpty) reqEmpty.hidden = true;

    /* ── 이벤트 바인딩 ── */
    bindRequirementsEvents(requirements, categoryClassMap);
  }

  /* ============================================================
     배점기준 탭 콘텐츠 렌더링
     ============================================================ */
  function populateScoringTab(scoringData) {
    var scoringContent = document.getElementById('tabpanel-scoring-content');
    var scoringEmpty   = document.getElementById('tabpanel-scoring-empty');
    if (!scoringContent) return;

    /* 데이터가 없거나 빈 배열이면 빈 상태 표시 */
    if (!scoringData || scoringData.length === 0) {
      if (scoringEmpty) scoringEmpty.hidden = false;
      return;
    }

    /* 분류별 그룹핑 (출현순서 유지) */
    var categoryOrder = [];
    var categoryMap = {};
    for (var i = 0; i < scoringData.length; i++) {
      var cat = scoringData[i].category;
      if (!categoryMap[cat]) {
        categoryMap[cat] = { items: [], totalScore: 0 };
        categoryOrder.push(cat);
      }
      categoryMap[cat].items.push(scoringData[i]);
      categoryMap[cat].totalScore += scoringData[i].score;
    }

    /* 총점 계산 */
    var grandTotal = 0;
    for (var t = 0; t < categoryOrder.length; t++) {
      grandTotal += categoryMap[categoryOrder[t]].totalScore;
    }

    /* 분류별 색상 매핑 */
    var categoryColors = [
      { bg: 'var(--krds-color-primary-50)',  text: 'var(--krds-color-primary-600)', bar: 'var(--krds-color-primary-500)' },
      { bg: '#E8F5E9',                       text: '#2E7D32',                       bar: '#43A047' },
      { bg: 'var(--krds-color-warning-light)',text: 'var(--krds-color-warning-dark)', bar: '#F9A825' },
      { bg: 'var(--krds-color-info-light)',   text: 'var(--krds-color-info-dark)',    bar: 'var(--krds-color-info)' },
      { bg: 'var(--krds-color-error-light)',  text: 'var(--krds-color-error-dark)',   bar: 'var(--krds-color-error)' },
      { bg: '#F3E5F5',                       text: '#6A1B9A',                        bar: '#8E24AA' },
      { bg: '#FFF3E0',                       text: '#E65100',                        bar: '#FB8C00' }
    ];

    /* ── 통계 요약 바 ── */
    var html = '<div class="scoring-summary">';
    html += '<div class="scoring-summary-header">';
    html += '<span class="scoring-summary-title">배점 현황</span>';
    html += '<span class="scoring-summary-total">총점 <strong>' + grandTotal + '점</strong></span>';
    html += '</div>';

    /* 분류별 비율 막대 차트 */
    html += '<div class="scoring-ratio-bar" role="img" aria-label="평가분류별 배점 비율 차트">';
    for (var b = 0; b < categoryOrder.length; b++) {
      var catName = categoryOrder[b];
      var catData = categoryMap[catName];
      var pct = Math.round((catData.totalScore / grandTotal) * 100);
      var color = categoryColors[b % categoryColors.length];
      html += '<div class="scoring-ratio-segment" style="width:' + pct + '%;background-color:' + color.bar + '" title="' + escapeHtml(catName) + ' ' + catData.totalScore + '점 (' + pct + '%)">';
      if (pct >= 8) {
        html += '<span class="scoring-ratio-label">' + pct + '%</span>';
      }
      html += '</div>';
    }
    html += '</div>';

    /* 범례 */
    html += '<div class="scoring-legend">';
    for (var lg = 0; lg < categoryOrder.length; lg++) {
      var lCat = categoryOrder[lg];
      var lData = categoryMap[lCat];
      var lColor = categoryColors[lg % categoryColors.length];
      var lPct = Math.round((lData.totalScore / grandTotal) * 100);
      html += '<span class="scoring-legend-item">';
      html += '<span class="scoring-legend-dot" style="background-color:' + lColor.bar + '"></span>';
      html += escapeHtml(lCat) + ' <strong>' + lData.totalScore + '점</strong>';
      html += '<span class="scoring-legend-pct">(' + lPct + '%)</span>';
      html += '</span>';
    }
    html += '</div>';
    html += '</div>';

    /* ── 테이블 ── */
    html += '<div class="scoring-table-wrap">';
    html += '<table class="scoring-table">';
    html += '<caption class="sr-only">배점기준표 – 총점 ' + grandTotal + '점</caption>';
    html += '<thead><tr>';
    html += '<th scope="col" class="scoring-col-category">평가분류</th>';
    html += '<th scope="col" class="scoring-col-item">평가항목</th>';
    html += '<th scope="col" class="scoring-col-criteria">세부평가기준</th>';
    html += '<th scope="col" class="scoring-col-score">배점</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    for (var g = 0; g < categoryOrder.length; g++) {
      var gCat = categoryOrder[g];
      var gData = categoryMap[gCat];
      var gColor = categoryColors[g % categoryColors.length];
      var items = gData.items;

      for (var r = 0; r < items.length; r++) {
        var isFirst = (r === 0);
        var isLast  = (r === items.length - 1);
        var rowClass = isLast ? ' scoring-group-last' : '';

        html += '<tr class="scoring-group-' + g + rowClass + '">';

        /* 평가분류 (첫 행에서만 rowspan) */
        if (isFirst) {
          html += '<td class="scoring-col-category scoring-category-cell" rowspan="' + items.length + '">';
          html += '<div class="scoring-category-inner">';
          html += '<span class="scoring-category-badge" style="background-color:' + gColor.bg + ';color:' + gColor.text + '">' + escapeHtml(gCat) + '</span>';
          html += '<span class="scoring-category-subtotal">' + gData.totalScore + '점</span>';
          html += '</div>';
          html += '</td>';
        }

        /* 평가항목 */
        html += '<td class="scoring-col-item" data-label="평가항목"><span class="scoring-item-name">' + escapeHtml(items[r].item) + '</span></td>';

        /* 세부평가기준 */
        html += '<td class="scoring-col-criteria" data-label="세부평가기준"><span class="scoring-criteria-text">' + escapeHtml(items[r].criteria) + '</span></td>';

        /* 배점 */
        html += '<td class="scoring-col-score" data-label="배점"><span class="scoring-score-value">' + items[r].score + '</span></td>';

        html += '</tr>';
      }
    }

    /* 합계 행 */
    html += '</tbody>';
    html += '<tfoot>';
    html += '<tr class="scoring-total-row">';
    html += '<td colspan="3" class="scoring-total-label">합계</td>';
    html += '<td class="scoring-col-score"><span class="scoring-score-total">' + grandTotal + '</span></td>';
    html += '</tr>';
    html += '</tfoot>';
    html += '</table>';
    html += '</div>';

    scoringContent.innerHTML = html;
    if (scoringEmpty) scoringEmpty.hidden = true;

    /* 모바일 가로 스크롤 힌트 */
    var scoringWrap = scoringContent.querySelector('.scoring-table-wrap');
    if (scoringWrap) {
      scoringWrap.classList.add('scroll-hint-wrap');
      scoringWrap.addEventListener('scroll', function () {
        var atEnd = scoringWrap.scrollLeft + scoringWrap.clientWidth >= scoringWrap.scrollWidth - 4;
        scoringWrap.classList.toggle('is-scrolled-end', atEnd);
      });
    }
  }

  /* ── 요구사항 행 HTML 생성 ── */
  function buildReqRow(req, classMap) {
    var isMandatory = req.level === '필수';
    var catClass = classMap[req.category] || 'is-func';
    var needsToggle = req.desc && req.desc.length > 80;

    /* 신뢰도 검사: ID 또는 설명 누락 시 '검토 필요' 표시 */
    var needsReview = (!req.id || req.id.trim() === '') || (!req.desc || req.desc.trim() === '');
    var reviewBadge = '';
    if (needsReview && typeof window.StateUI !== 'undefined') {
      reviewBadge = ' ' + window.StateUI.buildConfidenceBadge(needsReview ? 30 : 80);
    }

    var rowClass = isMandatory ? 'is-mandatory' : '';
    if (needsReview) rowClass += ' needs-review';

    var row = '<tr class="' + rowClass + '" data-category="' + escapeHtml(req.category) + '" data-id="' + escapeHtml(req.id) + '" data-name="' + escapeHtml(req.name) + '">';
    row += '<td class="req-col-category" data-label="분류"><span class="req-category-badge ' + catClass + '">' + escapeHtml(req.category) + '</span></td>';
    row += '<td class="req-col-id" data-label="ID"><span class="req-id">' + escapeHtml(req.id || '—') + '</span></td>';
    row += '<td class="req-col-name" data-label="요구사항명"><span class="req-name">' + escapeHtml(req.name) + '</span>' + reviewBadge + '</td>';
    row += '<td class="req-col-desc" data-label="상세설명">';
    if (!req.desc || req.desc.trim() === '') {
      row += '<span class="req-desc-text" style="color:var(--krds-text-tertiary);font-style:italic">(상세설명 없음)</span>';
    } else {
      row += '<div class="req-desc-text">' + escapeHtml(req.desc) + '</div>';
      if (needsToggle) {
        row += '<button type="button" class="req-desc-toggle" aria-label="상세설명 펼치기">';
        row += '더보기 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>';
        row += '</button>';
      }
    }
    row += '</td>';
    row += '<td class="req-col-level" data-label="응낙수준"><span class="req-level-badge ' + (isMandatory ? 'is-mandatory' : 'is-optional') + '">' + escapeHtml(req.level) + '</span></td>';
    row += '</tr>';
    return row;
  }

  /* ── 요구사항 이벤트 바인딩 (필터, 검색, 토글) ── */
  function bindRequirementsEvents(requirements, classMap) {
    var filterSelect  = document.getElementById('req-category-filter');
    var searchInput   = document.getElementById('req-search-input');
    var tableBody     = document.getElementById('req-table-body');
    var tableWrap     = document.querySelector('.req-table-wrap');
    var emptyResult   = document.getElementById('req-empty-result');
    var filteredCount = document.getElementById('req-filtered-count');
    var filteredNum   = document.getElementById('req-filtered-num');

    if (!filterSelect || !searchInput || !tableBody) return;

    var currentCategory = 'all';
    var currentSearch = '';

    /* 상세설명 펼치기/접기 (이벤트 위임) */
    tableBody.addEventListener('click', function (e) {
      var toggleBtn = e.target.closest('.req-desc-toggle');
      if (!toggleBtn) return;

      var descText = toggleBtn.previousElementSibling;
      if (!descText) return;

      var isExpanded = descText.classList.toggle('is-expanded');
      toggleBtn.classList.toggle('is-expanded', isExpanded);

      if (isExpanded) {
        toggleBtn.innerHTML = '접기 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>';
        toggleBtn.setAttribute('aria-label', '상세설명 접기');
      } else {
        toggleBtn.innerHTML = '더보기 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>';
        toggleBtn.setAttribute('aria-label', '상세설명 펼치기');
      }
    });

    /* 필터 + 검색 적용 */
    function applyFilter() {
      var filtered = [];
      var searchLower = currentSearch.toLowerCase();

      for (var i = 0; i < requirements.length; i++) {
        var req = requirements[i];
        var matchCategory = (currentCategory === 'all') || (req.category === currentCategory);
        var matchSearch = !currentSearch ||
          req.id.toLowerCase().indexOf(searchLower) !== -1 ||
          req.name.toLowerCase().indexOf(searchLower) !== -1;

        if (matchCategory && matchSearch) {
          filtered.push(req);
        }
      }

      /* 테이블 리렌더 */
      var rowsHtml = '';
      for (var j = 0; j < filtered.length; j++) {
        rowsHtml += buildReqRow(filtered[j], classMap);
      }
      tableBody.innerHTML = rowsHtml;

      /* 검색어 하이라이트 */
      if (currentSearch) {
        highlightSearch(tableBody, currentSearch);
      }

      /* 결과 없음 표시 */
      var hasResults = filtered.length > 0;
      if (tableWrap) tableWrap.hidden = !hasResults;
      if (emptyResult) emptyResult.hidden = hasResults;

      /* 필터링 카운트 표시 */
      var isFiltered = currentCategory !== 'all' || currentSearch;
      if (filteredCount) filteredCount.hidden = !isFiltered;
      if (filteredNum) filteredNum.textContent = String(filtered.length);
    }

    /* 분류 필터 */
    filterSelect.addEventListener('change', function () {
      currentCategory = filterSelect.value;
      applyFilter();
    });

    /* ID/이름 검색 (디바운스) */
    var searchTimer = null;
    searchInput.addEventListener('input', function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        currentSearch = searchInput.value.trim();
        applyFilter();
      }, 250);
    });
  }

  /* ── 검색어 하이라이트 ── */
  function highlightSearch(container, term) {
    var cells = container.querySelectorAll('.req-id, .req-name');
    var termLower = term.toLowerCase();

    for (var i = 0; i < cells.length; i++) {
      var text = cells[i].textContent;
      var textLower = text.toLowerCase();
      var idx = textLower.indexOf(termLower);

      if (idx !== -1) {
        var before = text.substring(0, idx);
        var match = text.substring(idx, idx + term.length);
        var after = text.substring(idx + term.length);
        cells[i].innerHTML = escapeHtml(before) +
          '<span class="req-highlight">' + escapeHtml(match) + '</span>' +
          escapeHtml(after);
      }
    }
  }

  /* ============================================================
     제안목차 탭 콘텐츠 렌더링 (TocEditor에 위임)
     ============================================================ */
  function populateTocTab(tocData) {
    var tocContent = document.getElementById('tabpanel-toc-content');
    var tocEmpty   = document.getElementById('tabpanel-toc-empty');
    if (!tocContent) return;

    /* 데이터가 없거나 빈 배열이면 빈 상태 표시 */
    if (!tocData || tocData.length === 0) {
      if (tocEmpty) tocEmpty.hidden = false;
      /* TocEditor도 초기화 (빈 상태에서도 템플릿 적용·추가 가능) */
      if (typeof window.TocEditor !== 'undefined') {
        if (tocEmpty) tocEmpty.hidden = true;
        window.TocEditor.init('tabpanel-toc-content', []);
      }
      return;
    }

    if (tocEmpty) tocEmpty.hidden = true;

    /* TocEditor가 로드되어 있으면 위임 */
    if (typeof window.TocEditor !== 'undefined') {
      window.TocEditor.init('tabpanel-toc-content', tocData);
    } else {
      tocContent.innerHTML = '<p style="color:var(--krds-text-tertiary);">목차 에디터를 로드할 수 없습니다.</p>';
    }
  }

  /* ── 다시 분석 ── */
  if (retryBtn) {
    retryBtn.addEventListener('click', function () {
      /* 진행 중인 API 요청이 있으면 취소 */
      if (currentRequest) {
        currentRequest.abort();
        currentRequest = null;
      }
      stopProgressAnimation();

      resultCard.hidden = true;
      resultCard.classList.remove('is-visible');
      uploadCardEl.hidden = false;

      /* 에러 상태 / 경고 숨기기 */
      var analysisErrorCard = document.getElementById('analysis-error');
      if (analysisErrorCard) {
        analysisErrorCard.hidden = true;
        analysisErrorCard.classList.remove('is-visible');
      }
      if (typeof window.StateUI !== 'undefined') {
        window.StateUI.hideErrorState();
        window.StateUI.hideParsingWarnings();
      }

      /* 사업개요 탭 초기화 */
      var overviewContent = document.getElementById('tabpanel-overview-content');
      var overviewEmpty   = document.getElementById('tabpanel-overview-empty');
      if (overviewContent) overviewContent.innerHTML = '';
      if (overviewEmpty) overviewEmpty.hidden = false;

      /* 요구사항 탭 초기화 */
      var reqContent = document.getElementById('tabpanel-requirements-content');
      var reqEmpty   = document.getElementById('tabpanel-requirements-empty');
      if (reqContent) reqContent.innerHTML = '';
      if (reqEmpty) reqEmpty.hidden = false;

      /* 배점기준 탭 초기화 */
      var scoringContent = document.getElementById('tabpanel-scoring-content');
      var scoringEmpty   = document.getElementById('tabpanel-scoring-empty');
      if (scoringContent) scoringContent.innerHTML = '';
      if (scoringEmpty) scoringEmpty.hidden = false;

      /* 제안목차 탭 초기화 */
      var tocContentEl = document.getElementById('tabpanel-toc-content');
      var tocEmptyEl   = document.getElementById('tabpanel-toc-empty');
      if (tocContentEl) tocContentEl.innerHTML = '';
      if (tocEmptyEl) tocEmptyEl.hidden = false;

      /* 탭 카드 숨기기 */
      if (typeof window.hideAnalysisTabs === 'function') {
        window.hideAnalysisTabs();
      }
    });
  }
})();
