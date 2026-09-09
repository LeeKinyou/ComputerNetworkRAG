(function () {
  var ref = Vue.ref;
  var computed = Vue.computed;
  var onMounted = Vue.onMounted;

  window.Store = {
    currentView: ref('overview'),
    health: ref(null),
    llmStatus: ref('unknown'),   // 仅由深探测更新，避免 15s 浅轮询冲掉降级态
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

  // 06 §4.2 / 07 Task4.2：check_llm=1 深探测接入状态点（挂载时 + 每 60s）
  function refreshHealthDeep() {
    API.getJSON('/api/health?check_llm=1').then(function (data) {
      Store.health.value = data;
      Store.llmStatus.value = data.llm || 'unknown';
    }).catch(function () {
      // 深探测失败时保留最近一次结果，不立刻翻红
    });
  }

  var app = Vue.createApp({
    setup: function () {
      onMounted(function () {
        syncFromHash();
        window.addEventListener('hashchange', syncFromHash);
        refreshHealth();
        refreshHealthDeep();
        // 文档 06 §5：断网/API 异常时顶部状态点变红
        setInterval(refreshHealth, 15000);
        setInterval(refreshHealthDeep, 60000);
      });

      var healthClass = computed(function () {
        if (!Store.health.value) return '';
        if (Store.health.value.status === 'error') return 'error';
        // 服务可达但 LLM 探测失败：琥珀色降级态（错 key / 断网 / 超时）
        var llm = Store.llmStatus.value;
        if (llm !== 'ok' && llm !== 'unknown') return 'warn';
        return 'ok';
      });
      var healthText = computed(function () {
        if (!Store.health.value) return '检测中';
        if (Store.health.value.status === 'error') return '服务异常';
        var llm = Store.llmStatus.value;
        if (llm !== 'ok' && llm !== 'unknown') return 'LLM 异常';
        return '服务正常';
      });
      var healthTitle = computed(function () {
        if (!Store.health.value) return '正在检测服务状态';
        var h = Store.health.value;
        return 'status=' + h.status + '  llm=' + Store.llmStatus.value;
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
