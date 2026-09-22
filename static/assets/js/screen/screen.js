/* 大屏适配与标题栏时钟（09 §2.3）：设计稿 1920×1080 整体等比缩放居中。
   刻意不复用工作台 Store/app.js：两套生命周期互不干扰。 */
(function () {
  var BASE_W = 1920;
  var BASE_H = 1080;

  function fit() {
    var root = document.getElementById('screenRoot');
    var scale = Math.min(window.innerWidth / BASE_W, window.innerHeight / BASE_H);
    root.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function tickClock() {
    var el = document.getElementById('scClock');
    var now = new Date();
    el.textContent = pad2(now.getHours()) + ':' + pad2(now.getMinutes()) + ':' + pad2(now.getSeconds());
  }

  fit();
  tickClock();
  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', fit);
  setInterval(tickClock, 1000);
})();
