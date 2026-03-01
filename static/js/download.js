/* ============================================================
   Excel Download + Toast Notification System
   ============================================================ */
(function () {
  'use strict';

  /* ── DOM 요소 캐시 ── */
  var downloadBtn    = document.getElementById('excel-download-btn');
  var toastContainer = document.getElementById('toast-container');

  if (!downloadBtn || !toastContainer) return;

  /* ── 설정 ── */
  var DOWNLOAD_ENDPOINT = '/api/download/excel';
  var TOAST_DURATION_MS = 5000;
  var isDownloading = false;

  /* ── SVG 아이콘 ── */
  var TOAST_ICONS = {
    success: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.06l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/></svg>',
    error: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/></svg>',
    info: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/></svg>',
    warning: '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>'
  };

  /* ============================================================
     토스트 알림 시스템 (전역 API)
     사용: window.showToast('success', '제목', '설명')
     ============================================================ */
  function showToast(type, title, desc) {
    var toast = document.createElement('div');
    toast.className = 'toast is-' + type;
    toast.setAttribute('role', 'status');

    var html = '';
    html += '<div class="toast-icon">' + (TOAST_ICONS[type] || '') + '</div>';
    html += '<div class="toast-body">';
    html += '<p class="toast-title">' + escapeHtml(title) + '</p>';
    if (desc) {
      html += '<p class="toast-desc">' + escapeHtml(desc) + '</p>';
    }
    html += '</div>';
    html += '<button type="button" class="toast-close" aria-label="닫기">';
    html += '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>';
    html += '</button>';
    html += '<div class="toast-progress" style="width:100%"></div>';

    toast.innerHTML = html;
    toastContainer.appendChild(toast);

    /* 닫기 버튼 */
    var closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', function () {
      removeToast(toast);
    });

    /* 프로그레스 바 애니메이션 */
    var progressBar = toast.querySelector('.toast-progress');
    /* 한 프레임 뒤에 시작하여 transition 적용 */
    requestAnimationFrame(function () {
      progressBar.style.transitionDuration = TOAST_DURATION_MS + 'ms';
      progressBar.style.width = '0%';
    });

    /* 자동 제거 */
    var autoTimer = setTimeout(function () {
      removeToast(toast);
    }, TOAST_DURATION_MS);

    /* hover 시 타이머 일시중지 */
    toast.addEventListener('mouseenter', function () {
      clearTimeout(autoTimer);
      progressBar.style.transitionDuration = '0ms';
      var currentWidth = progressBar.getBoundingClientRect().width;
      var containerWidth = toast.getBoundingClientRect().width;
      var remaining = (currentWidth / containerWidth) * 100;
      progressBar.style.width = remaining + '%';
    });

    toast.addEventListener('mouseleave', function () {
      var currentWidth = progressBar.getBoundingClientRect().width;
      var containerWidth = toast.getBoundingClientRect().width;
      var remainPct = currentWidth / containerWidth;
      var remainTime = remainPct * TOAST_DURATION_MS;

      progressBar.style.transitionDuration = remainTime + 'ms';
      progressBar.style.width = '0%';

      autoTimer = setTimeout(function () {
        removeToast(toast);
      }, remainTime);
    });

    return toast;
  }

  function removeToast(toast) {
    if (!toast || !toast.parentNode) return;
    toast.classList.add('is-removing');
    setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 250);
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* 전역 API로 노출 */
  window.showToast = showToast;

  /* ============================================================
     Excel 다운로드 로직
     ============================================================ */
  function setLoading(loading) {
    isDownloading = loading;
    if (loading) {
      downloadBtn.classList.add('is-loading');
      downloadBtn.setAttribute('aria-busy', 'true');
      downloadBtn.querySelector('.btn-label').textContent = '다운로드 중…';
    } else {
      downloadBtn.classList.remove('is-loading');
      downloadBtn.removeAttribute('aria-busy');
      downloadBtn.querySelector('.btn-label').textContent = 'Excel 다운로드';
    }
  }

  function extractFileName(response) {
    var disposition = response.headers.get('Content-Disposition');
    if (disposition) {
      /* filename*=UTF-8'' 형식 우선 */
      var utf8Match = disposition.match(/filename\*=(?:UTF-8''|utf-8'')([^;\s]+)/i);
      if (utf8Match) return decodeURIComponent(utf8Match[1]);

      /* filename="..." 형식 */
      var match = disposition.match(/filename="?([^";\n]+)"?/);
      if (match) return match[1].trim();
    }
    return 'RFP_분석결과.xlsx';
  }

  function downloadExcel() {
    if (isDownloading) return;

    setLoading(true);

    fetch(DOWNLOAD_ENDPOINT, {
      method: 'GET',
      headers: { 'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
    })
    .then(function (response) {
      if (!response.ok) {
        throw new Error(response.status + ' ' + response.statusText);
      }
      var fileName = extractFileName(response);
      return response.blob().then(function (blob) {
        return { blob: blob, fileName: fileName };
      });
    })
    .then(function (result) {
      /* Blob URL로 다운로드 트리거 */
      var url = URL.createObjectURL(result.blob);
      var link = document.createElement('a');
      link.href = url;
      link.download = result.fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setLoading(false);
      showToast('success', 'Excel 다운로드 완료', result.fileName + ' 파일이 저장되었습니다.');
    })
    .catch(function (err) {
      setLoading(false);
      showToast('error', 'Excel 다운로드 실패', '파일을 다운로드할 수 없습니다. 잠시 후 다시 시도해주세요.');
    });
  }

  /* ── 버튼 클릭 이벤트 ── */
  downloadBtn.addEventListener('click', function () {
    downloadExcel();
  });
})();
