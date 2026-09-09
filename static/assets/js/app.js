(function () {
  var ref = Vue.ref;
  var computed = Vue.computed;
  var onMounted = Vue.onMounted;

  window.Store = {
    currentView: ref('overview'),
    health: ref(null),
    stats: ref({}),
  };

  Store.refreshStats = function () {
    API.getJSON('/api/stats').then(function (data) {
      Store.stats.value = data;
    }).catch(function () { /* 状态点已提示 */ });
  };

  var TABS = [
    { key: 'overview', label: '概览' },
    { key: 'graph', label: '知识图谱' },
    { key: 'rag', label: 'RAG 问答' },
    { key: 'agent', label: 'ReAct 智能体' },
    { key: 'library', label: '知识库管理' },
  ];
  var KEYS = TABS.map(function (t) { return t.key; });

  function syncFromHash() {
    var key = (location.hash || '').replace(/^#\//, '');
    Store.currentView.value = KEYS.indexOf(key) !== -1 ? key : 'overview';
  }

  function refreshHealth() {
    API.getJSON('/api/health').then(function (data) {
      Store.health.value = data;
    }).catch(function () {
      Store.health.value = { status: 'error' };
    });
  }

  var app = Vue.createApp({
    setup: function () {
      onMounted(function () {
        syncFromHash();
        window.addEventListener('hashchange', syncFromHash);
        refreshHealth();
        // 文档 06 §5：断网/API 异常时顶部状态点变红
        setInterval(refreshHealth, 15000);
      });

      var healthClass = computed(function () {
        if (!Store.health.value) return '';
        return Store.health.value.status === 'ok' ? 'ok' : 'error';
      });
      var healthText = computed(function () {
        if (!Store.health.value) return '检测中';
        return Store.health.value.status === 'ok' ? '服务正常' : '服务异常';
      });
      var healthTitle = computed(function () {
        if (!Store.health.value) return '正在检测服务状态';
        return 'status=' + Store.health.value.status + '  llm=' + (Store.health.value.llm || 'unknown');
      });

      function go(key) { location.hash = '#/' + key; }

      return {
        tabs: TABS,
        currentView: Store.currentView,
        healthClass: healthClass,
        healthText: healthText,
        healthTitle: healthTitle,
        go: go,
      };
    },
  });

  app.component('overview-view', window.Views.overview);
  app.component('graph-view', window.Views.graph);
  app.component('rag-view', window.Views.rag);
  app.component('agent-view', window.Views.agent);
  app.component('library-view', window.Views.library);

  app.mount('#app');
})();
