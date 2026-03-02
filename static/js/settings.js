/* ============================================================
   Font Preset & Settings Manager
   폰트 프리셋 CRUD + 적용 모드 설정
   ============================================================ */
(function () {
  'use strict';

  var API_PRESETS  = '/api/fonts/presets';
  var API_SETTINGS = '/api/fonts/settings';

  /* ── DOM ── */
  var section        = document.getElementById('settings-section');
  var modeOptions    = document.querySelectorAll('.font-mode-option');
  var presetsGrid    = document.getElementById('font-presets-grid');
  var addPresetBtn   = document.getElementById('font-add-preset-btn');
  var formWrap       = document.getElementById('font-preset-form');
  var formTitle      = document.getElementById('font-preset-form-title');
  var formName       = document.getElementById('font-form-name');
  var formCancel     = document.getElementById('font-form-cancel');
  var formSubmit     = document.getElementById('font-form-submit');

  if (!section) return;

  var currentSettings = { mode: 'template_keep', active_preset_id: null };
  var presets = [];
  var editingPresetId = null;

  /* ============================================================
     Utilities
     ============================================================ */
  function esc(s) {
    if (!s) return '';
    var el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
  }

  function toast(msg, type) {
    var c = document.getElementById('toast-container');
    if (!c) return;
    var t = document.createElement('div');
    t.className = 'toast toast--' + (type || 'info');
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(function () { t.classList.add('is-visible'); }, 10);
    setTimeout(function () {
      t.classList.remove('is-visible');
      setTimeout(function () { t.remove(); }, 300);
    }, 3000);
  }

  /* ============================================================
     Settings: Load & Update Mode
     ============================================================ */
  function loadSettings() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_SETTINGS);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        currentSettings = xhr.response || currentSettings;
        renderMode();
      }
    });
    xhr.send();
  }

  function saveMode(mode) {
    var body = {
      mode: mode,
      active_preset_id: currentSettings.active_preset_id
    };
    var xhr = new XMLHttpRequest();
    xhr.open('PUT', API_SETTINGS);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        currentSettings = xhr.response;
        renderMode();
        toast('폰트 적용 모드가 변경되었습니다.', 'success');
      } else {
        toast('설정 변경에 실패했습니다.', 'error');
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify(body));
  }

  function renderMode() {
    modeOptions.forEach(function (opt) {
      var radio = opt.querySelector('input[type="radio"]');
      var isActive = radio && radio.value === currentSettings.mode;
      opt.classList.toggle('is-active', isActive);
      if (radio) radio.checked = isActive;
    });
  }

  /* ============================================================
     Presets: Load & Render
     ============================================================ */
  function loadPresets() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_PRESETS);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        presets = xhr.response || [];
        renderPresets();
      }
    });
    xhr.send();
  }

  function renderPresets() {
    if (!presetsGrid) return;
    if (!presets.length) {
      presetsGrid.innerHTML = '<p style="color:var(--krds-text-tertiary);font-size:var(--krds-font-size-sm);">등록된 프리셋이 없습니다.</p>';
      return;
    }

    var h = '';
    for (var i = 0; i < presets.length; i++) {
      var p = presets[i];
      var isActive = currentSettings.active_preset_id === p.id;
      var isBuiltin = p.builtin;

      h += '<div class="font-preset-card' +
        (isBuiltin ? ' is-builtin' : '') +
        (isActive ? ' is-active' : '') +
        '" data-id="' + esc(p.id) + '">';

      /* Header */
      h += '<div class="font-preset-card-header">' +
        '<span class="font-preset-name">' + esc(p.name) + '</span>' +
        '<div class="font-preset-actions">';

      if (isBuiltin) {
        h += '<span class="font-preset-badge">내장</span>';
      } else {
        h += '<button type="button" class="btn btn-ghost btn-sm font-edit-btn" data-id="' + esc(p.id) + '" title="수정">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
        '</button>' +
        '<button type="button" class="btn btn-ghost btn-sm font-delete-btn" data-id="' + esc(p.id) + '" title="삭제">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>';
      }

      h += '<button type="button" class="btn ' + (isActive ? 'btn-primary' : 'btn-secondary') + ' btn-sm font-select-btn" data-id="' + esc(p.id) + '">' +
        (isActive ? '선택됨' : '선택') +
      '</button>';

      h += '</div></div>';

      /* Preview */
      h += renderFontPreview(p);

      h += '</div>';
    }

    presetsGrid.innerHTML = h;
    bindPresetEvents();
  }

  function renderFontPreview(preset) {
    return '<div class="font-preview">' +
      renderPreviewItem('제목', preset.title_font) +
      renderPreviewItem('본문', preset.body_font) +
      renderPreviewItem('강조', preset.emphasis_font) +
    '</div>';
  }

  function renderPreviewItem(label, fontDef) {
    if (!fontDef) return '';
    var style = 'font-weight:' + (fontDef.bold ? 'bold' : 'normal') + ';';
    if (fontDef.color) style += 'color:' + fontDef.color + ';';

    return '<div class="font-preview-item">' +
      '<span class="font-preview-label">' + esc(label) + '</span>' +
      '<span class="font-preview-sample" style="' + style + '">' +
        esc(fontDef.name) + ' 샘플 텍스트' +
      '</span>' +
      '<span class="font-preview-meta">' + (fontDef.size_pt || '') + 'pt</span>' +
    '</div>';
  }

  /* ============================================================
     Preset Event Binding
     ============================================================ */
  function bindPresetEvents() {
    /* Select */
    presetsGrid.querySelectorAll('.font-select-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        selectPreset(this.dataset.id);
      });
    });

    /* Edit */
    presetsGrid.querySelectorAll('.font-edit-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        editPreset(this.dataset.id);
      });
    });

    /* Delete */
    presetsGrid.querySelectorAll('.font-delete-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        deletePreset(this.dataset.id);
      });
    });
  }

  /* ============================================================
     Preset Actions
     ============================================================ */
  function selectPreset(id) {
    var body = {
      mode: currentSettings.mode,
      active_preset_id: id
    };
    var xhr = new XMLHttpRequest();
    xhr.open('PUT', API_SETTINGS);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        currentSettings = xhr.response;
        renderPresets();
        toast('프리셋이 선택되었습니다.', 'success');
      } else {
        toast('프리셋 선택에 실패했습니다.', 'error');
      }
    });
    xhr.send(JSON.stringify(body));
  }

  function deletePreset(id) {
    if (!confirm('이 프리셋을 삭제하시겠습니까?')) return;

    var xhr = new XMLHttpRequest();
    xhr.open('DELETE', API_PRESETS + '/' + id);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        toast('프리셋이 삭제되었습니다.', 'success');
        loadPresets();
        loadSettings();
      } else {
        var msg = '삭제에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send();
  }

  function editPreset(id) {
    var preset = null;
    for (var i = 0; i < presets.length; i++) {
      if (presets[i].id === id) { preset = presets[i]; break; }
    }
    if (!preset) return;
    showForm(preset);
  }

  /* ============================================================
     Preset Form
     ============================================================ */
  function showForm(presetData) {
    if (!formWrap) return;
    editingPresetId = presetData ? presetData.id : null;
    formTitle.textContent = presetData ? '프리셋 수정' : '새 프리셋 만들기';

    if (presetData) {
      formName.value = presetData.name || '';
      fillFontRow('title', presetData.title_font);
      fillFontRow('body', presetData.body_font);
      fillFontRow('emphasis', presetData.emphasis_font);
    } else {
      formName.value = '';
      fillFontRow('title', { name: '', size_pt: 28, bold: true, color: '#1E293B' });
      fillFontRow('body', { name: '', size_pt: 11, bold: false, color: '#334155' });
      fillFontRow('emphasis', { name: '', size_pt: 13, bold: true, color: '#4F46E5' });
    }

    formWrap.hidden = false;
    formName.focus();
  }

  function hideForm() {
    if (!formWrap) return;
    formWrap.hidden = true;
    editingPresetId = null;
  }

  function fillFontRow(prefix, fontDef) {
    var nameEl  = document.getElementById('font-form-' + prefix + '-name');
    var sizeEl  = document.getElementById('font-form-' + prefix + '-size');
    var boldEl  = document.getElementById('font-form-' + prefix + '-bold');
    var colorEl = document.getElementById('font-form-' + prefix + '-color');
    if (nameEl)  nameEl.value  = (fontDef && fontDef.name) || '';
    if (sizeEl)  sizeEl.value  = (fontDef && fontDef.size_pt) || 11;
    if (boldEl)  boldEl.checked = !!(fontDef && fontDef.bold);
    if (colorEl) colorEl.value = (fontDef && fontDef.color) || '#334155';
  }

  function readFontRow(prefix) {
    var nameEl  = document.getElementById('font-form-' + prefix + '-name');
    var sizeEl  = document.getElementById('font-form-' + prefix + '-size');
    var boldEl  = document.getElementById('font-form-' + prefix + '-bold');
    var colorEl = document.getElementById('font-form-' + prefix + '-color');
    return {
      name:    nameEl  ? nameEl.value.trim()      : '',
      size_pt: sizeEl  ? parseFloat(sizeEl.value)  : 11,
      bold:    boldEl  ? boldEl.checked            : false,
      color:   colorEl ? colorEl.value             : '#334155'
    };
  }

  function submitForm() {
    var name = formName ? formName.value.trim() : '';
    if (!name) {
      toast('프리셋 이름을 입력해주세요.', 'error');
      return;
    }

    var payload = {
      name: name,
      title_font: readFontRow('title'),
      body_font: readFontRow('body'),
      emphasis_font: readFontRow('emphasis')
    };

    /* Validate font names */
    if (!payload.title_font.name || !payload.body_font.name || !payload.emphasis_font.name) {
      toast('모든 폰트 이름을 입력해주세요.', 'error');
      return;
    }

    var isEdit = !!editingPresetId;
    var method = isEdit ? 'PUT' : 'POST';
    var url    = isEdit ? API_PRESETS + '/' + editingPresetId : API_PRESETS;

    formSubmit.disabled = true;
    formSubmit.classList.add('is-loading');

    var xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      formSubmit.disabled = false;
      formSubmit.classList.remove('is-loading');
      if (xhr.status >= 200 && xhr.status < 300) {
        toast(isEdit ? '프리셋이 수정되었습니다.' : '프리셋이 생성되었습니다.', 'success');
        hideForm();
        loadPresets();
      } else {
        var msg = '저장에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      formSubmit.disabled = false;
      formSubmit.classList.remove('is-loading');
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify(payload));
  }

  /* ============================================================
     Event Binding
     ============================================================ */

  /* Mode radio cards */
  modeOptions.forEach(function (opt) {
    opt.addEventListener('click', function () {
      var radio = this.querySelector('input[type="radio"]');
      if (radio) {
        radio.checked = true;
        saveMode(radio.value);
      }
    });
  });

  /* Add preset button */
  if (addPresetBtn) {
    addPresetBtn.addEventListener('click', function () {
      showForm(null);
    });
  }

  /* Form cancel / submit */
  if (formCancel) formCancel.addEventListener('click', hideForm);
  if (formSubmit) formSubmit.addEventListener('click', submitForm);

  /* ============================================================
     Nav link binding (설정)
     ============================================================ */
  document.querySelectorAll('.header-nav-link').forEach(function (link) {
    if (link.textContent.trim() === '설정') {
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
  loadSettings();
  loadPresets();

  /* ============================================================
     TOC Template Management
     목차 템플릿 CRUD + 트리 편집기
     ============================================================ */

  var TOC_API = '/api/toc/templates';

  /* ── DOM ── */
  var tocTplGrid      = document.getElementById('toc-tpl-grid');
  var tocTplAddBtn    = document.getElementById('toc-tpl-add-btn');
  var tocTplEditor    = document.getElementById('toc-tpl-editor');
  var tocTplEdTitle   = document.getElementById('toc-tpl-editor-title');
  var tocTplFormName  = document.getElementById('toc-tpl-form-name');
  var tocTplTree      = document.getElementById('toc-tpl-tree');
  var tocTplAddL1     = document.getElementById('toc-tpl-add-l1');
  var tocTplCancel    = document.getElementById('toc-tpl-form-cancel');
  var tocTplSubmit    = document.getElementById('toc-tpl-form-submit');

  if (!tocTplGrid) return;

  var tocTemplates = [];
  var tocEditingId = null;   // null = 새 템플릿, string = 편집 중
  var tocEditItems = [];     // 편집 중인 목차 항목 (트리)

  /* ── Load & Render ── */
  function loadTocTemplates() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', TOC_API);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        tocTemplates = xhr.response || [];
        renderTocTemplates();
      }
    });
    xhr.send();
  }

  function renderTocTemplates() {
    if (!tocTplGrid) return;
    if (!tocTemplates.length) {
      tocTplGrid.innerHTML = '<p style="color:var(--krds-text-tertiary);font-size:var(--krds-font-size-sm);">등록된 목차 템플릿이 없습니다.</p>';
      return;
    }

    var h = '';
    for (var i = 0; i < tocTemplates.length; i++) {
      var t = tocTemplates[i];
      var isBuiltin = t.builtin;
      var itemCount = countTocItems(t.items || []);

      h += '<div class="toc-tpl-card' + (isBuiltin ? ' is-builtin' : '') + '" data-id="' + esc(t.id) + '">';

      /* Header */
      h += '<div class="toc-tpl-card-header">';
      h += '<span class="toc-tpl-name">' + esc(t.name) + '</span>';
      h += '<div class="toc-tpl-actions">';

      if (isBuiltin) {
        h += '<span class="toc-tpl-badge">내장</span>';
      }

      h += '<button type="button" class="btn btn-ghost btn-sm toc-tpl-edit-btn" data-id="' + esc(t.id) + '" title="편집">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
      '</button>';

      if (!isBuiltin) {
        h += '<button type="button" class="btn btn-ghost btn-sm toc-tpl-delete-btn" data-id="' + esc(t.id) + '" title="삭제">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>';
      }

      h += '</div></div>';

      /* Preview: item count + L1 titles */
      h += '<div class="toc-tpl-preview">';
      h += '<span class="toc-tpl-count">' + itemCount + '개 항목</span>';
      var l1Titles = (t.items || []).map(function (item) { return item.title; }).join(' / ');
      h += '<p class="toc-tpl-summary">' + esc(l1Titles) + '</p>';
      h += '</div>';

      h += '</div>';
    }

    tocTplGrid.innerHTML = h;
    bindTocTplEvents();
  }

  function countTocItems(items) {
    var n = 0;
    for (var i = 0; i < items.length; i++) {
      n += 1;
      if (items[i].children && items[i].children.length) {
        n += countTocItems(items[i].children);
      }
    }
    return n;
  }

  /* ── Card Events ── */
  function bindTocTplEvents() {
    tocTplGrid.querySelectorAll('.toc-tpl-edit-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openTocEditor(this.dataset.id);
      });
    });

    tocTplGrid.querySelectorAll('.toc-tpl-delete-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        deleteTocTemplate(this.dataset.id);
      });
    });
  }

  /* ── CRUD ── */
  function deleteTocTemplate(id) {
    if (!confirm('이 목차 템플릿을 삭제하시겠습니까?')) return;
    var xhr = new XMLHttpRequest();
    xhr.open('DELETE', TOC_API + '/' + id);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        toast('목차 템플릿이 삭제되었습니다.', 'success');
        loadTocTemplates();
      } else {
        var msg = '삭제에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () { toast('네트워크 오류가 발생했습니다.', 'error'); });
    xhr.send();
  }

  /* ── Editor: Open / Close ── */
  function openTocEditor(id) {
    var tpl = null;
    for (var i = 0; i < tocTemplates.length; i++) {
      if (tocTemplates[i].id === id) { tpl = tocTemplates[i]; break; }
    }
    if (!tpl) return;

    // 내장 템플릿은 복사하여 새 템플릿으로 편집
    if (tpl.builtin) {
      tocEditingId = null;
      tocTplEdTitle.textContent = '템플릿 복사: ' + tpl.name;
      tocTplFormName.value = tpl.name + ' (사본)';
    } else {
      tocEditingId = id;
      tocTplEdTitle.textContent = '템플릿 수정';
      tocTplFormName.value = tpl.name;
    }

    tocEditItems = deepCloneItems(tpl.items || []);
    renderTocTree();
    tocTplEditor.hidden = false;
    tocTplFormName.focus();
    tocTplEditor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function openTocEditorNew() {
    tocEditingId = null;
    tocTplEdTitle.textContent = '새 목차 템플릿 만들기';
    tocTplFormName.value = '';
    tocEditItems = [
      makeItem(1, 'I', '새 대분류', '', []),
    ];
    renderTocTree();
    tocTplEditor.hidden = false;
    tocTplFormName.focus();
    tocTplEditor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function closeTocEditor() {
    tocTplEditor.hidden = true;
    tocEditingId = null;
    tocEditItems = [];
  }

  /* ── Editor: Save ── */
  function saveTocTemplate() {
    var name = tocTplFormName.value.trim();
    if (!name) {
      toast('템플릿 이름을 입력해주세요.', 'error');
      return;
    }

    // 트리에서 빈 제목 항목 검증
    if (!tocEditItems.length) {
      toast('최소 1개의 목차 항목이 필요합니다.', 'error');
      return;
    }

    var payload = { name: name, items: tocEditItems };
    var isEdit = !!tocEditingId;
    var method = isEdit ? 'PUT' : 'POST';
    var url = isEdit ? TOC_API + '/' + tocEditingId : TOC_API;

    tocTplSubmit.disabled = true;
    tocTplSubmit.classList.add('is-loading');

    var xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      tocTplSubmit.disabled = false;
      tocTplSubmit.classList.remove('is-loading');
      if (xhr.status >= 200 && xhr.status < 300) {
        toast(isEdit ? '목차 템플릿이 수정되었습니다.' : '목차 템플릿이 생성되었습니다.', 'success');
        closeTocEditor();
        loadTocTemplates();
      } else {
        var msg = '저장에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      tocTplSubmit.disabled = false;
      tocTplSubmit.classList.remove('is-loading');
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify(payload));
  }

  /* ── Tree Helpers ── */
  function makeItem(level, number, title, description, children) {
    return {
      level: level,
      number: number || '',
      title: title || '',
      description: description || '',
      children: children || [],
    };
  }

  function deepCloneItems(items) {
    return JSON.parse(JSON.stringify(items));
  }

  /* Roman numerals for L1 */
  var ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

  function reassignNumbers(items, level) {
    for (var i = 0; i < items.length; i++) {
      if (level === 1) {
        items[i].number = ROMAN[i] || String(i + 1);
      } else {
        items[i].number = String(i + 1);
      }
      items[i].level = level;
      if (items[i].children && items[i].children.length) {
        reassignNumbers(items[i].children, level + 1);
      }
    }
  }

  /* ── Tree Rendering ── */
  function renderTocTree() {
    if (!tocTplTree) return;
    reassignNumbers(tocEditItems, 1);
    tocTplTree.innerHTML = renderBranch(tocEditItems, 1, []);
    bindTreeEvents();
    initDragDrop();
  }

  function renderBranch(items, level, parentPath) {
    if (!items.length) return '';
    var maxLevel = 3;
    var h = '<ul class="toc-tpl-branch toc-tpl-branch-l' + level + '">';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var path = parentPath.concat([i]);
      var pathStr = path.join('-');

      h += '<li class="toc-tpl-node" data-path="' + pathStr + '" draggable="true">';
      h += '<div class="toc-tpl-node-row toc-tpl-node-l' + level + '">';

      /* Drag handle */
      h += '<span class="toc-tpl-drag" title="드래그하여 이동">&#x2630;</span>';

      /* Number badge */
      h += '<span class="toc-tpl-num">' + esc(item.number) + '</span>';

      /* Title input */
      h += '<input type="text" class="toc-tpl-title-input" data-path="' + pathStr + '" data-field="title" value="' + esc(item.title) + '" placeholder="제목">';

      /* Description input */
      h += '<input type="text" class="toc-tpl-desc-input" data-path="' + pathStr + '" data-field="description" value="' + esc(item.description) + '" placeholder="설명">';

      /* Actions */
      h += '<div class="toc-tpl-node-actions">';
      if (level < maxLevel) {
        h += '<button type="button" class="toc-tpl-action-btn toc-tpl-add-child" data-path="' + pathStr + '" title="하위 항목 추가">+</button>';
      }
      h += '<button type="button" class="toc-tpl-action-btn toc-tpl-remove-node" data-path="' + pathStr + '" title="삭제">&times;</button>';
      h += '</div>';

      h += '</div>';

      /* Children */
      if (item.children && item.children.length) {
        h += renderBranch(item.children, level + 1, path);
      }

      h += '</li>';
    }
    h += '</ul>';
    return h;
  }

  /* ── Tree Event Binding ── */
  function bindTreeEvents() {
    /* Title & description inline edit */
    tocTplTree.querySelectorAll('.toc-tpl-title-input, .toc-tpl-desc-input').forEach(function (input) {
      input.addEventListener('input', function () {
        var path = parsePath(this.dataset.path);
        var field = this.dataset.field;
        var node = getNodeByPath(path);
        if (node) node[field] = this.value;
      });
    });

    /* Add child */
    tocTplTree.querySelectorAll('.toc-tpl-add-child').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var path = parsePath(this.dataset.path);
        var node = getNodeByPath(path);
        if (!node) return;
        if (!node.children) node.children = [];
        var childLevel = node.level + 1;
        node.children.push(makeItem(childLevel, '', '새 항목', '', []));
        renderTocTree();
      });
    });

    /* Remove node */
    tocTplTree.querySelectorAll('.toc-tpl-remove-node').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var path = parsePath(this.dataset.path);
        if (path.length === 1 && tocEditItems.length <= 1) {
          toast('최소 1개의 대분류가 필요합니다.', 'error');
          return;
        }
        removeNodeByPath(path);
        renderTocTree();
      });
    });
  }

  function parsePath(str) {
    return str.split('-').map(Number);
  }

  function getNodeByPath(path) {
    var items = tocEditItems;
    var node = null;
    for (var i = 0; i < path.length; i++) {
      if (path[i] < 0 || path[i] >= items.length) return null;
      node = items[path[i]];
      if (i < path.length - 1) items = node.children || [];
    }
    return node;
  }

  function removeNodeByPath(path) {
    if (path.length === 1) {
      tocEditItems.splice(path[0], 1);
      return;
    }
    var parentPath = path.slice(0, -1);
    var parent = getNodeByPath(parentPath);
    if (parent && parent.children) {
      parent.children.splice(path[path.length - 1], 1);
    }
  }

  /* ── Drag & Drop ── */
  var dragSrcPath = null;

  function initDragDrop() {
    tocTplTree.querySelectorAll('.toc-tpl-node').forEach(function (node) {
      node.addEventListener('dragstart', function (e) {
        e.stopPropagation();
        dragSrcPath = this.dataset.path;
        this.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      node.addEventListener('dragend', function () {
        this.classList.remove('is-dragging');
        tocTplTree.querySelectorAll('.toc-tpl-node').forEach(function (n) {
          n.classList.remove('drag-over');
        });
        dragSrcPath = null;
      });

      node.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        this.classList.add('drag-over');
      });

      node.addEventListener('dragleave', function () {
        this.classList.remove('drag-over');
      });

      node.addEventListener('drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('drag-over');
        if (!dragSrcPath) return;

        var fromPath = parsePath(dragSrcPath);
        var toPath = parsePath(this.dataset.path);

        // Don't drop on self
        if (dragSrcPath === this.dataset.path) return;

        // Don't drop parent into own child
        var fromStr = dragSrcPath + '-';
        if (this.dataset.path.indexOf(fromStr) === 0) return;

        // Same level move: reorder within same parent
        if (fromPath.length === toPath.length) {
          var fromParent = fromPath.length === 1 ? tocEditItems : (getNodeByPath(fromPath.slice(0, -1)) || {}).children;
          var toParent = toPath.length === 1 ? tocEditItems : (getNodeByPath(toPath.slice(0, -1)) || {}).children;

          if (fromParent === toParent && fromParent) {
            var fi = fromPath[fromPath.length - 1];
            var ti = toPath[toPath.length - 1];
            var moved = fromParent.splice(fi, 1)[0];
            if (fi < ti) ti--;
            fromParent.splice(ti, 0, moved);
            renderTocTree();
            return;
          }
        }

        // Cross-level: extract and insert at target's position
        var srcNode = getNodeByPath(fromPath);
        if (!srcNode) return;
        removeNodeByPath(fromPath);

        // Insert at toPath position
        if (toPath.length === 1) {
          var idx = Math.min(toPath[0], tocEditItems.length);
          tocEditItems.splice(idx, 0, srcNode);
        } else {
          var tParent = getNodeByPath(toPath.slice(0, -1));
          if (tParent && tParent.children) {
            var tIdx = Math.min(toPath[toPath.length - 1], tParent.children.length);
            tParent.children.splice(tIdx, 0, srcNode);
          }
        }
        renderTocTree();
      });
    });
  }

  /* ── Event Binding ── */
  if (tocTplAddBtn) {
    tocTplAddBtn.addEventListener('click', function () {
      openTocEditorNew();
    });
  }

  if (tocTplAddL1) {
    tocTplAddL1.addEventListener('click', function () {
      tocEditItems.push(makeItem(1, '', '새 대분류', '', []));
      renderTocTree();
    });
  }

  if (tocTplCancel) tocTplCancel.addEventListener('click', closeTocEditor);
  if (tocTplSubmit) tocTplSubmit.addEventListener('click', saveTocTemplate);

  /* ── Init TOC Templates ── */
  loadTocTemplates();
})();
