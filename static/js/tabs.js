/* ============================================================
   RFP Parsing Result Tabs – KRDS Tab Navigation
   ============================================================ */
(function () {
  'use strict';

  var tabsContainer = document.querySelector('.tabs[role="tablist"]');
  if (!tabsContainer) return;

  var tabs = tabsContainer.querySelectorAll('.tab[role="tab"]');
  var panels = [];

  for (var i = 0; i < tabs.length; i++) {
    var panelId = tabs[i].getAttribute('aria-controls');
    var panel = document.getElementById(panelId);
    if (panel) panels.push(panel);
  }

  /* ============================================================
     Tab 전환
     ============================================================ */
  function activateTab(targetTab) {
    /* 모든 탭 비활성화 */
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.remove('is-active');
      tabs[i].setAttribute('aria-selected', 'false');
      tabs[i].setAttribute('tabindex', '-1');
    }

    /* 모든 패널 숨기기 */
    for (var j = 0; j < panels.length; j++) {
      panels[j].hidden = true;
      panels[j].classList.remove('is-active');
    }

    /* 선택된 탭 활성화 */
    targetTab.classList.add('is-active');
    targetTab.setAttribute('aria-selected', 'true');
    targetTab.setAttribute('tabindex', '0');

    /* 선택된 패널 표시 */
    var panelId = targetTab.getAttribute('aria-controls');
    var panel = document.getElementById(panelId);
    if (panel) {
      panel.hidden = false;
      panel.classList.remove('is-active');
      /* reflow를 발생시켜 애니메이션 재시작 */
      void panel.offsetHeight;
      panel.classList.add('is-active');
    }
  }

  /* ============================================================
     이벤트 바인딩 – 클릭
     ============================================================ */
  for (var k = 0; k < tabs.length; k++) {
    tabs[k].addEventListener('click', function () {
      activateTab(this);
    });
  }

  /* ============================================================
     이벤트 바인딩 – 키보드 (WAI-ARIA Tabs Pattern)
     좌/우 화살표: 이전/다음 탭 포커스 이동
     Home/End: 첫/마지막 탭
     ============================================================ */
  tabsContainer.addEventListener('keydown', function (e) {
    var currentIndex = -1;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i] === document.activeElement) {
        currentIndex = i;
        break;
      }
    }

    if (currentIndex === -1) return;

    var nextIndex = currentIndex;

    switch (e.key) {
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % tabs.length;
        break;
      case 'ArrowLeft':
        nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = tabs.length - 1;
        break;
      default:
        return;
    }

    e.preventDefault();
    tabs[nextIndex].focus();
    activateTab(tabs[nextIndex]);
  });

  /* ============================================================
     탭 바 스크롤 페이드 힌트
     ============================================================ */
  function updateTabScrollFade() {
    if (tabsContainer.scrollWidth <= tabsContainer.clientWidth) {
      tabsContainer.classList.remove('has-scroll-fade');
      return;
    }
    tabsContainer.classList.add('has-scroll-fade');
    var atEnd = tabsContainer.scrollLeft + tabsContainer.clientWidth >= tabsContainer.scrollWidth - 4;
    tabsContainer.classList.toggle('is-scrolled-end', atEnd);
  }

  tabsContainer.addEventListener('scroll', updateTabScrollFade, { passive: true });
  window.addEventListener('resize', updateTabScrollFade, { passive: true });

  /* 초기 호출 (약간 지연하여 레이아웃 안정화 후) */
  setTimeout(updateTabScrollFade, 100);

  /* ============================================================
     터치 스와이프 – 탭 패널에서 좌/우 스와이프로 탭 전환
     ============================================================ */
  var tabPanelContainer = tabsContainer.parentElement;

  if (tabPanelContainer && 'ontouchstart' in window) {
    var touchStartX = 0;
    var touchStartY = 0;
    var touchMoved = false;
    var SWIPE_THRESHOLD = 50;
    var SWIPE_VERTICAL_LIMIT = 80;

    tabPanelContainer.addEventListener('touchstart', function (e) {
      touchStartX = e.changedTouches[0].clientX;
      touchStartY = e.changedTouches[0].clientY;
      touchMoved = false;
    }, { passive: true });

    tabPanelContainer.addEventListener('touchmove', function () {
      touchMoved = true;
    }, { passive: true });

    tabPanelContainer.addEventListener('touchend', function (e) {
      if (!touchMoved) return;

      var deltaX = e.changedTouches[0].clientX - touchStartX;
      var deltaY = e.changedTouches[0].clientY - touchStartY;

      /* 수직 스크롤 의도 무시 */
      if (Math.abs(deltaY) > SWIPE_VERTICAL_LIMIT) return;
      if (Math.abs(deltaX) < SWIPE_THRESHOLD) return;

      /* 현재 활성 탭 인덱스 */
      var currentIndex = -1;
      for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].classList.contains('is-active')) {
          currentIndex = i;
          break;
        }
      }
      if (currentIndex === -1) return;

      var nextIndex;
      if (deltaX < 0) {
        /* 왼쪽 스와이프 → 다음 탭 */
        nextIndex = currentIndex + 1;
      } else {
        /* 오른쪽 스와이프 → 이전 탭 */
        nextIndex = currentIndex - 1;
      }

      if (nextIndex < 0 || nextIndex >= tabs.length) return;

      activateTab(tabs[nextIndex]);
      /* 활성 탭이 보이도록 스크롤 */
      tabs[nextIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }, { passive: true });
  }

  /* ============================================================
     배지 카운트 업데이트 API
     외부에서 window.updateTabBadge('overview', 8) 형태로 호출
     ============================================================ */
  window.updateTabBadge = function (tabKey, count) {
    var badge = document.getElementById('tab-badge-' + tabKey);
    if (badge) {
      badge.textContent = String(count);
    }
  };

  /* ============================================================
     탭 컨테이너 표시/숨김 API
     ============================================================ */
  var tabsCard = document.getElementById('analysis-tabs');

  window.showAnalysisTabs = function () {
    if (!tabsCard) return;
    tabsCard.hidden = false;
    tabsCard.classList.remove('is-visible');
    void tabsCard.offsetHeight;
    tabsCard.classList.add('is-visible');
  };

  window.hideAnalysisTabs = function () {
    if (!tabsCard) return;
    tabsCard.hidden = true;
    tabsCard.classList.remove('is-visible');
  };
})();
