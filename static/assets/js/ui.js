(function () {
  var mqPhone = window.matchMedia('(max-width: 767px)');

  // 聊天区的滚动容器有两套模型：桌面端 .chat-scroll 自身滚动，
  // 手机端为避免 iOS 键盘顶不起输入框改为整页文档流滚动（.chat-scroll overflow:visible）。
  // 这里按实际能否滚动来定位真正的滚动者，返回 null 表示由文档负责滚动。
  function canScroll(node) {
    var oy = window.getComputedStyle(node).overflowY;
    return (oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 1;
  }

  function scrollerOf(el) {
    if (!el) return null;
    // overflow:visible 的盒子即使内容溢出也报 scrollHeight > clientHeight，
    // 但它滚不动，必须按 overflowY 判定真正的滚动者
    if (canScroll(el)) return el;
    var node = el.parentElement;
    while (node && node.nodeType === 1) {
      if (canScroll(node)) return node;
      node = node.parentElement;
    }
    return null;
  }

  function docScrolledToBottom() {
    var de = document.documentElement;
    return de.scrollHeight - (window.pageYOffset || de.scrollTop) - window.innerHeight < 80;
  }

  window.UI = {
    isPhone: function () { return mqPhone.matches; },

    atBottom: function (el) {
      var t = scrollerOf(el);
      if (!t) return docScrolledToBottom();
      return t.scrollHeight - t.scrollTop - t.clientHeight < 60;
    },

    // 仅在调用处已判定需要跟随时执行；nextTick 由调用方负责
    scrollToEnd: function (el) {
      var t = scrollerOf(el);
      if (!t) { window.scrollTo(0, document.documentElement.scrollHeight); return; }
      t.scrollTop = t.scrollHeight;
    },
  };
})();
