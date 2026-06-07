/* ============================================================
   TOC Editor – Table-based Interactive Editor
   제안목차 테이블 에디터 (엑셀 동일 형식, 인라인 편집, 요구사항 매핑)
   ============================================================ */
(function () {
  'use strict';

  var API_TOC_CURRENT = '/api/toc/current';
  var API_TOC_TEMPLATES = '/api/toc/templates';
  var API_TOC_APPLY = '/api/toc/current/apply-template';
  var API_TOC_FINALIZE = '/api/toc/current/finalize';

  var ROMAN = ['\u2160', '\u2161', '\u2162', '\u2163', '\u2164',
               '\u2165', '\u2166', '\u2167', '\u2168', '\u2169',
               '\u216A', '\u216B'];  /* Ⅰ~Ⅻ */

  var containerId = null;
  var tocData = [];
  var reqData = [];
  var finalized = false;
  var saveTimer = null;
  var dragSrcIdx = null;

  /* ============================================================
     Utilities
     ============================================================ */
  /* escapeHtml·esc·toast → util.js 전역 사용 */


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

  function getParentList(items, path) {
    var current = items;
    for (var i = 0; i < path.length - 1; i++) {
      if (!current[path[i]]) return [];
      current = current[path[i]].children || [];
    }
    return current;
  }

  function parsePath(pathStr) {
    return pathStr.split('-').map(Number);
  }

  /* ============================================================
     Hierarchical Numbering (엑셀과 동일)
     ============================================================ */
  function flattenHierarchical(items, out, parentPrefix, depth) {
    for (var idx = 0; idx < items.length; idx++) {
      var item = items[idx];
      var labelNumber, childPrefix;

      if (depth === 1) {
        var roman = ROMAN[idx] || '' + (idx + 1);
        labelNumber = roman + '.';
        childPrefix = '' + (idx + 1);
      } else if (depth === 2) {
        var num = '' + (idx + 1);
        labelNumber = num + '.';
        childPrefix = (parentPrefix || '') + num + '.';
      } else {
        var full = parentPrefix + (idx + 1) + '.';
        labelNumber = full;
        childPrefix = full;
      }

      var indent = '';
      for (var s = 1; s < depth; s++) indent += '\u00A0\u00A0\u00A0\u00A0';

      out.push({
        level: depth,
        label: indent + labelNumber + ' ' + (item.title || ''),
        labelNumber: labelNumber,
        title: item.title || '',
        description: item.description || '',
        path: item._path,
        reqIds: ''
      });

      var children = item.children || [];
      if (children.length > 0) {
        flattenHierarchical(children, out, childPrefix, depth + 1);
      }
    }
  }

  /* ============================================================
     Requirement ↔ TOC Matching (엑셀 매핑 로직과 동일)
     ============================================================ */
  function extractKeywords(text) {
    if (!text) return [];
    var matches = text.match(/[가-힣a-zA-Z0-9]{2,}/g);
    return matches ? matches.map(function (w) { return w.toLowerCase(); }) : [];
  }

  function matchRequirements(flatRows) {
    if (!reqData || reqData.length === 0) return;

    var entries = [];
    for (var r = 0; r < reqData.length; r++) {
      var req = reqData[r];
      var rid = req.id || '';
      var rname = (req.name || '').trim();
      if (!rid || !rname) continue;
      entries.push({
        id: rid,
        name: rname,
        nameLower: rname.toLowerCase(),
        keywords: extractKeywords(rname)
      });
    }
    if (entries.length === 0) return;

    for (var i = 0; i < flatRows.length; i++) {
      var row = flatRows[i];
      var title = row.title;
      if (!title) continue;

      var titleLower = title.toLowerCase();
      var titleKw = extractKeywords(title);
      var titleKwSet = {};
      for (var k = 0; k < titleKw.length; k++) titleKwSet[titleKw[k]] = true;

      var matched = [];
      for (var j = 0; j < entries.length; j++) {
        var e = entries[j];

        /* 방법 1: 부분 문자열 포함 */
        if (titleLower.indexOf(e.nameLower) !== -1 || e.nameLower.indexOf(titleLower) !== -1) {
          matched.push(e.id);
          continue;
        }

        /* 방법 2: 키워드 50% 이상 일치 */
        if (e.keywords.length > 0 && titleKw.length > 0) {
          var overlap = 0;
          for (var m = 0; m < e.keywords.length; m++) {
            if (titleKwSet[e.keywords[m]]) overlap++;
          }
          if (overlap >= Math.max(1, e.keywords.length * 0.5)) {
            matched.push(e.id);
          }
        }
      }

      if (matched.length > 0) {
        /* 중복 제거 */
        var seen = {};
        var unique = [];
        for (var u = 0; u < matched.length; u++) {
          if (!seen[matched[u]]) {
            seen[matched[u]] = true;
            unique.push(matched[u]);
          }
        }
        row.reqIds = unique.join(', ');
      }
    }
  }

  /* ============================================================
     Assign internal _path for editing operations
     ============================================================ */
  function assignPaths(items, prefix) {
    for (var i = 0; i < items.length; i++) {
      var p = prefix.concat([i]);
      items[i]._path = p.join('-');
      if (items[i].children && items[i].children.length > 0) {
        assignPaths(items[i].children, p);
      }
    }
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
     Render – Table-based (엑셀 동일 형식)
     ============================================================ */
  function render() {
    var container = document.getElementById(containerId);
    if (!container) return;

    assignPaths(tocData, []);
    var total = countItems(tocData);

    /* Flatten with hierarchical numbering */
    var flatRows = [];
    flattenHierarchical(tocData, flatRows, '', 1);

    /* Match requirements */
    matchRequirements(flatRows);

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

    /* ── Table ── */
    if (tocData.length === 0) {
      html += '<div class="toc-editor-empty">';
      html += '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.4;margin-bottom:12px"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>';
      html += '<p style="font-weight:600;margin:0 0 4px">제안서 목차를 구성해주세요</p>';
      html += '<p style="opacity:0.65;margin:0">위 드롭다운에서 <strong>표준 템플릿을 선택</strong>하거나, "대분류 추가" 버튼으로 직접 작성할 수 있습니다.</p>';
      html += '</div>';
    } else {
      html += '<div class="toc-table-wrap" id="toc-editor-tree">';
      html += '<table class="toc-table">';
      html += '<thead><tr>';
      html += '<th class="toc-th toc-th-label">목차</th>';
      html += '<th class="toc-th toc-th-req">요구사항 ID</th>';
      html += '<th class="toc-th toc-th-author">작성담당자</th>';
      html += '<th class="toc-th toc-th-desc">설명</th>';
      html += '<th class="toc-th toc-th-actions"></th>';
      html += '</tr></thead>';
      html += '<tbody>';

      for (var i = 0; i < flatRows.length; i++) {
        var row = flatRows[i];
        var level = row.level;
        var rowClass = 'toc-tr toc-tr-l' + level;
        if (level === 1) rowClass += ' toc-tr-l1';

        html += '<tr class="' + rowClass + '" data-path="' + esc(row.path) + '" data-idx="' + i + '" draggable="true">';

        /* 목차 (계층형 번호 + 제목) */
        html += '<td class="toc-td toc-td-label">';
        html += '<span class="toc-cell-label" data-field="title" data-path="' + esc(row.path) + '">' + esc(row.label) + '</span>';
        html += '</td>';

        /* 요구사항 ID */
        html += '<td class="toc-td toc-td-req">' + esc(row.reqIds) + '</td>';

        /* 작성담당자 */
        html += '<td class="toc-td toc-td-author"></td>';

        /* 설명 */
        html += '<td class="toc-td toc-td-desc">';
        html += '<span class="toc-cell-desc" data-field="desc" data-path="' + esc(row.path) + '">';
        html += row.description ? esc(row.description) : '<span style="opacity:0.35">클릭하여 입력</span>';
        html += '</span>';
        html += '</td>';

        /* Actions */
        html += '<td class="toc-td toc-td-actions">';
        html += '<div class="toc-row-actions">';
        html += '<button type="button" class="toc-action-btn toc-add-child-btn" data-path="' + esc(row.path) + '" title="하위 추가"' + (level >= 4 ? ' disabled' : '') + '>';
        html += '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
        html += '</button>';
        html += '<button type="button" class="toc-action-btn is-danger toc-delete-btn" data-path="' + esc(row.path) + '" title="삭제">';
        html += '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
        html += '</button>';
        html += '</div>';
        html += '</td>';

        html += '</tr>';
      }

      html += '</tbody></table></div>';
    }

    container.innerHTML = html;
    bindEvents();
    loadTemplateOptions();
  }

  /* ============================================================
     Event Binding
     ============================================================ */
  function bindEvents() {
    var tree = document.getElementById('toc-editor-tree');
    var addRootBtn = document.getElementById('toc-add-root-btn');
    var finalizeBtn = document.getElementById('toc-finalize-btn');
    var templateSelect = document.getElementById('toc-template-select');

    if (tree) {
      tree.addEventListener('click', function (e) {
        var labelEl = e.target.closest('.toc-cell-label');
        if (labelEl) { startEditTitle(labelEl); return; }

        var descEl = e.target.closest('.toc-cell-desc');
        if (descEl) { startEditDesc(descEl); return; }

        var addChildBtn = e.target.closest('.toc-add-child-btn');
        if (addChildBtn && !addChildBtn.disabled) { doAddChild(addChildBtn.dataset.path); return; }

        var deleteBtn = e.target.closest('.toc-delete-btn');
        if (deleteBtn) { doDelete(deleteBtn.dataset.path); return; }
      });

      /* ── Drag & Drop ── */
      tree.addEventListener('dragstart', function (e) {
        var tr = e.target.closest('.toc-tr');
        if (!tr) return;
        dragSrcIdx = tr.dataset.idx;
        tr.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragSrcIdx);
      });

      tree.addEventListener('dragend', function (e) {
        var tr = e.target.closest('.toc-tr');
        if (tr) tr.classList.remove('is-dragging');
        clearDragStates(tree);
        dragSrcIdx = null;
      });

      tree.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var tr = e.target.closest('.toc-tr');
        if (!tr || tr.dataset.idx === dragSrcIdx) return;
        clearDragStates(tree);
        var rect = tr.getBoundingClientRect();
        if ((e.clientY - rect.top) < rect.height / 2) {
          tr.classList.add('drag-over-above');
        } else {
          tr.classList.add('drag-over-below');
        }
      });

      tree.addEventListener('dragleave', function (e) {
        var tr = e.target.closest('.toc-tr');
        if (tr) tr.classList.remove('drag-over-above', 'drag-over-below');
      });

      tree.addEventListener('drop', function (e) {
        e.preventDefault();
        var tr = e.target.closest('.toc-tr');
        if (!tr || dragSrcIdx === null) return;

        var srcPath = parsePath(tr.closest('table').querySelector('[data-idx="' + dragSrcIdx + '"]').dataset.path);
        var dstPath = parsePath(tr.dataset.path);
        var rect = tr.getBoundingClientRect();
        var above = (e.clientY - rect.top) < rect.height / 2;

        doMove(srcPath, dstPath, above);
        clearDragStates(tree);
        dragSrcIdx = null;
      });
    }

    if (addRootBtn) {
      addRootBtn.addEventListener('click', function () {
        tocData.push({ level: 1, number: '', title: '새 대분류', description: '', children: [] });
        finalized = false;
        render();
        scheduleSave();
      });
    }

    if (finalizeBtn) {
      finalizeBtn.addEventListener('click', function () {
        if (finalized) {
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
    var rows = container.querySelectorAll('.toc-tr');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.remove('drag-over-above', 'drag-over-below');
    }
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
    input.className = 'toc-inline-input';
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
    input.className = 'toc-inline-input';
    input.value = item.description || '';
    input.placeholder = '설명을 입력하세요...';
    el.textContent = '';
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
    if (srcPath.join('-') === dstPath.join('-')) return;

    var srcList = getParentList(tocData, srcPath);
    var srcIdx = srcPath[srcPath.length - 1];
    if (srcIdx < 0 || srcIdx >= srcList.length) return;
    var item = srcList.splice(srcIdx, 1)[0];

    var dstList = getParentList(tocData, dstPath);
    var dstIdx = dstPath[dstPath.length - 1];
    if (!above) dstIdx++;
    dstIdx = Math.max(0, Math.min(dstIdx, dstList.length));
    dstList.splice(dstIdx, 0, item);

    finalized = false;
    render();
    scheduleSave();
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
  function init(targetContainerId, initialData, requirements) {
    containerId = targetContainerId;
    tocData = initialData || [];
    reqData = requirements || [];
    finalized = false;

    /* Load current TOC from server if available */
    var xhr = new XMLHttpRequest();
    xhr.open('GET', API_TOC_CURRENT);
    xhr.responseType = 'json';
    xhr.addEventListener('load', function () {
      if (xhr.status === 200 && xhr.response) {
        var serverItems = xhr.response.items || [];
        if (serverItems.length > 0) {
          tocData = serverItems;
        }
        finalized = xhr.response.finalized || false;
      }
      syncEmptyState();
      render();
    });
    xhr.addEventListener('error', function () {
      syncEmptyState();
      render();
    });
    xhr.send();
  }

  /** empty 오버레이를 tocData 유무에 따라 토글 */
  function syncEmptyState() {
    var emptyEl = document.getElementById('tabpanel-toc-empty');
    if (emptyEl) emptyEl.hidden = true;   /* TocEditor가 모든 상태를 직접 관리 */
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
