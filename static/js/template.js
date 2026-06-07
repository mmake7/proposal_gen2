/* ============================================================
   PowerPoint Template Manager
   장(Chapter) 기반 슬라이드 구조 분석 · 업로드 · 상세보기
   ============================================================ */
(function () {
  'use strict';

  var API = '/api/templates';

  /* ── DOM ── */
  var section       = document.getElementById('template-section');
  var dropzone      = document.getElementById('tpl-dropzone');
  var fileInput     = document.getElementById('tpl-file-input');
  var promptEl      = document.getElementById('tpl-upload-prompt');
  var previewEl     = document.getElementById('tpl-upload-preview');
  var fileNameEl    = document.getElementById('tpl-file-name');
  var fileSizeEl    = document.getElementById('tpl-file-size');
  var removeBtn     = document.getElementById('tpl-remove-btn');
  var uploadBtn     = document.getElementById('tpl-upload-btn');
  var progressEl    = document.getElementById('tpl-upload-progress');
  var listEl        = document.getElementById('tpl-list');
  var listEmptyEl   = document.getElementById('tpl-list-empty');
  var modal         = document.getElementById('tpl-detail-modal');
  var modalBody     = document.getElementById('tpl-detail-content');
  var modalClose    = document.getElementById('tpl-detail-close');

  if (!section || !dropzone) return;

  var MAX_SIZE = 50 * 1024 * 1024;
  var selectedFile = null;

  /* ============================================================
     Utilities
     ============================================================ */
  function fmtSize(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }

  function fmtDate(iso) {
    var d = new Date(iso);
    return d.getFullYear() + '.' +
      String(d.getMonth() + 1).padStart(2, '0') + '.' +
      String(d.getDate()).padStart(2, '0') + ' ' +
      String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0');
  }

  /* escapeHtml·esc·toast → util.js 전역 사용 */


  /* ============================================================
     File Selection & Drag-Drop
     ============================================================ */
  function pick(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pptx')) {
      toast('PPTX 파일만 업로드할 수 있습니다.', 'error'); return;
    }
    if (file.size > MAX_SIZE) {
      toast('파일 크기가 50MB를 초과했습니다.', 'error'); return;
    }
    selectedFile = file;
    fileNameEl.textContent = file.name;
    fileSizeEl.textContent = fmtSize(file.size);
    promptEl.hidden = true;
    previewEl.hidden = false;
    uploadBtn.disabled = false;
    dropzone.classList.add('has-file');
  }

  function clear() {
    selectedFile = null;
    fileInput.value = '';
    promptEl.hidden = false;
    previewEl.hidden = true;
    uploadBtn.disabled = true;
    dropzone.classList.remove('has-file');
  }

  dropzone.addEventListener('click', function (e) {
    if (e.target.closest('button') || selectedFile) return;
    fileInput.click();
  });
  fileInput.addEventListener('change', function () {
    if (fileInput.files.length) pick(fileInput.files[0]);
  });
  dropzone.addEventListener('dragover', function (e) {
    e.preventDefault(); dropzone.classList.add('is-dragover');
  });
  dropzone.addEventListener('dragleave', function () {
    dropzone.classList.remove('is-dragover');
  });
  dropzone.addEventListener('drop', function (e) {
    e.preventDefault(); dropzone.classList.remove('is-dragover');
    if (e.dataTransfer.files.length) pick(e.dataTransfer.files[0]);
  });
  if (removeBtn) removeBtn.addEventListener('click', function (e) {
    e.stopPropagation(); clear();
  });

  /* ============================================================
     Upload
     ============================================================ */
  if (uploadBtn) uploadBtn.addEventListener('click', function () {
    if (selectedFile) doUpload(selectedFile);
  });

  function doUpload(file) {
    var fd = new FormData();
    fd.append('file', file);
    uploadBtn.disabled = true;
    uploadBtn.classList.add('is-loading');
    if (progressEl) progressEl.hidden = false;

    var xhr = new XMLHttpRequest();
    xhr.open('POST', API + '/upload');
    xhr.timeout = 120000;
    xhr.responseType = 'json';

    xhr.upload.addEventListener('progress', function (e) {
      if (e.lengthComputable && progressEl) {
        var fill = progressEl.querySelector('.tpl-progress-fill');
        if (fill) fill.style.width = Math.round(e.loaded / e.total * 100) + '%';
      }
    });

    xhr.addEventListener('load', function () {
      uploadBtn.classList.remove('is-loading');
      if (progressEl) progressEl.hidden = true;
      if (xhr.status >= 200 && xhr.status < 300) {
        toast('템플릿이 업로드되었습니다.', 'success');
        clear();
        loadList();
      } else {
        var msg = '업로드에 실패했습니다.';
        try { msg = (typeof xhr.response === 'object' ? xhr.response : JSON.parse(xhr.responseText)).error || msg; } catch (e) {}
        toast(msg, 'error');
        uploadBtn.disabled = false;
      }
    });
    xhr.addEventListener('error', function () {
      uploadBtn.classList.remove('is-loading');
      if (progressEl) progressEl.hidden = true;
      toast('네트워크 오류가 발생했습니다.', 'error');
      uploadBtn.disabled = false;
    });
    xhr.addEventListener('timeout', function () {
      uploadBtn.classList.remove('is-loading');
      if (progressEl) progressEl.hidden = true;
      toast('업로드 시간이 초과되었습니다.', 'error');
      uploadBtn.disabled = false;
    });
    xhr.send(fd);
  }

  /* ============================================================
     Template List
     ============================================================ */
  function loadList() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) renderList(xhr.response || []);
    });
    xhr.send();
  }

  function renderList(items) {
    if (!listEl) return;
    if (!items.length) {
      listEl.innerHTML = '';
      if (listEmptyEl) listEmptyEl.hidden = false;
      return;
    }
    if (listEmptyEl) listEmptyEl.hidden = true;

    var h = '';
    for (var i = 0; i < items.length; i++) {
      var t = items[i];
      var chapters = t.chapter_titles || [];
      var chapterHint = chapters.length
        ? chapters.slice(0, 3).join(', ') + (chapters.length > 3 ? ' 외 ' + (chapters.length - 3) + '개' : '')
        : '';

      h += '<div class="tpl-card" data-id="' + esc(t.id) + '">' +
        '<div class="tpl-card-icon" aria-hidden="true">' +
          '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>' +
        '</div>' +
        '<div class="tpl-card-body">' +
          '<h4 class="tpl-card-title">' + esc(t.name) + '</h4>' +
          '<div class="tpl-card-meta">' +
            '<span class="tpl-card-meta-item">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>' +
              ' ' + (t.slide_count || 0) + '슬라이드' +
            '</span>' +
            '<span class="tpl-card-meta-item">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>' +
              ' ' + (t.chapter_count || 0) + '개 장' +
            '</span>' +
            '<span class="tpl-card-meta-item">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' +
              ' ' + fmtDate(t.uploaded_at) +
            '</span>' +
          '</div>' +
          (chapterHint ? '<p class="tpl-card-chapters">' + esc(chapterHint) + '</p>' : '') +
        '</div>' +
        '<div class="tpl-card-actions">' +
          '<button type="button" class="btn btn-ghost btn-sm tpl-view-btn" data-id="' + esc(t.id) + '" title="상세보기">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
          '</button>' +
          '<button type="button" class="btn btn-ghost btn-sm tpl-delete-btn" data-id="' + esc(t.id) + '" title="삭제">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
          '</button>' +
        '</div>' +
      '</div>';
    }
    listEl.innerHTML = h;

    /* bind events */
    listEl.querySelectorAll('.tpl-view-btn').forEach(function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); openDetail(this.dataset.id); });
    });
    listEl.querySelectorAll('.tpl-delete-btn').forEach(function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); doDelete(this.dataset.id); });
    });
    listEl.querySelectorAll('.tpl-card').forEach(function (c) {
      c.addEventListener('click', function () { openDetail(this.dataset.id); });
    });
  }

  /* ============================================================
     Delete
     ============================================================ */
  function doDelete(id) {
    if (!confirm('이 템플릿을 삭제하시겠습니까?')) return;
    var xhr = new XMLHttpRequest();
    xhr.open('DELETE', API + '/' + id);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) { toast('삭제되었습니다.', 'success'); loadList(); }
      else toast('삭제에 실패했습니다.', 'error');
    });
    xhr.addEventListener('error', function () { toast('네트워크 오류', 'error'); });
    xhr.send();
  }

  /* ============================================================
     Detail Modal
     ============================================================ */
  function openDetail(id) {
    if (!modal || !modalBody) return;
    modalBody.innerHTML =
      '<div class="tpl-detail-loading">' +
        '<div class="tpl-detail-spinner"></div>' +
        '<p>슬라이드 구조를 분석하는 중...</p>' +
      '</div>';
    modal.hidden = false;
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';

    var xhr = new XMLHttpRequest();
    xhr.open('GET', API + '/' + id);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) renderDetail(xhr.response);
      else modalBody.innerHTML = '<p class="tpl-detail-error">상세정보를 불러올 수 없습니다.</p>';
    });
    xhr.addEventListener('error', function () {
      modalBody.innerHTML = '<p class="tpl-detail-error">네트워크 오류가 발생했습니다.</p>';
    });
    xhr.send();
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    setTimeout(function () { modal.hidden = true; }, 200);
  }

  if (modalClose) modalClose.addEventListener('click', closeModal);
  if (modal) {
    modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modal.hidden) closeModal(); });
  }

  /* ============================================================
     Render Detail – Chapter Tree
     ============================================================ */
  function renderDetail(data) {
    if (!modalBody) return;
    var a = data.analysis || {};
    var chapters = a.chapters || [];
    var tplId = data.id;

    var fontSummary = a.font_summary || {};

    var h = '<div class="tpl-detail-header">' +
      '<h3 class="tpl-detail-title">' + esc(data.name) + '</h3>' +
      '<div class="tpl-detail-meta">' +
        '<span>' + (data.slide_count || 0) + '개 슬라이드</span>' +
        '<span>' + (data.chapter_count || chapters.length) + '개 장</span>' +
        '<span>' + (a.slide_width_cm || '–') + ' × ' + (a.slide_height_cm || '–') + ' cm</span>' +
        '<span>' + fmtDate(data.uploaded_at) + '</span>' +
      '</div>';

    /* Font summary tags */
    var uFonts = fontSummary.unique_fonts || [];
    if (uFonts.length) {
      h += '<div class="tpl-detail-fonts">' +
        '<span class="tpl-detail-fonts-label">사용 폰트:</span>';
      for (var fi = 0; fi < uFonts.length; fi++) {
        h += '<span class="tpl-font-tag">' + esc(uFonts[fi]) + '</span>';
      }
      h += '</div>';
    }

    h += '</div>';

    /* Chapter accordion tree */
    h += '<div class="tpl-chapters">';
    for (var ci = 0; ci < chapters.length; ci++) {
      var ch = chapters[ci];
      var slides = ch.slides || [];
      var isOpen = ci === 0 ? ' is-open' : '';

      h += '<div class="tpl-chapter' + isOpen + '" data-chapter="' + ci + '">' +
        '<button type="button" class="tpl-chapter-header" aria-expanded="' + (ci === 0 ? 'true' : 'false') + '">' +
          '<span class="tpl-chapter-toggle" aria-hidden="true">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>' +
          '</span>' +
          '<span class="tpl-chapter-num">' + (ci + 1) + '</span>' +
          '<span class="tpl-chapter-title">' + esc(ch.title) + '</span>' +
          '<span class="tpl-chapter-badge">' + slides.length + '슬라이드</span>' +
        '</button>' +
        '<div class="tpl-chapter-body">';

      for (var si = 0; si < slides.length; si++) {
        var s = slides[si];
        var phs = s.placeholders || [];
        var isDivider = s.is_chapter_divider;

        h += '<div class="tpl-slide' + (isDivider ? ' is-divider' : '') + '">' +
          '<div class="tpl-slide-header">' +
            '<div class="tpl-slide-thumb" data-tpl="' + esc(tplId) + '" data-slide="' + s.index + '">' +
              '<div class="tpl-slide-thumb-placeholder">' +
                '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="3" width="20" height="14" rx="2"/></svg>' +
              '</div>' +
            '</div>' +
            '<div class="tpl-slide-info">' +
              '<div class="tpl-slide-info-top">' +
                '<span class="tpl-slide-num">' + s.index + '</span>' +
                '<span class="tpl-slide-layout">' + esc(s.layout_name || '기본 레이아웃') + '</span>' +
                (isDivider ? '<span class="tpl-slide-divider-tag">장 구분</span>' : '') +
              '</div>' +
              '<div class="tpl-slide-info-bottom">' +
                '<span class="tpl-slide-ph-count">' + phs.length + '개 플레이스홀더</span>' +
              '</div>' +
            '</div>' +
          '</div>';

        /* Placeholders */
        if (phs.length > 0) {
          h += '<div class="tpl-slide-phs">';
          for (var pi = 0; pi < phs.length; pi++) {
            var ph = phs[pi];
            h += '<div class="tpl-ph">' +
              '<div class="tpl-ph-row">' +
                '<span class="tpl-ph-idx" title="Placeholder Index">#' + ph.idx + '</span>' +
                '<span class="tpl-ph-name">' + esc(ph.name) + '</span>' +
                '<span class="tpl-ph-type">' + esc(ph.type) + '</span>' +
                '<span class="tpl-ph-size">' +
                  (ph.left_cm != null ? ph.left_cm + ',' + ph.top_cm + ' / ' : '') +
                  (ph.width_cm || '–') + '×' + (ph.height_cm || '–') + 'cm' +
                '</span>' +
              '</div>';
            if (ph.text) {
              h += '<p class="tpl-ph-text">' + esc(ph.text.substring(0, 200)) + '</p>';
            }
            h += '</div>';
          }
          h += '</div>';
        }

        /* Font info per slide */
        var slideFonts = s.fonts || [];
        if (slideFonts.length > 0) {
          h += '<div class="tpl-slide-fonts">' +
            '<p class="tpl-slide-fonts-title">사용 폰트</p>';
          for (var ffi = 0; ffi < slideFonts.length; ffi++) {
            var ff = slideFonts[ffi];
            h += '<span class="tpl-font-tag' + (ff.is_bold ? ' tpl-font-tag-bold' : '') + '">';
            if (ff.color) {
              h += '<span class="tpl-font-tag-color" style="background-color:' + esc(ff.color) + '"></span>';
            }
            h += esc(ff.font_name);
            if (ff.size_pt) h += ' ' + ff.size_pt + 'pt';
            h += '</span>';
          }
          h += '</div>';
        }

        /* Text content toggle */
        if (s.text_content && !isDivider) {
          h += '<details class="tpl-slide-text">' +
            '<summary>텍스트 내용 보기</summary>' +
            '<pre class="tpl-slide-text-pre">' + esc(s.text_content.substring(0, 1000)) + '</pre>' +
          '</details>';
        }

        h += '</div>'; /* .tpl-slide */
      }

      h += '</div></div>'; /* .tpl-chapter-body, .tpl-chapter */
    }
    h += '</div>'; /* .tpl-chapters */

    modalBody.innerHTML = h;

    /* Chapter accordion toggle */
    modalBody.querySelectorAll('.tpl-chapter-header').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var chapter = this.parentElement;
        var isOpen = chapter.classList.toggle('is-open');
        this.setAttribute('aria-expanded', String(isOpen));
      });
    });

    /* Lazy-load thumbnails */
    lazyLoadThumbnails();
  }

  /* ============================================================
     Lazy Thumbnail Loading
     ============================================================ */
  function lazyLoadThumbnails() {
    var thumbs = modalBody.querySelectorAll('.tpl-slide-thumb[data-tpl]');
    if (!thumbs.length) return;

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            loadThumb(entry.target);
            observer.unobserve(entry.target);
          }
        });
      }, { root: modalBody, rootMargin: '100px' });
      thumbs.forEach(function (el) { observer.observe(el); });
    } else {
      /* fallback: load first 10 immediately */
      for (var i = 0; i < Math.min(thumbs.length, 10); i++) {
        loadThumb(thumbs[i]);
      }
    }
  }

  function loadThumb(el) {
    var tplId = el.dataset.tpl;
    var slideNum = el.dataset.slide;
    if (!tplId || !slideNum) return;

    var img = new Image();
    img.className = 'tpl-slide-thumb-img';
    img.alt = '슬라이드 ' + slideNum + ' 미리보기';
    img.src = API + '/' + tplId + '/slides/' + slideNum + '/thumbnail?w=240';
    img.addEventListener('load', function () {
      el.innerHTML = '';
      el.appendChild(img);
    });
    /* on error: keep placeholder icon */
  }

  /* ============================================================
     Nav link binding
     ============================================================ */
  document.querySelectorAll('.header-nav-link').forEach(function (link) {
    if (link.textContent.trim() === '템플릿 관리') {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        section.scrollIntoView({ behavior: 'smooth' });
        document.querySelectorAll('.header-nav-link').forEach(function (l) {
          l.classList.remove('active'); l.removeAttribute('aria-current');
        });
        this.classList.add('active');
        this.setAttribute('aria-current', 'page');
      });
    }
  });

  /* ── Init ── */
  loadList();
})();
