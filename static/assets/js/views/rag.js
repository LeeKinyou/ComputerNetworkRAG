window.Views = window.Views || {};

window.Views.rag = {
  components: {
    'source-card': window.Components.sourceCard,
  },
  setup: function () {
    var ref = Vue.ref;
    var watch = Vue.watch;
    var nextTick = Vue.nextTick;
    var onMounted = Vue.onMounted;
    var onBeforeUnmount = Vue.onBeforeUnmount;

    var MODES = [
      { value: 'naive', label: 'naive', desc: '纯向量检索：直接取语义最相近的原文分块' },
      { value: 'local', label: 'local', desc: '实体检索：取问题相关实体的邻居细节' },
      { value: 'global', label: 'global', desc: '全局检索：跨文档的实体关系总结' },
      { value: 'hybrid', label: 'hybrid', desc: 'local + global 融合（推荐）' },
    ];
    var CHIPS = [
      '对比 TCP 和 UDP 的区别，课件里是怎么讲的？',
      '简述 TCP 三次握手的过程',
      '子网掩码的作用是什么？',
    ];

    var sessions = ref([]);
    var sessionsLoaded = ref(false);
    var currentSessionId = ref('');
    var mode = ref('hybrid');
    var messages = ref([]);
    var question = ref('');
    var busy = ref(false);
    var listError = ref('');
    var inputError = ref('');
    var scroller = ref(null);
    var followBottom = ref(true);
    var sideOpen = ref(false);      // 手机端历史会话浮层；桌面端侧栏常驻不受影响

    function onActivate(fn) {
      watch(Store.currentView, function (view) { if (view === 'rag') fn(); });
      if (Store.currentView.value === 'rag') fn();
    }

    function fmtTime(iso) {
      var s = String(iso || '');
      var m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
      return m ? m[1] + ' ' + m[2] : s.slice(0, 16);
    }

    function loadSessions() {
      return API.getJSON('/api/sessions').then(function (data) {
        sessions.value = (data.items || []).filter(function (s) { return s.mode === 'rag'; });
        sessionsLoaded.value = true;
        listError.value = '';
      }).catch(function () {
        sessionsLoaded.value = true;
        listError.value = '会话列表加载失败';
      });
    }

    function scrollBottom(force) {
      var el = scroller.value;
      if (!el) return;
      if (!force && !UI.atBottom(el)) return;
      nextTick(function () { UI.scrollToEnd(el); });
    }

    function onScroll() {
      if (!scroller.value) return;
      followBottom.value = UI.atBottom(scroller.value);
    }

    function selectSession(s) {
      if (busy.value) return;
      API.getJSON('/api/sessions/' + s.session_id).then(function (data) {
        currentSessionId.value = s.session_id;
        sideOpen.value = false;
        messages.value = (data.messages || []).map(function (m) {
          return { role: m.role, content: m.content, sources: [], error: '', streaming: false, question: '' };
        });
        followBottom.value = true;
        scrollBottom(true);
      }).catch(function () {
        listError.value = '历史消息加载失败';
      });
    }

    function newSession() {
      if (busy.value) return;
      currentSessionId.value = '';
      sideOpen.value = false;
      messages.value = [];
      question.value = '';
      inputError.value = '';
      followBottom.value = true;
    }

    function questionWeight(q) {
      var w = 0;
      for (var i = 0; i < q.length; i++) w += /[\u2e80-\ufdff]/.test(q[i]) ? 2 : 1;
      return w;
    }

    function send(preset) {
      var q = String(preset == null ? question.value : preset).trim();
      if (!q || busy.value) return;
      // 与服务端阈值一致（权重 ≥3，中文按 2 计），提前拦截避免 422
      if (questionWeight(q) < 3) {
        inputError.value = '问题太短，请至少输入 2 个中文词或 3 个英文字符';
        return;
      }
      question.value = '';
      inputError.value = '';
      busy.value = true;
      followBottom.value = true;
      messages.value.push({ role: 'user', content: q, sources: [], error: '', streaming: false, question: '' });
      // reactive：SSE 闭包持原始引用，普通对象的属性变更不会触发重渲染
      var bot = Vue.reactive({ role: 'assistant', content: '', sources: [], error: '', streaming: true, question: q });
      messages.value.push(bot);
      scrollBottom();

      API.postSSE('/api/rag/chat', { question: q, mode: mode.value, session_id: currentSessionId.value || null }, {
        meta: function (data) {
          if (data && data.session_id) currentSessionId.value = data.session_id;
          loadSessions();
        },
        sources: function (data) {
          bot.sources = (data && data.items) || [];
          scrollBottom();
        },
        token: function (data) {
          bot.content += (data && data.delta) || '';
          scrollBottom();
        },
        final: function () {
          bot.streaming = false;
          busy.value = false;
          loadSessions();
        },
        error: function (data) {
          bot.streaming = false;
          busy.value = false;
          bot.error = (data && data.message) || '服务异常，请重试';
          scrollBottom();
        },
      });
    }

    function retry() {
      if (busy.value) return;
      for (var i = messages.value.length - 1; i >= 0; i--) {
        var m = messages.value[i];
        if (m.role === 'assistant' && m.error && m.question) {
          messages.value.splice(i, 1);
          send(m.question);
          return;
        }
      }
    }

    onActivate(loadSessions);

    // 手机端由文档滚动，@scroll 挂在 .chat-scroll 上收不到事件，需补整页监听
    onMounted(function () {
      window.addEventListener('scroll', onScroll, { passive: true });
    });
    onBeforeUnmount(function () {
      window.removeEventListener('scroll', onScroll);
    });

    return {
      modes: MODES,
      chips: CHIPS,
      sessions: sessions,
      sessionsLoaded: sessionsLoaded,
      currentSessionId: currentSessionId,
      mode: mode,
      messages: messages,
      question: question,
      busy: busy,
      listError: listError,
      inputError: inputError,
      scroller: scroller,
      sideOpen: sideOpen,
      fmtTime: fmtTime,
      modeDesc: function () {
        for (var i = 0; i < MODES.length; i++) if (MODES[i].value === mode.value) return MODES[i].desc;
        return '';
      },
      loadSessions: loadSessions,
      selectSession: selectSession,
      newSession: newSession,
      send: send,
      retry: retry,
      onScroll: onScroll,
    };
  },
  template: `
    <section>
      <h2 class="view-title">RAG 问答</h2>
      <div class="split rag-split">
        <div class="drawer-mask" v-if="sideOpen" @click="sideOpen = false"></div>
        <div class="card side-panel" :class="{ open: sideOpen }">
          <div class="side-head">
            <div class="side-title">历史会话</div>
            <button class="btn btn-sm" :disabled="busy" @click="newSession">新会话</button>
          </div>
          <div v-if="listError" class="error-bar">{{ listError }}</div>
          <div v-if="!sessionsLoaded" class="hint">加载中…</div>
          <div v-else-if="!sessions.length" class="empty" style="padding: 24px 8px;">暂无会话</div>
          <div v-else class="session-list">
            <div v-for="s in sessions" :key="s.session_id" class="session-item"
                 :class="{ active: s.session_id === currentSessionId }" @click="selectSession(s)">
              <div class="session-title">{{ s.title || '未命名会话' }}</div>
              <div class="session-time">{{ fmtTime(s.last_active_at || s.created_at) }}</div>
            </div>
          </div>
        </div>

        <div class="card chat-panel">
          <div class="chat-toolbar">
            <button class="btn btn-sm side-open-btn" :disabled="busy" @click="sideOpen = true">历史会话</button>
            <span class="side-title">检索模式</span>
            <div class="mode-seg">
              <button v-for="m in modes" :key="m.value" class="mode-btn"
                      :class="{ active: mode === m.value }" :title="m.desc"
                      :disabled="busy" @click="mode = m.value">{{ m.label }}</button>
            </div>
            <span class="mode-desc">{{ modeDesc() }}</span>
          </div>

          <div class="chat-scroll" ref="scroller" @scroll="onScroll">
            <div v-if="!messages.length" class="chat-empty">
              <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="8" y="10" width="32" height="24" rx="4"/>
                <path d="M18 40 L24 34 L30 40 M17 19 H31 M17 25 H26"/>
              </svg>
              <p>基于课程材料的检索增强问答，回答附带来源引用</p>
              <p class="hint">先在"知识库管理"上传课件，再选择下方示例提问</p>
              <div class="chip-row">
                <button v-for="c in chips" :key="c" class="btn btn-sm chip" :disabled="busy"
                        @click="send(c)">{{ c }}</button>
              </div>
            </div>
            <template v-else>
              <div v-for="(m, i) in messages" :key="i" class="bubble-row" :class="m.role">
                <div class="bubble" :class="m.role">
                  <source-card v-if="m.role === 'assistant' && m.sources.length"
                               :items="m.sources" :question="m.question"></source-card>
                  <div v-if="m.role === 'user' || m.content || !m.streaming" class="bubble-text">{{ m.content }}</div>
                  <div v-if="m.role === 'assistant' && m.streaming && !m.content" class="loading-hint">正在检索课程材料…</div>
                  <span v-if="m.role === 'assistant' && m.streaming && m.content" class="caret"></span>
                  <div v-if="m.error" class="error-bar">
                    {{ m.error }}
                    <button class="btn btn-sm" @click="retry">重试</button>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <div v-if="inputError" class="error-bar">{{ inputError }}</div>
          <div class="chat-input-row">
            <textarea v-model="question" placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                      @keydown.enter.exact.prevent="send()"></textarea>
            <button class="btn primary" :disabled="busy || !question.trim()" @click="send()">
              {{ busy ? '回答中…' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </section>
  `,
};
