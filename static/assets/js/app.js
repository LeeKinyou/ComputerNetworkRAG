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

  var ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">';
  var TABS = [
    {
      key: 'overview', label: '概览', short: '概览',
      icon: ICON_SVG + '<rect x="4" y="4" width="7" height="7" rx="1.6"/>' +
        '<rect x="13" y="4" width="7" height="7" rx="1.6"/>' +
        '<rect x="4" y="13" width="7" height="7" rx="1.6"/>' +
        '<rect x="13" y="13" width="7" height="7" rx="1.6"/></svg>',
    },
    {
      key: 'graph', label: '知识图谱', short: '图谱',
      icon: ICON_SVG + '<circle cx="18" cy="5.5" r="2.4"/><circle cx="6" cy="12" r="2.4"/>' +
        '<circle cx="18" cy="18.5" r="2.4"/><path d="M8.2 10.8 15.8 6.6M8.2 13.2 15.8 17.4"/></svg>',
    },
    {
      key: 'rag', label: 'RAG 问答', short: '问答',
      icon: ICON_SVG + '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' +
        '<path d="M8 8h8M8 11.5h5"/></svg>',
    },
    {
      key: 'agent', label: 'ReAct 智能体', short: '智能体',
      icon: ICON_SVG + '<rect x="6" y="6" width="12" height="12" rx="2.4"/>' +
        '<rect x="9.5" y="9.5" width="5" height="5" rx="1"/>' +
        '<path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/></svg>',
    },
    {
      key: 'library', label: '知识库管理', short: '知识库',
      icon: ICON_SVG + '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    },
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
