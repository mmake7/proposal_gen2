/* ============================================================
   TOC Editor – Interactive Tree Editor
   제안목차 트리 에디터 (인라인 편집, 추가/삭제, 들여쓰기, 드래그&드롭)
   ============================================================ */
(function () {
  'use strict';

  var API_TOC_CURRENT = '/api/toc/current';
  var API_TOC_TEMPLATES = '/api/toc/templates';
  var API_TOC_APPLY = '/api/toc/current/apply-template';
  var API_TOC_FINALIZE = '/api/toc/current/finalize';

  var ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'];
  var KOREAN = ['가', '나', '다', '라', '마', '바', '사', '아', '자', '차', '카', '타', '파', '하'];

  var containerId = null;
  var tocData = [];
  var finalized = false;
  var saveTimer = null;
  var dragSrcPath = null;

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

  function autoNumber(items, level) {
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      item.level = level;
      if (level === 1) {
        item.number = ROMAN[i] || '' + (i + 1);
      } else if (level === 2) {
        item.number = '' + (i + 1);
      } else {
        item.number = KOREAN[i] || String.fromCharCode(0xAC00 + i);
      }
      if (item.children && item.children.length > 0) {
        autoNumber(item.children, level + 1);
      }
    }
  }

  function flattenItems(items, path) {
    var result = [];
    for (var i = 0; i < items.length; i++) {
      var p = path.concat([i]);
      result.push({ item: items[i], path: p });
      if (items[i].children && items[i].children.length > 0) {
        result = result.concat(flattenItems(items[i].children, p));
      }
    }
    return result;
  }

  function countItems(items) {
    var c = 0;
    for (var i = 0; i < items.length; i++) {
      c++;
      if (items[i].children) c += countItems(items[i].children);
    }
    return c;
  }

  function getItemAtPath(items, path) {
    var current = items;
    for (var i = 0; i < path.length - 1; i++) {
      current = current[path[i]].children || [];
    }
    return current[path[path.length - 1]] || null;
  }

  /* ============================================================
     Auto-save (debounced)
     ============================================================ */
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    var indicator = document.getElementById('toc-save-indicator');
    if (indicator) {
      indicator.textContent = '저장 중...';
      indicator.className = 'toc-editor-save-indicator is-saving';
    }
    saveTimer = setTimeout(function () {
      doSave();
    }, 500);
  }

  function doSave() {
    var xhr = new XMLHttpRequest();
    xhr.open('PUT', API_TOC_CURRENT);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      var indicator = document.getElementById('toc-save-indicator');
      if (xhr.status === 200) {
        if (indicator) {
          indicator.textContent = '저장됨';
          indicator.className = 'toc-editor-save-indicator is-saved';
          setTimeout(function () {
            indicator.textContent = '';
            indicator.className = 'toc-editor-save-indicator';
          }, 2000);
        }
      } else {
        if (indicator) {
          indicator.textContent = '저장 실패';
          indicator.className = 'toc-editor-save-indicator';
        }
      }
    });
    xhr.send(JSON.stringify({ items: tocData }));
  }

  /* ============================================================
     Render
     ============================================================ */
  function render() {
    var container = document.getElementById(containerId);
    if (!container) return;

    autoNumber(tocData, 1);
    var total = countItems(tocData);

    var html = '';

    /* ── Toolbar ── */
    html += '<div class="toc-editor-toolbar">';
    html += '<div class="toc-editor-toolbar-left">';
    html += '<span class="toc-toolbar-title">제안서 목차 편집</span>';
    html += '<span class="toc-toolbar-count">' + total + '개 항목</span>';
    html += '<span class="toc-editor-save-indicator" id="toc-save-indicator"></span>';
    html += '</div>';
    html += '<div class="toc-editor-toolbar-right">';
    html += '<select class="toc-template-select" id="toc-template-select" title="표준 템플릿 적용"><option value="">표준 템플릿 적용...</option></select>';
    html += '<button type="button" class="toc-add-root-btn" id="toc-add-root-btn">';
    html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
    html += ' 대분류 추가';
    html += '</button>';
    html += '<button type="button" class="toc-finalize-btn' + (finalized ? ' is-finalized' : '') + '" id="toc-finalize-btn">';
    html += finalized ? '확정됨 (수정하려면 클릭)' : '목차 확정';
    html += '</button>';
    html += '</div>';
    html += '</div>';

    /* ── Summary ── */
    var l1Count = tocData.length;
    html += '<div class="toc-summary">';
    html += '<span class="toc-summary-item">L1 대분류 <strong>' + l1Count + '</strong>개</span>';
    html += '<span class="toc-summary-divider"></span>';
    html += '<span class="toc-summary-item">전체 항목 <strong>' + total + '</strong>개</span>';
    html += '</div>';

    /* ── Tree items ── */
    if (tocData.length === 0) {
      html += '<div class="toc-editor-empty">목차 항목이 없습니다. "대분류 추가" 버튼을 클릭하거나 표준 템플릿을 적용하세요.</div>';
    } else {
      html += '<div class="toc-editor" id="toc-editor-tree">';
      var flat = flattenItems(tocData, []);
      for (var i = 0; i < flat.length; i++) {
        html += renderItem(flat[i].item, flat[i].path);
      }
      html += '</div>';
    }

    container.innerHTML = html;
    bindEvents();
    loadTemplateOptions();
  }

  function renderItem(item, path) {
    var pathStr = path.join('-');
    var level = item.level || 1;

    var h = '<div class="toc-editor-item" data-path="' + pathStr + '" data-level="' + level + '" draggable="true">';

    /* Drag handle */
    h += '<span class="toc-editor-drag" title="드래그하여 이동">';
    h += '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="8" cy="4" r="2"/><circle cx="16" cy="4" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="20" r="2"/><circle cx="16" cy="20" r="2"/></svg>';
    h += '</span>';

    /* Number */
    h += '<span class="toc-editor-number">' + esc(item.number) + '</span>';

    /* Content */
    h += '<div class="toc-editor-content">';
    h += '<div class="toc-editor-title" data-path="' + pathStr + '">' + esc(item.title) + '</div>';
    if (item.description) {
      h += '<div class="toc-editor-desc" data-path="' + pathStr + '">' + esc(item.description) + '</div>';
    } else {
      h += '<div class="toc-editor-desc" data-path="' + pathStr + '" style="opacity:0.4">설명 추가...</div>';
    }
    h += '</div>';

    /* Actions */
    h += '<div class="toc-editor-actions">';
    /* Outdent (level up) */
    h += '<button type="button" class="toc-editor-action-btn toc-outdent-btn" data-path="' + pathStr + '" title="레벨 올리기"' + (level <= 1 ? ' disabled' : '') + '>';
    h += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>';
    h += '</button>';
    /* Indent (level down) */
    h += '<button type="button" class="toc-editor-action-btn toc-indent-btn" data-path="' + pathStr + '" title="레벨 내리기"' + (level >= 3 ? ' disabled' : '') + '>';
    h += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>';
    h += '</button>';
    /* Add child */
    h += '<button type="button" class="toc-editor-action-btn toc-add-child-btn" data-path="' + pathStr + '" title="하위 항목 추가"' + (level >= 3 ? ' disabled' : '') + '>';
    h += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
    h += '</button>';
    /* Delete */
    h += '<button type="button" class="toc-editor-action-btn is-danger toc-delete-btn" data-path="' + pathStr + '" title="삭제">';
    h += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
    h += '</button>';
    h += '</div>';

    h += '</div>';
    return h;
  }

  /* ============================================================
     Event Binding
     ============================================================ */
  function bindEvents() {
    var tree = document.getElementById('toc-editor-tree');
    var addRootBtn = document.getElementById('toc-add-root-btn');
    var finalizeBtn = document.getElementById('toc-finalize-btn');
    var templateSelect = document.getElementById('toc-template-select');

    /* ── Inline edit (title) ── */
    if (tree) {
      tree.addEventListener('click', function (e) {
        var titleEl = e.target.closest('.toc-editor-title');
        if (titleEl) { startEditTitle(titleEl); return; }

        var descEl = e.target.closest('.toc-editor-desc');
        if (descEl) { startEditDesc(descEl); return; }

        var outdentBtn = e.target.closest('.toc-outdent-btn');
        if (outdentBtn && !outdentBtn.disabled) { doOutdent(outdentBtn.dataset.path); return; }

        var indentBtn = e.target.closest('.toc-indent-btn');
        if (indentBtn && !indentBtn.disabled) { doIndent(indentBtn.dataset.path); return; }

        var addChildBtn = e.target.closest('.toc-add-child-btn');
        if (addChildBtn && !addChildBtn.disabled) { doAddChild(addChildBtn.dataset.path); return; }

        var deleteBtn = e.target.closest('.toc-delete-btn');
        if (deleteBtn) { doDelete(deleteBtn.dataset.path); return; }
      });

      /* ── Drag & Drop ── */
      tree.addEventListener('dragstart', function (e) {
        var item = e.target.closest('.toc-editor-item');
        if (!item) return;
        dragSrcPath = item.dataset.path;
        item.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragSrcPath);
      });

      tree.addEventListener('dragend', function (e) {
        var item = e.target.closest('.toc-editor-item');
        if (item) item.classList.remove('is-dragging');
        clearDragStates(tree);
        dragSrcPath = null;
      });

      tree.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var target = e.target.closest('.toc-editor-item');
        if (!target || target.dataset.path === dragSrcPath) return;

        clearDragStates(tree);
        var rect = target.getBoundingClientRect();
        var y = e.clientY - rect.top;
        if (y < rect.height / 2) {
          target.classList.add('drag-over-above');
        } else {
          target.classList.add('drag-over-below');
        }
      });

      tree.addEventListener('dragleave', function (e) {
        var target = e.target.closest('.toc-editor-item');
        if (target) {
          target.classList.remove('drag-over-above', 'drag-over-below');
        }
      });

      tree.addEventListener('drop', function (e) {
        e.preventDefault();
        var target = e.target.closest('.toc-editor-item');
        if (!target || !dragSrcPath) return;

        var srcPath = parsePath(dragSrcPath);
        var dstPath = parsePath(target.dataset.path);
        var rect = target.getBoundingClientRect();
        var above = (e.clientY - rect.top) < rect.height / 2;

        doMove(srcPath, dstPath, above);
        clearDragStates(tree);
        dragSrcPath = null;
      });
    }

    /* ── Add root ── */
    if (addRootBtn) {
      addRootBtn.addEventListener('click', function () {
        tocData.push({
          level: 1, number: '', title: '새 대분류', description: '', children: []
        });
        finalized = false;
        render();
        scheduleSave();
      });
    }

    /* ── Finalize ── */
    if (finalizeBtn) {
      finalizeBtn.addEventListener('click', function () {
        if (finalized) {
          /* Unfinalize */
          finalized = false;
          render();
          scheduleSave();
          toast('목차 편집 모드로 전환되었습니다.', 'info');
        } else {
          if (tocData.length === 0) {
            toast('확정할 목차가 없습니다.', 'error');
            return;
          }
          doFinalize();
        }
      });
    }

    /* ── Template select ── */
    if (templateSelect) {
      templateSelect.addEventListener('change', function () {
        var tid = this.value;
        if (!tid) return;
        if (!confirm('현재 목차를 선택한 템플릿으로 교체하시겠습니까?')) {
          this.value = '';
          return;
        }
        doApplyTemplate(tid);
        this.value = '';
      });
    }
  }

  function clearDragStates(container) {
    var items = container.querySelectorAll('.toc-editor-item');
    for (var i = 0; i < items.length; i++) {
      items[i].classList.remove('drag-over', 'drag-over-above', 'drag-over-below');
    }
  }

  function parsePath(pathStr) {
    return pathStr.split('-').map(Number);
  }

  /* ============================================================
     Inline Editing
     ============================================================ */
  function startEditTitle(el) {
    if (el.querySelector('input')) return;
    var path = parsePath(el.dataset.path);
    var item = getItemAtPath(tocData, path);
    if (!item) return;

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'toc-editor-title-input';
    input.value = item.title;
    el.textContent = '';
    el.appendChild(input);
    input.focus();
    input.select();

    function save() {
      var val = input.value.trim();
      if (val) item.title = val;
      render();
      scheduleSave();
    }

    input.addEventListener('blur', save);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { input.value = item.title; input.blur(); }
    });
  }

  function startEditDesc(el) {
    if (el.querySelector('input')) return;
    var path = parsePath(el.dataset.path);
    var item = getItemAtPath(tocData, path);
    if (!item) return;

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'toc-editor-desc-input';
    input.value = item.description || '';
    input.placeholder = '설명을 입력하세요...';
    el.textContent = '';
    el.style.opacity = '';
    el.appendChild(input);
    input.focus();

    function save() {
      item.description = input.value.trim();
      render();
      scheduleSave();
    }

    input.addEventListener('blur', save);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { input.value = item.description || ''; input.blur(); }
    });
  }

  /* ============================================================
     TOC Operations
     ============================================================ */
  function doOutdent(pathStr) {
    var path = parsePath(pathStr);
    if (path.length < 2) return; /* Already at root level */

    var parentPath = path.slice(0, -1);
    var idx = path[path.length - 1];
    var parentItems = getParentList(tocData, path);
    var item = parentItems[idx];

    /* Remove from current position */
    parentItems.splice(idx, 1);

    /* Insert after parent in grandparent list */
    var grandParentList = getParentList(tocData, parentPath);
    var parentIdx = parentPath[parentPath.length - 1];
    grandParentList.splice(parentIdx + 1, 0, item);

    finalized = false;
    render();
    scheduleSave();
  }

  function doIndent(pathStr) {
    var path = parsePath(pathStr);
    var idx = path[path.length - 1];
    if (idx === 0) return; /* No previous sibling to become parent */

    var parentList = getParentList(tocData, path);
    var item = parentList[idx];
    var prevSibling = parentList[idx - 1];

    /* Remove from current position */
    parentList.splice(idx, 1);

    /* Add as last child of previous sibling */
    if (!prevSibling.children) prevSibling.children = [];
    prevSibling.children.push(item);

    finalized = false;
    render();
    scheduleSave();
  }

  function doAddChild(pathStr) {
    var path = parsePath(pathStr);
    var item = getItemAtPath(tocData, path);
    if (!item) return;
    if (!item.children) item.children = [];
    item.children.push({
      level: (item.level || 1) + 1,
      number: '',
      title: '새 항목',
      description: '',
      children: [],
    });
    finalized = false;
    render();
    scheduleSave();
  }

  function doDelete(pathStr) {
    var path = parsePath(pathStr);
    var item = getItemAtPath(tocData, path);
    if (!item) return;
    var hasChildren = item.children && item.children.length > 0;
    if (hasChildren && !confirm('하위 항목도 함께 삭제됩니다. 계속하시겠습니까?')) return;

    var parentList = getParentList(tocData, path);
    var idx = path[path.length - 1];
    parentList.splice(idx, 1);

    finalized = false;
    render();
    scheduleSave();
  }

  function doMove(srcPath, dstPath, above) {
    if (pathsEqual(srcPath, dstPath)) return;

    /* Extract source item */
    var srcList = getParentList(tocData, srcPath);
    var srcIdx = srcPath[srcPath.length - 1];
    if (srcIdx < 0 || srcIdx >= srcList.length) return;
    var item = srcList.splice(srcIdx, 1)[0];

    /* Recalculate dstPath after removal if needed */
    var dstList = getParentList(tocData, dstPath);
    var dstIdx = dstPath[dstPath.length - 1];
    if (!above) dstIdx++;
    dstIdx = Math.max(0, Math.min(dstIdx, dstList.length));
    dstList.splice(dstIdx, 0, item);

    finalized = false;
    render();
    scheduleSave();
  }

  function getParentList(items, path) {
    var current = items;
    for (var i = 0; i < path.length - 1; i++) {
      if (!current[path[i]]) return [];
      current = current[path[i]].children || [];
    }
    return current;
  }

  function pathsEqual(a, b) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  /* ============================================================
     API Actions
     ============================================================ */
  function doFinalize() {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_TOC_FINALIZE);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        finalized = true;
        render();
        toast('목차가 확정되었습니다. 제안서 작성을 진행할 수 있습니다.', 'success');
      } else {
        var msg = '목차 확정에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send();
  }

  function doApplyTemplate(templateId) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_TOC_APPLY);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        var result = xhr.response;
        tocData = result.items || [];
        finalized = result.finalized || false;
        render();
        toast('표준 템플릿이 적용되었습니다.', 'success');
      } else {
        var msg = '템플릿 적용에 실패했습니다.';
        try { msg = xhr.response.error || msg; } catch (e) {}
        toast(msg, 'error');
      }
    });
    xhr.addEventListener('error', function () {
      toast('네트워크 오류가 발생했습니다.', 'error');
    });
    xhr.send(JSON.stringify({ template_id: templateId }));
  }

  function loadTemplateOptions() {
    var select = document.getElementById('toc-template-select');
    if (!select) return;
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_TOC_TEMPLATES);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200) {
        var templates = xhr.response || [];
        var html = '<option value="">표준 템플릿 적용...</option>';
        for (var i = 0; i < templates.length; i++) {
          html += '<option value="' + esc(templates[i].id) + '">' + esc(templates[i].name) + (templates[i].builtin ? ' (내장)' : '') + '</option>';
        }
        select.innerHTML = html;
      }
    });
    xhr.send();
  }

  /* ============================================================
     Public API
     ============================================================ */
  function init(targetContainerId, initialData) {
    containerId = targetContainerId;
    tocData = initialData || [];
    finalized = false;

    /* Load current TOC from server if available */
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_TOC_CURRENT);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200 && xhr.response) {
        var serverItems = xhr.response.items || [];
        /* Use server data if available, otherwise use initial data */
        if (serverItems.length > 0) {
          tocData = serverItems;
        }
        finalized = xhr.response.finalized || false;
      }
      render();
    });
    xhr.addEventListener('error', function () {
      /* On error, just render with initial data */
      render();
    });
    xhr.send();
  }

  function getData() {
    return tocData;
  }

  function refresh() {
    render();
  }

  window.TocEditor = {
    init: init,
    getData: getData,
    refresh: refresh,
  };

})();
