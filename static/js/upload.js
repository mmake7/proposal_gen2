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
  var ALLOWED_EXTENSIONS = ['.pdf', '.hwpx', '.docx'];
  /* MIME은 PDF만 신뢰 가능(hwpx/docx는 브라우저별 상이) — 검증은 확장자 기준 */
  var ALLOWED_PDF_MIME = 'application/pdf';
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
        desc: '"' + ext + '" 파일은 업로드할 수 없습니다. PDF(.pdf)·HWPX(.hwpx)·DOCX(.docx) 파일만 허용됩니다. (.hwp/.doc는 변환 후 업로드)'
      };
    }

    /* 2) MIME 검사 — PDF만 신뢰 가능 (hwpx/docx는 브라우저별 MIME 상이) */
    if (ext === '.pdf' && file.type && file.type !== ALLOWED_PDF_MIME) {
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

    /* 엔진 선택 — radio[name="engine"]에서 읽음. 기본 v2. */
    var engineRadio = document.querySelector('input[name="engine"]:checked');
    var selectedEngine = engineRadio ? engineRadio.value : 'v2';

    /* v2 다운로드 버튼 그룹 (v2 분석 시에만 노출) */
    var v2DownloadGroup = document.getElementById('v2-download-group');

    /* Flask API 호출 — 세 번째 인자로 engine 전달 */
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

        /* v2 분석이면 다운로드 그룹 + 견적 카드 노출 */
        if (v2DownloadGroup) {
          v2DownloadGroup.hidden = (selectedEngine !== 'v2');
        }
        if (selectedEngine === 'v2' && data._estimation) {
          renderEstimationCard(data._estimation);
        }

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
    }, { engine: selectedEngine });

    /* 서버 분석 대기 중 진행률 애니메이션 시작 (20% ~ 90%) */
    activateStep(0);
    startProgressAnimation();
  }

  /* ── v2 견적 카드 렌더 ── */
  function renderEstimationCard(est) {
    var card = document.getElementById('estimation-card');
    if (!card || !est) return;

    // 헤더 총계
    var period = est.project_months ? est.project_months.toFixed(0) + '개월' : '미산정';
    document.getElementById('est-period').textContent = period;
    var totalHead = (est.organization || []).reduce(function (s, o) { return s + (o.headcount || 0); }, 0);
    document.getElementById('est-headcount').textContent = totalHead + '명';
    document.getElementById('est-total-mm').textContent = (est.total_mm || 0).toFixed(1);

    // 조직도
    var orgBody = document.getElementById('est-org-tbody');
    var orgEmpty = document.getElementById('est-org-empty');
    orgBody.innerHTML = '';
    if (!est.organization || est.organization.length === 0) {
      orgEmpty.hidden = false;
    } else {
      orgEmpty.hidden = true;
      est.organization.forEach(function (org) {
        var tr = document.createElement('tr');
        tr.innerHTML = '<td>' + escapeHtml(org.role) + '</td>' +
                       '<td class="num">' + org.headcount + '명</td>' +
                       '<td>' + escapeHtml(org.grade || '-') + '</td>';
        orgBody.appendChild(tr);
      });
    }

    // M/M
    var mmBody = document.getElementById('est-mm-tbody');
    mmBody.innerHTML = '';
    (est.man_months || []).forEach(function (mm) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td>' + escapeHtml(mm.role) + '</td>' +
                     '<td class="num">' + mm.headcount + '</td>' +
                     '<td class="num">' + mm.months.toFixed(0) + '</td>' +
                     '<td class="num strong">' + mm.total_mm.toFixed(1) + '</td>';
      mmBody.appendChild(tr);
    });
    document.getElementById('est-mm-total').textContent = (est.total_mm || 0).toFixed(1);

    // WBS 타임라인
    var wbsList = document.getElementById('est-wbs-list');
    wbsList.innerHTML = '';
    (est.wbs || []).forEach(function (phase) {
      var div = document.createElement('div');
      div.className = 'estimation-wbs-phase';
      var wrange = phase.week_start ? ('W' + phase.week_start + '~W' + phase.week_end) : '-';
      var acts = (phase.activities || []).map(function (a) {
        return '<li>' + escapeHtml(a) + '</li>';
      }).join('');
      var dels = (phase.deliverables || []).map(function (d) {
        return '<li>' + escapeHtml(d) + '</li>';
      }).join('');
      div.innerHTML =
        '<div class="estimation-wbs-head">' +
          '<span class="estimation-wbs-name">' + escapeHtml(phase.name) + '</span>' +
          '<span class="estimation-wbs-meta">' + wrange + ' · ' + phase.duration_weeks + '주</span>' +
        '</div>' +
        '<div class="estimation-wbs-body">' +
          '<div><h5>활동</h5><ul>' + acts + '</ul></div>' +
          '<div><h5>산출물</h5><ul>' + dels + '</ul></div>' +
        '</div>';
      wbsList.appendChild(div);
    });

    // notes
    var notesEl = document.getElementById('est-notes');
    notesEl.textContent = est.notes || '';

    card.hidden = false;
  }

  /* escapeHtml·esc·toast → util.js 전역 사용 */

  /* ── 데모 모드: URL ?demo=estimation 이면 KIAT mock 견적 자동 렌더 ── */
  function checkDemoMode() {
    var params = new URLSearchParams(location.search);
    if (params.get('demo') !== 'estimation') return;
    var mockEstimation = {
      project_months: 24,
      total_mm: 528.0,
      organization: [
        { role: 'PM', headcount: 1, grade: '고급', notes: '상주' },
        { role: '응용SW 개발자', headcount: 15, grade: '중급', notes: '' },
        { role: 'UI/UX 디자이너', headcount: 1, grade: '중급', notes: '' },
        { role: 'IT 지원기술자', headcount: 5, grade: '초급', notes: '' }
      ],
      man_months: [
        { role: 'PM', headcount: 1, months: 24, total_mm: 24.0, grade: '고급' },
        { role: '응용SW 개발자', headcount: 15, months: 24, total_mm: 360.0, grade: '중급' },
        { role: 'UI/UX 디자이너', headcount: 1, months: 24, total_mm: 24.0, grade: '중급' },
        { role: 'IT 지원기술자', headcount: 5, months: 24, total_mm: 120.0, grade: '초급' }
      ],
      wbs: [
        { name: '분석/설계', activities: ['요구사항 분석', '아키텍처 설계', 'DB 설계'],
          deliverables: ['요구사항 정의서', '시스템 설계서', 'DB 설계서'],
          duration_weeks: 24, week_start: 1, week_end: 24 },
        { name: '구축/개발', activities: ['응용 SW 개발', '인프라 구축', '연계 개발'],
          deliverables: ['소스코드', '시스템 매뉴얼', '연계 명세서'],
          duration_weeks: 43, week_start: 25, week_end: 67 },
        { name: '테스트', activities: ['단위/통합 테스트', '성능 테스트', '보안 점검'],
          deliverables: ['테스트 계획서', '테스트 결과서'],
          duration_weeks: 14, week_start: 68, week_end: 81 },
        { name: '이행/안정화', activities: ['데이터 이관', '교육', '안정화 운영'],
          deliverables: ['이행 계획서', '교육 자료', '운영 매뉴얼'],
          duration_weeks: 15, week_start: 82, week_end: 96 }
      ],
      notes: '[데모] KIAT 정보시스템 운영·유지보수 사업 기준 — 기간 24개월, 직무 4종, 총 528.0 M/M'
    };
    setTimeout(function () { renderEstimationCard(mockEstimation); }, 100);
  }
  checkDemoMode();

  /* ── v2 다운로드 버튼 핸들러 ── */
  function setupV2DownloadButtons() {
    var btnConfig = [
      ['v2-excel-btn',    'excel'],
      ['v2-markdown-btn', 'markdown'],
      ['v2-json-btn',     'json']
    ];
    btnConfig.forEach(function (cfg) {
      var btn = document.getElementById(cfg[0]);
      if (!btn) return;
      btn.addEventListener('click', function () {
        if (!window.ApiClient || !window.ApiClient.downloadV2) {
          alert('v2 다운로드를 사용할 수 없습니다.');
          return;
        }
        btn.disabled = true;
        window.ApiClient.downloadV2(cfg[1])
          .catch(function (err) {
            alert('다운로드 실패: ' + (err && err.message ? err.message : err));
          })
          .then(function () {
            btn.disabled = false;
          });
      });
    });
  }
  setupV2DownloadButtons();

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
    var overview       = apiData.overview;
    var requirements   = apiData.requirements || [];
    var scoring        = apiData.scoring || [];
    var toc            = apiData.toc || [];
    var parserStats    = apiData.parser_stats   || null;
    var parserSummary  = apiData.parser_summary || [];

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

    /* ① 탭 콘텐츠를 먼저 채워서 비어있지 않은 탭의 empty 상태를 숨긴다 */
    var qualityResult = null;
    if (typeof window.StateUI !== 'undefined') {
      qualityResult = window.StateUI.analyzeParsingQuality(apiData);
    }

    populateOverviewTab(overview, qualityResult ? qualityResult.fieldScores : null);
    populateRequirementsTab(requirements, parserStats, parserSummary);
    populateScoringTab(scoring);
    populateTocTab(toc, requirements);

    /* ② 데이터가 없는 탭에만 빈 상태 업그레이드 + 경고 알림 표시 */
    if (typeof window.StateUI !== 'undefined') {
      if (!overview) {
        window.StateUI.upgradeEmptyState('overview');
        window.StateUI.showTabAlert('overview', 'error', '사업개요 데이터를 추출하지 못했습니다. PDF 문서의 형식을 확인해주세요.');
      }
      if (requirements.length === 0) {
        window.StateUI.upgradeEmptyState('requirements');
        window.StateUI.showTabAlert('requirements', 'warning', '요구사항을 추출하지 못했습니다. RFP에 요구사항 섹션이 포함되어 있는지 확인해주세요.');
      }
      if (scoring.length === 0) {
        window.StateUI.upgradeEmptyState('scoring');
        window.StateUI.showTabAlert('scoring', 'warning', '배점기준을 추출하지 못했습니다. 평가기준표가 포함된 PDF인지 확인해주세요.');
      }
      /* TOC 빈 상태는 TocEditor가 직접 관리 (템플릿 선택/수동 작성 안내 포함)
         — upgradeEmptyState, showTabAlert 불필요 */

      /* 파싱 경고 표시 (데이터가 있지만 불완전한 항목만) */
      if (qualityResult && qualityResult.warnings.length > 0) {
        window.StateUI.showParsingWarnings(qualityResult.warnings);
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


  /* ============================================================
     요구사항 탭 콘텐츠 렌더링
     ============================================================ */
  function populateRequirementsTab(requirements, parserStats, parserSummary) {
    var reqContent = document.getElementById('tabpanel-requirements-content');
    var reqEmpty   = document.getElementById('tabpanel-requirements-empty');
    if (!reqContent) return;

    if (!requirements || requirements.length === 0) {
      if (reqEmpty) reqEmpty.hidden = false;
      return;
    }

    /* 분류 → CSS 클래스 매핑 (약칭 + 풀네임 + category_code) */
    var categoryClassMap = {
      '기능': 'is-func',     '기능 요구사항': 'is-func',
      '비기능': 'is-nonfunc', '비기능 요구사항': 'is-nonfunc',
      '성능': 'is-perf',     '성능 요구사항': 'is-perf',
      '보안': 'is-security', '보안 요구사항': 'is-security',
      '데이터': 'is-data',   '데이터 요구사항': 'is-data',
      '인터페이스': 'is-interface', '인터페이스 요구사항': 'is-interface'
    };
    var codeClassMap = {
      'SFR': 'is-func',  'SNR': 'is-nonfunc', 'PER': 'is-perf',
      'SER': 'is-security', 'SSR': 'is-security',
      'DAR': 'is-data',  'SDR': 'is-data',
      'SIR': 'is-interface',
      'TER': 'is-perf',  'QUR': 'is-nonfunc',
      'PSR': 'is-nonfunc', 'PMR': 'is-nonfunc', 'MPR': 'is-nonfunc',
      'ECR': 'is-data',  'COR': 'is-interface', 'CSR': 'is-interface'
    };

    /* 인덱스 부여 (상세 보기에서 참조) */
    for (var idx = 0; idx < requirements.length; idx++) {
      requirements[idx]._index = idx;
    }

    var html = '';

    /* ── 1. 파싱 통계 카드 ── */
    if (parserStats) {
      var compPct = Math.min(parserStats.completeness_pct || 0, 100);
      var detPct  = Math.min(parserStats.detail_completeness_pct || 0, 100);
      var compColor = compPct >= 95 ? 'is-success' : compPct >= 80 ? 'is-warning' : 'is-error';
      var detColor  = detPct  >= 95 ? 'is-success' : detPct  >= 80 ? 'is-warning' : 'is-error';

      html += '<div class="req-stats-card">';
      html +=   '<div class="req-stats-header">';
      html +=     '<span class="req-stats-title">파싱 현황</span>';
      html +=     '<span class="req-stats-total">총 <strong>' + (parserStats.parsed_total || requirements.length) + '</strong>건 추출</span>';
      html +=   '</div>';

      html +=   '<div class="req-stats-row">';
      html +=     '<span class="req-stats-label">요구사항 완성도</span>';
      html +=     '<span class="req-stats-value">' + (parserStats.completeness_pct || 0) + '%</span>';
      html +=   '</div>';
      html +=   '<div class="req-stats-bar"><div class="req-stats-bar-fill ' + compColor + '" style="width:' + compPct + '%"></div></div>';

      html +=   '<div class="req-stats-row">';
      html +=     '<span class="req-stats-label">세부내용 완성도</span>';
      html +=     '<span class="req-stats-value">' + (parserStats.detail_completeness_pct || 0) + '%</span>';
      html +=   '</div>';
      html +=   '<div class="req-stats-bar"><div class="req-stats-bar-fill ' + detColor + '" style="width:' + detPct + '%"></div></div>';

      html +=   '<div class="req-stats-chips">';
      if (parserStats.table_parsed > 0) html += '<span class="req-stats-chip is-table">테이블 ' + parserStats.table_parsed + '</span>';
      if (parserStats.text_parsed > 0)  html += '<span class="req-stats-chip is-text">텍스트 ' + parserStats.text_parsed + '</span>';
      if (parserStats.list_only > 0)    html += '<span class="req-stats-chip is-list">목록만 ' + parserStats.list_only + '</span>';
      html +=     '<span class="req-stats-chip is-cat">분류 ' + (parserStats.categories_found || 0) + '개</span>';
      html +=   '</div>';
      html += '</div>';
    }

    /* ── 2. 분류별 뱃지 ── */
    if (parserSummary && parserSummary.length > 0) {
      html += '<div class="req-cat-badges" id="req-cat-badges">';
      html +=   '<div class="req-cat-badges-header">';
      html +=     '<span class="req-cat-badges-title">분류별 요구사항</span>';
      html +=     '<button type="button" class="req-cat-badges-toggle" id="req-cat-badges-toggle" aria-expanded="true">접기</button>';
      html +=   '</div>';
      html +=   '<div class="req-cat-badges-list" id="req-cat-badges-list">';
      html +=     '<button type="button" class="req-cat-badge-btn is-active" data-category="all">';
      html +=       '<span class="req-cat-badge-name">전체</span>';
      html +=       '<span class="req-cat-badge-count">' + requirements.length + '</span>';
      html +=     '</button>';
      for (var ps = 0; ps < parserSummary.length; ps++) {
        var s = parserSummary[ps];
        var shortName = (s.category || '').replace(/\s*요구사항$/, '');
        html += '<button type="button" class="req-cat-badge-btn" data-category="' + escapeHtml(s.category || '') + '">';
        html +=   '<span class="req-cat-badge-code">' + escapeHtml(s.code || '') + '</span>';
        html +=   '<span class="req-cat-badge-name">' + escapeHtml(shortName) + '</span>';
        html +=   '<span class="req-cat-badge-count">' + (s.count || 0) + '</span>';
        html += '</button>';
      }
      html +=   '</div>';
      html += '</div>';
    }

    /* ── 3. 툴바 ── */
    html += '<div class="req-toolbar">';
    html +=   '<div class="req-filter-group">';
    html +=     '<select class="req-filter-select" id="req-method-filter" aria-label="파싱방식 필터">';
    html +=       '<option value="all">파싱: 전체</option>';
    html +=       '<option value="table">테이블</option>';
    html +=       '<option value="text">텍스트</option>';
    html +=       '<option value="ai">AI</option>';
    html +=       '<option value="list_only">목록만</option>';
    html +=     '</select>';
    html +=     '<label class="req-toggle-label">';
    html +=       '<input type="checkbox" id="req-missing-only" class="req-toggle-check">';
    html +=       '<span>미완성만</span>';
    html +=     '</label>';
    html +=   '</div>';
    html +=   '<div class="req-sort-group">';
    html +=     '<select class="req-filter-select" id="req-sort" aria-label="정렬">';
    html +=       '<option value="id">ID순</option>';
    html +=       '<option value="category">분류순</option>';
    html +=       '<option value="name">이름순</option>';
    html +=     '</select>';
    html +=   '</div>';
    html +=   '<div class="req-search-box">';
    html +=     '<input type="text" class="req-search-input" id="req-search-input" placeholder="ID, 요구사항명, 정의 검색" aria-label="요구사항 검색">';
    html +=   '</div>';
    html +=   '<span class="req-filter-count" id="req-filtered-count" hidden>검색 결과: <strong id="req-filtered-num">0</strong>건</span>';
    html += '</div>';

    /* ── 4. 테이블 ── */
    html += '<div class="req-table-wrap">';
    html += '<table class="req-table" id="req-table">';
    html += '<caption class="sr-only">RFP 요구사항 목록 – 총 ' + requirements.length + '건</caption>';
    html += '<thead><tr>';
    html += '<th scope="col" class="req-col-id">ID</th>';
    html += '<th scope="col" class="req-col-name">요구사항명</th>';
    html += '<th scope="col" class="req-col-category">분류</th>';
    html += '<th scope="col" class="req-col-def">정의</th>';
    html += '<th scope="col" class="req-col-detail">세부</th>';
    html += '<th scope="col" class="req-col-method">파싱</th>';
    html += '</tr></thead>';
    html += '<tbody id="req-table-body">';
    for (var r = 0; r < requirements.length; r++) {
      html += buildReqRow(requirements[r], categoryClassMap, codeClassMap);
    }
    html += '</tbody></table></div>';

    /* ── 5. 검색 결과 없음 ── */
    html += '<div class="req-empty-result" id="req-empty-result" hidden>';
    html += '<svg class="req-empty-result-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';
    html += '<p class="req-empty-result-text">검색 결과가 없습니다</p>';
    html += '</div>';

    reqContent.innerHTML = html;
    if (reqEmpty) reqEmpty.hidden = true;

    bindRequirementsEvents(requirements, categoryClassMap, codeClassMap);
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
  function buildReqRow(req, classMap, codeMap) {
    var code = req.category_code || '';
    var catShort = code || (req.category || '').replace(/\s*요구사항$/, '');
    var catClass = (code && codeMap[code]) || classMap[req.category] || classMap[catShort] || 'is-func';
    var hasDef    = req.definition && req.definition.trim() !== '';
    var hasDetail = req.detail && req.detail.trim() !== '';
    var methodClass = { table: 'is-table', text: 'is-text', ai: 'is-ai', list_only: 'is-list' }[req.parse_method] || '';
    var methodLabel = { table: '테이블', text: '텍스트', ai: 'AI', list_only: '목록' }[req.parse_method] || '—';

    var row = '<tr class="req-row" data-category="' + escapeHtml(req.category) + '"';
    row += ' data-id="' + escapeHtml(req.id) + '"';
    row += ' data-name="' + escapeHtml(req.name) + '"';
    row += ' data-method="' + escapeHtml(req.parse_method || '') + '"';
    row += ' data-has-detail="' + (hasDetail ? '1' : '0') + '"';
    row += ' data-req-index="' + (req._index != null ? req._index : '') + '">';

    row += '<td class="req-col-id" data-label="ID"><span class="req-id">' + escapeHtml(req.id || '—') + '</span></td>';
    row += '<td class="req-col-name" data-label="요구사항명"><span class="req-name">' + escapeHtml(req.name) + '</span></td>';
    row += '<td class="req-col-category" data-label="분류"><span class="req-category-badge ' + catClass + '">' + escapeHtml(catShort) + '</span></td>';
    row += '<td class="req-col-def" data-label="정의"><span class="req-presence ' + (hasDef ? 'is-ok' : 'is-missing') + '">' + (hasDef ? '&#10003;' : '&#9888;') + '</span></td>';
    row += '<td class="req-col-detail" data-label="세부"><span class="req-presence ' + (hasDetail ? 'is-ok' : 'is-missing') + '">' + (hasDetail ? '&#10003;' : '&#9888;') + '</span></td>';
    row += '<td class="req-col-method" data-label="파싱"><span class="req-method-badge ' + methodClass + '">' + escapeHtml(methodLabel) + '</span></td>';
    row += '</tr>';
    return row;
  }

  /* ── 요구사항 이벤트 바인딩 ── */
  function bindRequirementsEvents(requirements, classMap, codeMap) {
    var methodFilter  = document.getElementById('req-method-filter');
    var missingCheck  = document.getElementById('req-missing-only');
    var sortSelect    = document.getElementById('req-sort');
    var searchInput   = document.getElementById('req-search-input');
    var tableBody     = document.getElementById('req-table-body');
    var tableWrap     = document.querySelector('.req-table-wrap');
    var emptyResult   = document.getElementById('req-empty-result');
    var filteredCount = document.getElementById('req-filtered-count');
    var filteredNum   = document.getElementById('req-filtered-num');
    var badgeList     = document.getElementById('req-cat-badges-list');
    var badgeToggle   = document.getElementById('req-cat-badges-toggle');

    if (!tableBody) return;

    var currentCategory = 'all';
    var currentMethod   = 'all';
    var currentSort     = 'id';
    var missingOnly     = false;
    var currentSearch   = '';

    /* ── 행 클릭 → 인라인 상세 패널 ── */
    tableBody.addEventListener('click', function (e) {
      /* 텍스트 선택 중이면 무시 */
      if (window.getSelection && window.getSelection().toString().length > 1) return;

      var row = e.target.closest('tr.req-row');
      if (!row) return;

      var idxStr = row.getAttribute('data-req-index');
      if (idxStr === '' || idxStr === null) return;
      var reqIdx = parseInt(idxStr, 10);
      if (isNaN(reqIdx) || !requirements[reqIdx]) return;
      var req = requirements[reqIdx];

      /* 이미 열린 상세 행이면 닫기 */
      var next = row.nextElementSibling;
      if (next && next.classList.contains('req-detail-row')) {
        next.remove();
        row.classList.remove('is-expanded');
        return;
      }

      /* 다른 열린 상세 행 닫기 */
      var openRows = tableBody.querySelectorAll('.req-detail-row');
      for (var d = 0; d < openRows.length; d++) {
        if (openRows[d].previousElementSibling) openRows[d].previousElementSibling.classList.remove('is-expanded');
        openRows[d].remove();
      }

      /* 상세 패널 HTML 생성 */
      var dh = '<tr class="req-detail-row"><td colspan="6">';
      dh += '<div class="req-detail-panel">';

      dh += '<div class="req-detail-section">';
      dh += '<h5 class="req-detail-label">정의</h5>';
      dh += '<div class="req-detail-text">' + (req.definition ? escapeHtml(req.definition) : '<span class="req-detail-empty">정의 없음</span>') + '</div>';
      dh += '</div>';

      dh += '<div class="req-detail-section">';
      dh += '<h5 class="req-detail-label">세부내용</h5>';
      dh += '<div class="req-detail-text">' + (req.detail ? escapeHtml(req.detail) : '<span class="req-detail-empty">세부내용 없음</span>') + '</div>';
      dh += '</div>';

      if (req.output_info) {
        dh += '<div class="req-detail-section">';
        dh += '<h5 class="req-detail-label">산출정보</h5>';
        dh += '<div class="req-detail-text">' + escapeHtml(req.output_info) + '</div>';
        dh += '</div>';
      }

      if (req.related_reqs) {
        dh += '<div class="req-detail-section">';
        dh += '<h5 class="req-detail-label">관련 요구사항</h5>';
        dh += '<div class="req-detail-text">' + escapeHtml(req.related_reqs) + '</div>';
        dh += '</div>';
      }

      dh += '</div></td></tr>';

      row.classList.add('is-expanded');
      row.insertAdjacentHTML('afterend', dh);
    });

    /* ── 필터 + 검색 + 정렬 적용 ── */
    function applyFilter() {
      var filtered = [];
      var searchLower = currentSearch.toLowerCase();

      for (var i = 0; i < requirements.length; i++) {
        var req = requirements[i];
        var matchCategory = (currentCategory === 'all') || (req.category === currentCategory);
        var matchMethod   = (currentMethod === 'all') || (req.parse_method === currentMethod);
        var matchMissing  = !missingOnly || (!req.detail || req.detail.trim() === '');
        var matchSearch   = !currentSearch ||
          (req.id || '').toLowerCase().indexOf(searchLower) !== -1 ||
          (req.name || '').toLowerCase().indexOf(searchLower) !== -1 ||
          (req.definition || '').toLowerCase().indexOf(searchLower) !== -1;

        if (matchCategory && matchMethod && matchMissing && matchSearch) {
          filtered.push(req);
        }
      }

      /* 정렬 */
      if (currentSort === 'category') {
        filtered.sort(function (a, b) { return (a.category || '').localeCompare(b.category || ''); });
      } else if (currentSort === 'name') {
        filtered.sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); });
      }
      /* 'id' = 기본 순서 (파서 정렬 유지) */

      /* 테이블 리렌더 */
      var rowsHtml = '';
      for (var j = 0; j < filtered.length; j++) {
        rowsHtml += buildReqRow(filtered[j], classMap, codeMap);
      }
      tableBody.innerHTML = rowsHtml;

      if (currentSearch) highlightSearch(tableBody, currentSearch);

      var hasResults = filtered.length > 0;
      if (tableWrap) tableWrap.hidden = !hasResults;
      if (emptyResult) emptyResult.hidden = hasResults;

      var isFiltered = currentCategory !== 'all' || currentMethod !== 'all' || missingOnly || currentSearch;
      if (filteredCount) filteredCount.hidden = !isFiltered;
      if (filteredNum) filteredNum.textContent = String(filtered.length);
    }

    /* ── 분류 뱃지 클릭 ── */
    if (badgeList) {
      badgeList.addEventListener('click', function (e) {
        var btn = e.target.closest('.req-cat-badge-btn');
        if (!btn) return;
        currentCategory = btn.getAttribute('data-category') || 'all';
        var allBtns = badgeList.querySelectorAll('.req-cat-badge-btn');
        for (var b = 0; b < allBtns.length; b++) {
          allBtns[b].classList.toggle('is-active', allBtns[b] === btn);
        }
        applyFilter();
      });
    }

    /* 뱃지 접기/펼치기 */
    if (badgeToggle && badgeList) {
      badgeToggle.addEventListener('click', function () {
        var hidden = !badgeList.hidden;
        badgeList.hidden = hidden;
        badgeToggle.textContent = hidden ? '펼치기' : '접기';
        badgeToggle.setAttribute('aria-expanded', String(!hidden));
      });
    }

    /* ── 파싱방식 필터 ── */
    if (methodFilter) {
      methodFilter.addEventListener('change', function () {
        currentMethod = methodFilter.value;
        applyFilter();
      });
    }

    /* ── 미완성만 ── */
    if (missingCheck) {
      missingCheck.addEventListener('change', function () {
        missingOnly = missingCheck.checked;
        applyFilter();
      });
    }

    /* ── 정렬 ── */
    if (sortSelect) {
      sortSelect.addEventListener('change', function () {
        currentSort = sortSelect.value;
        applyFilter();
      });
    }

    /* ── 검색 (디바운스) ── */
    if (searchInput) {
      var searchTimer = null;
      searchInput.addEventListener('input', function () {
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          currentSearch = searchInput.value.trim();
          applyFilter();
        }, 250);
      });
    }
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
  function populateTocTab(tocData, requirements) {
    var tocContent = document.getElementById('tabpanel-toc-content');
    var tocEmpty   = document.getElementById('tabpanel-toc-empty');
    if (!tocContent) return;

    /* TocEditor가 있으면 항상 위임 (빈 배열이든 데이터든)
       TocEditor.init() 내부에서 서버 TOC를 비동기 로드 후 empty 상태를 직접 관리 */
    if (typeof window.TocEditor !== 'undefined') {
      if (tocEmpty) tocEmpty.hidden = true;   /* TocEditor가 모든 상태를 관리 */
      window.TocEditor.init('tabpanel-toc-content', tocData || [], requirements || []);
      return;
    }

    /* TocEditor가 없는 경우 폴백 */
    if (!tocData || tocData.length === 0) {
      if (tocEmpty) tocEmpty.hidden = false;
    } else {
      if (tocEmpty) tocEmpty.hidden = true;
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
