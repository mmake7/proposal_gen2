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
})();
