/* 공용 유틸 — 모든 모듈보다 먼저 로드됨.
 *
 * 기존에 7개 모듈에 흩어져 중복 정의되던 escapeHtml/esc/toast 를 한 곳으로 모음.
 * 각 모듈의 로컬 정의를 제거하면 호출이 스코프 체인을 따라 이 전역으로 해석된다.
 *   - escapeHtml / esc : HTML 텍스트 이스케이프 (동일 동작, esc는 별칭)
 *   - toast            : 간단 토스트 (#toast-container 필요). download.js 의
 *                        window.showToast(type,title,desc) 와는 별개(리치 토스트).
 */
(function (w) {
  'use strict';

  function escapeHtml(str) {
    if (str == null) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
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

  w.escapeHtml = escapeHtml;
  w.esc = escapeHtml;   // 별칭: 기존 esc() 호출처 호환
  w.toast = toast;
})(window);
