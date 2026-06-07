/* ============================================================
   Proposal Wizard – 4-Step Proposal Generation Flow
   제안서 작성 마법사 (템플릿 선택 → 매핑 → 콘텐츠 생성 → 다운로드)
   ============================================================ */
(function () {
  'use strict';

  var API_TEMPLATES = '/api/templates';
  var API_MAP = '/api/proposal/map';
  var API_GENERATE = '/api/proposal/generate';
  var API_CONTENT = '/api/proposal/content';
  var API_EXPORT = '/api/proposal/export';

  var section = document.getElementById('proposal-section');
  if (!section) return;

  var currentStep = 0;
  var selectedTemplateId = null;
  var mappingData = null;
  var generatedContent = null;

  /* ── Utilities ── */
  /* escapeHtml·esc·toast → util.js 전역 사용 */


  /* ============================================================
     Step Navigation
     ============================================================ */
  function showStep(step) {
    currentStep = step;
    var panels = section.querySelectorAll('.proposal-step-panel');
    for (var i = 0; i < panels.length; i++) {
      panels[i].hidden = (i !== step);
    }

    /* Update step indicators */
    var dots = section.querySelectorAll('.proposal-step-dot');
    for (var j = 0; j < dots.length; j++) {
      dots[j].classList.toggle('is-active', j === step);
      dots[j].classList.toggle('is-done', j < step);
    }

    /* Update nav buttons */
    var prevBtn = document.getElementById('proposal-prev-btn');
    var nextBtn = document.getElementById('proposal-next-btn');
    if (prevBtn) prevBtn.hidden = (step === 0);
    if (nextBtn) {
      nextBtn.hidden = (step === 3);
      nextBtn.textContent = step === 2 ? '콘텐츠 생성 시작' : '다음';
    }
  }

  function nextStep() {
    if (currentStep === 0) {
      /* Step 0 → 1: Template selected, do mapping */
      if (!selectedTemplateId) {
        toast('템플릿을 선택해주세요.', 'error');
        return;
      }
      doMapping();
    } else if (currentStep === 1) {
      /* Step 1 → 2: Mapping confirmed, show generate panel */
      showStep(2);
    } else if (currentStep === 2) {
      /* Step 2: Start content generation */
      doGenerate();
    }
  }

  function prevStep() {
    if (currentStep > 0) {
      showStep(currentStep - 1);
    }
  }

  /* ============================================================
     Step 0: Template Selection
     ============================================================ */
  function loadTemplates() {
    var grid = document.getElementById('proposal-template-grid');
    if (!grid) return;
    grid.innerHTML = '<p style="color:var(--krds-text-tertiary);">템플릿 목록을 불러오는 중...</p>';

    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_TEMPLATES);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        var templates = xhr.response || [];
        if (templates.length === 0) {
          grid.innerHTML = '<p style="color:var(--krds-text-tertiary);">업로드된 템플릿이 없습니다. 먼저 PPTX 템플릿을 업로드해주세요.</p>';
          return;
        }
        renderTemplateGrid(templates, grid);
      } else {
        grid.innerHTML = '<p style="color:var(--krds-error);">템플릿 목록 로드에 실패했습니다.</p>';
      }
    });
    xhr.send();
  }

  function renderTemplateGrid(templates, grid) {
    var h = '';
    for (var i = 0; i < templates.length; i++) {
      var t = templates[i];
      var isSelected = selectedTemplateId === t.id;
      h += '<div class="proposal-template-card' + (isSelected ? ' is-selected' : '') + '" data-id="' + esc(t.id) + '">';
      h += '<div class="proposal-template-card-header">';
      h += '<span class="proposal-template-name">' + esc(t.filename) + '</span>';
      h += '</div>';
      h += '<div class="proposal-template-card-meta">';
      h += '<span>' + (t.slide_count || 0) + '장</span>';
      h += '<span>' + (t.chapter_count || 0) + '개 챕터</span>';
      if (t.fonts_used && t.fonts_used.length > 0) {
        h += '<span>' + t.fonts_used.slice(0, 3).join(', ') + '</span>';
      }
      h += '</div>';
      h += '</div>';
    }
    grid.innerHTML = h;

    /* Bind clicks */
    var cards = grid.querySelectorAll('.proposal-template-card');
    for (var c = 0; c < cards.length; c++) {
      cards[c].addEventListener('click', function () {
        selectedTemplateId = this.dataset.id;
        var all = grid.querySelectorAll('.proposal-template-card');
        for (var a = 0; a < all.length; a++) {
          all[a].classList.toggle('is-selected', all[a].dataset.id === selectedTemplateId);
        }
      });
    }
  }

  /* ============================================================
     Step 1: Mapping
     ============================================================ */
  function doMapping() {
    var mappingPanel = document.getElementById('proposal-mapping-panel');
    if (mappingPanel) mappingPanel.innerHTML = '<p style="color:var(--krds-text-tertiary);">매핑 중...</p>';
    showStep(1);

    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_MAP);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        mappingData = xhr.response || [];
        renderMapping(mappingData);
      } else {
        var msg = '매핑에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        if (mappingPanel) mappingPanel.innerHTML = '<p style="color:var(--krds-error);">' + esc(msg) + '</p>';
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify({ template_id: selectedTemplateId }));
  }

  function renderMapping(data) {
    var panel = document.getElementById('proposal-mapping-panel');
    if (!panel) return;

    var h = '<table class="proposal-mapping-table">';
    h += '<thead><tr>';
    h += '<th>목차 항목</th>';
    h += '<th>템플릿 챕터</th>';
    h += '<th>유사도</th>';
    h += '<th>상태</th>';
    h += '</tr></thead><tbody>';

    for (var i = 0; i < data.length; i++) {
      var m = data[i];
      var scoreClass = m.score >= 0.7 ? 'high' : (m.score >= 0.4 ? 'medium' : 'low');
      h += '<tr class="proposal-mapping-row">';
      h += '<td>' + esc(m.toc_title) + '</td>';
      h += '<td>' + (m.chapter_title ? esc(m.chapter_title) : '<span style="color:var(--krds-text-quaternary)">매핑 없음</span>') + '</td>';
      h += '<td><span class="proposal-mapping-score is-' + scoreClass + '">' + Math.round(m.score * 100) + '%</span></td>';
      h += '<td><span class="proposal-mapping-status is-' + m.status + '">' + getStatusLabel(m.status) + '</span></td>';
      h += '</tr>';
    }

    h += '</tbody></table>';
    panel.innerHTML = h;
  }

  function getStatusLabel(status) {
    switch (status) {
      case 'matched': return '자동 매핑';
      case 'manual': return '수동 지정';
      case 'unmatched': return '미매핑';
      default: return status;
    }
  }

  /* ============================================================
     Step 2: Content Generation
     ============================================================ */
  function doGenerate() {
    var panel = document.getElementById('proposal-generate-panel');
    if (panel) {
      panel.innerHTML = '<div class="proposal-progress-wrapper">' +
        '<div class="proposal-progress-spinner"></div>' +
        '<p style="color:var(--krds-text-secondary);">AI가 제안서 콘텐츠를 생성하고 있습니다...</p>' +
        '<p style="font-size:var(--krds-font-size-xs);color:var(--krds-text-tertiary);">이 과정은 TOC 항목 수에 따라 수 분이 걸릴 수 있습니다.</p>' +
        '</div>';
    }

    var nextBtn = document.getElementById('proposal-next-btn');
    if (nextBtn) nextBtn.hidden = true;

    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_GENERATE);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.timeout = 600000; /* 10 minutes */
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        generatedContent = xhr.response;
        renderGeneratedContent(generatedContent);
        toast('콘텐츠 생성이 완료되었습니다!', 'success');
        /* Auto-advance to step 3 */
        showStep(3);
      } else {
        var msg = '콘텐츠 생성에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        if (panel) panel.innerHTML = '<p style="color:var(--krds-error);">' + esc(msg) + '</p>';
        toast(msg, 'error');
        if (nextBtn) { nextBtn.hidden = false; nextBtn.textContent = '다시 시도'; }
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
      if (panel) panel.innerHTML = '<p style="color:var(--krds-error);">네트워크 오류가 발생했습니다.</p>';
      if (nextBtn) { nextBtn.hidden = false; nextBtn.textContent = '다시 시도'; }
    });
    xhr.addEventListener('timeout', function () {
      toast('요청 시간이 초과되었습니다.', 'error');
      if (panel) panel.innerHTML = '<p style="color:var(--krds-error);">콘텐츠 생성 시간이 초과되었습니다.</p>';
      if (nextBtn) { nextBtn.hidden = false; nextBtn.textContent = '다시 시도'; }
    });
    xhr.send();
  }

  function renderGeneratedContent(data) {
    var panel = document.getElementById('proposal-generate-panel');
    if (!panel) return;

    var sections = data.sections || {};
    var progress = data.progress || {};
    var keys = Object.keys(sections);

    var h = '<div class="proposal-content-summary">';
    h += '<span>' + keys.length + '개 섹션 생성 완료</span>';
    h += '</div>';

    h += '<div class="proposal-content-preview">';
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      var sec = sections[key];
      h += '<div class="proposal-preview-item">';
      h += '<div class="proposal-preview-title">' + esc(sec.title) + '</div>';
      var preview = (sec.content_text || '').substring(0, 200);
      h += '<div class="proposal-preview-text">' + esc(preview) + (sec.content_text && sec.content_text.length > 200 ? '...' : '') + '</div>';
      if (sec.key_phrases && sec.key_phrases.length > 0) {
        h += '<div class="proposal-preview-tags">';
        for (var k = 0; k < sec.key_phrases.length && k < 5; k++) {
          h += '<span class="proposal-preview-tag">' + esc(sec.key_phrases[k]) + '</span>';
        }
        h += '</div>';
      }
      h += '</div>';
    }
    h += '</div>';

    panel.innerHTML = h;
  }

  /* ============================================================
     Step 3: Download
     ============================================================ */
  function doExport() {
    var exportBtn = document.getElementById('proposal-export-btn');
    if (exportBtn) {
      exportBtn.disabled = true;
      exportBtn.classList.add('is-loading');
    }

    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_EXPORT);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'blob';
    xhr.addEventListener('load', function () {
      if (exportBtn) {
        exportBtn.disabled = false;
        exportBtn.classList.remove('is-loading');
      }

      if (xhr.status === 200) {
        /* Trigger download */
        var blob = xhr.response;
        var contentDisposition = xhr.getResponseHeader('Content-Disposition');
        var filename = 'proposal.pptx';
        if (contentDisposition) {
          var match = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^;"]+)/);
          if (match) filename = decodeURIComponent(match[1].replace(/"/g, ''));
        }

        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        toast('제안서 PPTX 파일이 다운로드되었습니다!', 'success');
      } else {
        toast('PPTX 생성에 실패했습니다.', 'error');
      }
    });
    xhr.addEventListener('error', function () {
      if (exportBtn) {
        exportBtn.disabled = false;
        exportBtn.classList.remove('is-loading');
      }
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify({ template_id: selectedTemplateId }));
  }

  /* ============================================================
     Event Binding
     ============================================================ */
  /* Nav buttons */
  var prevBtn = document.getElementById('proposal-prev-btn');
  var nextBtn = document.getElementById('proposal-next-btn');
  var exportBtn = document.getElementById('proposal-export-btn');

  if (prevBtn) prevBtn.addEventListener('click', prevStep);
  if (nextBtn) nextBtn.addEventListener('click', nextStep);
  if (exportBtn) exportBtn.addEventListener('click', doExport);

  /* Entry points */
  var proceedBtn = document.getElementById('analysis-proceed-btn');
  if (proceedBtn) {
    proceedBtn.addEventListener('click', function () {
      section.hidden = false;
      section.scrollIntoView({ behavior: 'smooth' });
      showStep(0);
      loadTemplates();
    });
  }

  /* Nav link "제안서 작성" */
  document.querySelectorAll('.header-nav-link').forEach(function (link) {
    if (link.textContent.trim() === '제안서 작성') {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        section.hidden = false;
        section.scrollIntoView({ behavior: 'smooth' });
        document.querySelectorAll('.header-nav-link').forEach(function (l) {
          l.classList.remove('active'); l.removeAttribute('aria-current');
        });
        this.classList.add('active');
        this.setAttribute('aria-current', 'page');
        if (!selectedTemplateId) {
          showStep(0);
          loadTemplates();
        }
      });
    }
  });

  /* Init: hide section by default */
  section.hidden = true;

})();
