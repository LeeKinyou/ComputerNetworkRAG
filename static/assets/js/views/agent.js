window.Views = window.Views || {};

// 工具名 → 中文名（06 §7.1：工具名旁给中文名，避免技术黑话）
var TOOL_CN = {
  subnet_calculator: '子网计算器',
  lpm_lookup: '路由查表',
  dns_lookup: '域名解析',
  course_rag_query: '课程知识检索',
  ping_host: '主机连通性探测',
  http_probe: 'HTTP 探测',
};

window.Views.agent = {
  components: {
    'timeline': window.Components.timeline,
  },
  setup: function () {
    var ref = Vue.ref;
    var watch = Vue.watch;
    var nextTick = Vue.nextTick;

    // 演示用样例问题库（05 §6），点击即发送
    var CHIPS = [
      '192.168.10.137/27 的网络地址、广播地址和可用主机范围是什么？',
      '上题这个子网的网关一般设哪个地址？为什么？',
      '目的地址 10.2.3.4 在这张路由表里应该从哪个接口转发？',
      'www.example.com 解析到哪些 IP？它是什么类型的记录？',
      '域名解析用的是 TCP 还是 UDP？结合课件说明',
      '对比 TCP 和 UDP 的区别，课件里是怎么讲的？',
    ];

    var sessions = ref([]);
    var sessionsLoaded = ref(false);
    var listError = ref('');
    var currentSessionId = ref('');
    var runs = ref([]);        // 运行块：实时 run + 历史回放 run 共用同一结构
    var question = ref('');
    var busy = ref(false);
    var scroller = ref(null);
    var followBottom = ref(true);

    function onActivate(fn) {
      watch(Store.currentView, function (view) { if (view === 'agent') fn(); });
      if (Store.currentView.value === 'agent') fn();
    }

    function fmtTime(iso) {
      var s = String(iso || '');
      var m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
      return m ? m[1] + ' ' + m[2] : s.slice(0, 16);
    }

    function loadSessions() {
      return API.getJSON('/api/sessions').then(function (data) {
        sessions.value = (data.items || []).filter(function (s) { return s.mode === 'agent'; });
        sessionsLoaded.value = true;
        listError.value = '';
      }).catch(function () {
        sessionsLoaded.value = true;
        listError.value = '会话列表加载失败';
      });
    }

    function scrollBottom(force) {
      if (!scroller.value) return;
      if (!force && !followBottom.value) return;
      nextTick(function () {
        var el = scroller.value;
        if (el) el.scrollTop = el.scrollHeight;
      });
    }

    function onScroll() {
      var el = scroller.value;
      if (!el) return;
      followBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    }

    function lastGroup(run) {
      return run.groups.length ? run.groups[run.groups.length - 1] : null;
    }

    function pairObservation(run, d) {
      var g = null;
      for (var i = run.groups.length - 1; i >= 0; i--) {
        if (run.groups[i].step_no === d.step_no) { g = run.groups[i]; break; }
      }
      // 续跑流的观察可能落在中断前那一轮（该轮组已在），缺组时兜底建组
      if (!g) { g = { step_no: d.step_no, thought: '', actions: [] }; run.groups.push(g); }
      var obs = {
        status: d.status || 'failed',
        elapsed_ms: d.elapsed_ms || 0,
        result: d.result || '',
        structured: d.structured || {},
      };
      for (var j = 0; j < g.actions.length; j++) {
        if (!g.actions[j].obs) { g.actions[j].obs = obs; return; }
      }
      g.actions.push({ tool: '', tool_cn: '', args: {}, obs: obs });
    }

    // 首轮与审批续跑共用的 SSE 事件处理：续跑事件追加到同一条时间线（04 §6.5）
    function streamHandlers(run) {
      return {
        step_start: function (data) {
          run.groups.push({ step_no: data.step_no, thought: '', actions: [] });
          scrollBottom();
        },
        thought: function (data) {
          var g = lastGroup(run);
          if (g) g.thought = data.content || '';
          scrollBottom();
        },
        action: function (data) {
          var g = lastGroup(run);
          if (g) {
            g.actions.push({
              tool: data.tool || '', tool_cn: TOOL_CN[data.tool] || data.tool || '',
              args: data.args || {}, obs: null,
            });
          }
          scrollBottom();
        },
        observation: function (data) {
          pairObservation(run, data);
          scrollBottom();
        },
        token: function (data) {
          run.answer += (data && data.delta) || '';
          scrollBottom();
        },
        final: function (data) {
          run.answer = (data && data.answer) || run.answer;
          run.streaming = false;
          run.truncated = !!(data && data.truncated);
          // 完成后折叠时间线细节，保证答案在首屏（可再展开）
          if (run.answer) run.collapsed = true;
          busy.value = false;
          loadSessions();
          scrollBottom(true);
        },
        error: function (data) {
          run.streaming = false;
          run.pending = null;
          run.error = (data && data.message) || '服务异常，请重试';
          busy.value = false;
          scrollBottom();
        },
      };
    }

    // ----- 实时运行 -----

    function send(preset) {
      var q = String(preset == null ? question.value : preset).trim();
      if (!q || busy.value) return;
      question.value = '';
      busy.value = true;
      followBottom.value = true;
      // reactive 而非普通对象：SSE 闭包持原始引用时，普通对象的变更不经过
      // Vue 代理，不会触发重渲染（实测卡片全部等到 final 才一次性出现）
      var run = Vue.reactive({
        runId: '', sessionId: '', question: q,
        groups: [], answer: '', streaming: true,
        truncated: false, error: '', collapsed: false,
        pending: null,
      });
      runs.value.push(run);
      scrollBottom(true);

      var handlers = streamHandlers(run);
      handlers.meta = function (data) {
        run.runId = (data && data.run_id) || '';
        run.sessionId = (data && data.session_id) || '';
        currentSessionId.value = run.sessionId;
        loadSessions();
      };
      // 审批中断：当前流正常结束（无 final），行动卡下插入琥珀色审批条
      handlers.interrupt = function (data) {
        run.streaming = false;
        run.pending = {
          step_no: data.step_no, tool: data.tool || '',
          args: data.args || {}, argsText: JSON.stringify(data.args || {}, null, 2),
        };
        busy.value = false;
        scrollBottom(true);
      };
      API.postSSE('/api/agent/chat', { question: q, session_id: currentSessionId.value || null }, handlers);
    }

    // 审批决策（06 §4.4.1）：POST /resume，新流首帧 resumed，事件追加到原时间线
    function onDecide(run, payload) {
      if (busy.value || !run.pending) return;
      busy.value = true;
      followBottom.value = true;
      var handlers = streamHandlers(run);
      handlers.resumed = function () { run.pending = null; scrollBottom(); };
      API.postSSE('/api/agent/runs/' + run.runId + '/resume', {
        decision: payload.decision,
        edited_args: payload.decision === 'edit' ? payload.args : null,
      }, handlers);
    }

    function retry() {
      if (busy.value) return;
      for (var i = runs.value.length - 1; i >= 0; i--) {
        if (runs.value[i].error) {
          var q = runs.value[i].question;
          runs.value.splice(i, 1);
          send(q);
          return;
        }
      }
    }

    // ----- 历史回放（06 §4.4.3：与实时流共用时间线组件）-----

    function groupFromSteps(steps, run) {
      var groups = [];
      function ensure(stepNo) {
        for (var i = 0; i < groups.length; i++) {
          if (groups[i].step_no === stepNo) return groups[i];
        }
        var g = { step_no: stepNo, thought: '', actions: [] };
        groups.push(g);
        return g;
      }
      (steps || []).forEach(function (s) {
        if (s.kind === 'thought') {
          ensure(s.step_no).thought = s.content || '';
        } else if (s.kind === 'action') {
          ensure(s.step_no).actions.push({
            tool: s.tool_name || '', tool_cn: TOOL_CN[s.tool_name] || s.tool_name || '',
            args: s.tool_args || {}, obs: null,
          });
        } else if (s.kind === 'observation') {
          var g = ensure(s.step_no);
          var obs = {
            status: s.status || 'failed', elapsed_ms: s.elapsed_ms || 0,
            result: s.content || '', structured: s.structured || {},
          };
          var placed = false;
          for (var j = 0; j < g.actions.length; j++) {
            if (!g.actions[j].obs) { g.actions[j].obs = obs; placed = true; break; }
          }
          if (!placed) g.actions.push({ tool: '', tool_cn: '', args: {}, obs: obs });
        } else if (s.kind === 'error') {
          run.error = s.content || '运行失败';
        }
      });
      return groups;
    }

    function selectSession(s) {
      if (busy.value) return;
      API.getJSON('/api/sessions/' + s.session_id).then(function (data) {
        currentSessionId.value = s.session_id;
        // messages 按时间序携带 run_id：去重即该会话的运行列表
        var runIds = [];
        (data.messages || []).forEach(function (m) {
          if (m.run_id && runIds.indexOf(m.run_id) === -1) runIds.push(m.run_id);
        });
        return Promise.all(runIds.map(function (rid) {
          return API.getJSON('/api/sessions/' + s.session_id + '/runs/' + rid);
        })).then(function (payloads) {
          runs.value = payloads.map(function (p) {
            var run = {
              runId: p.run.run_id, sessionId: s.session_id,
              question: p.run.question,
              groups: [], answer: p.run.final_answer || '',
              streaming: false, truncated: false, error: '', collapsed: false,
              pending: null,
            };
            run.groups = groupFromSteps(p.steps, run);
            if (!run.answer && p.run.status === 'failed' && !run.error) {
              run.error = '运行失败';
            }
            // 待审批运行（03 §3.4）：刷新页面后仍可继续——从最后一个
            // 没有观察的行动卡片恢复审批条
            if (p.run.status === 'waiting_approval') {
              var pend = null;
              run.groups.forEach(function (g) {
                (g.actions || []).forEach(function (a) {
                  if (!a.obs) {
                    pend = { step_no: g.step_no, tool: a.tool, args: a.args || {},
                             argsText: JSON.stringify(a.args || {}, null, 2) };
                  }
                });
              });
              if (pend) run.pending = pend;
            }
            return run;
          });
          followBottom.value = true;
          scrollBottom(true);
        });
      }).catch(function () {
        listError.value = '历史运行加载失败';
      });
    }

    function newSession() {
      if (busy.value) return;
      currentSessionId.value = '';
      runs.value = [];
      question.value = '';
      followBottom.value = true;
    }

    onActivate(loadSessions);

    return {
      chips: CHIPS,
      sessions: sessions,
      sessionsLoaded: sessionsLoaded,
      listError: listError,
      currentSessionId: currentSessionId,
      runs: runs,
      question: question,
      busy: busy,
      scroller: scroller,
      fmtTime: fmtTime,
      loadSessions: loadSessions,
      selectSession: selectSession,
      newSession: newSession,
      send: send,
      onDecide: onDecide,
      retry: retry,
      onScroll: onScroll,
    };
  },
  template: `
    <section>
      <h2 class="view-title">ReAct 智能体</h2>
      <div class="split rag-split">
        <div class="card side-panel">
          <div class="side-head">
            <div class="side-title">历史会话</div>
            <button class="btn btn-sm" :disabled="busy" @click="newSession">新会话</button>
          </div>
          <div v-if="listError" class="error-bar">{{ listError }}</div>
          <div v-if="!sessionsLoaded" class="hint">加载中…</div>
          <div v-else-if="!sessions.length" class="empty" style="padding: 24px 8px;">暂无运行记录</div>
          <div v-else class="session-list">
            <div v-for="s in sessions" :key="s.session_id" class="session-item"
                 :class="{ active: s.session_id === currentSessionId }" @click="selectSession(s)">
              <div class="session-title">{{ s.title || '未命名会话' }}</div>
              <div class="session-time">{{ fmtTime(s.last_active_at || s.created_at) }}</div>
            </div>
          </div>
        </div>

        <div class="card chat-panel">
          <div class="chat-scroll" ref="scroller" @scroll="onScroll">
            <div v-if="!runs.length" class="chat-empty">
              <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="24" cy="24" r="14"/>
                <path d="M24 16 V24 L30 28"/>
                <path d="M8 10 L12 6 M40 10 L36 6 M24 4 V8" stroke-linecap="round"/>
              </svg>
              <p>智能体将逐步展示 思考 → 行动 → 观察 的完整推理过程</p>
              <p class="hint">支持子网计算、路由查表、DNS 解析、课程知识检索与主机探测（真实网络操作需人工审批）</p>
              <div class="chip-row">
                <button v-for="c in chips" :key="c" class="btn btn-sm chip" :disabled="busy"
                        @click="send(c)">{{ c }}</button>
              </div>
            </div>
            <template v-else>
              <div v-for="(run, ri) in runs" :key="ri" class="run-block">
                <div class="run-question">{{ run.question }}</div>
                <div v-if="run.error" class="error-bar">
                  {{ run.error }}
                  <button class="btn btn-sm" @click="retry">重试</button>
                </div>
                <template v-else>
                  <div v-if="run.collapsed" class="collapse-toggle">
                    <button class="btn btn-sm" @click="run.collapsed = false">
                      展开推理过程（{{ run.groups.length }} 步）
                    </button>
                  </div>
                  <div v-show="!run.collapsed" class="run-timeline">
                    <timeline :groups="run.groups" :answer="run.answer"
                              :streaming="run.streaming" :truncated="run.truncated"
                              :pending="run.pending" :disabled="busy"
                              @decide="onDecide(run, $event)"></timeline>
                  </div>
                </template>
              </div>
            </template>
          </div>

          <div class="chat-input-row">
            <textarea v-model="question" placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                      @keydown.enter.exact.prevent="send()"></textarea>
            <button class="btn primary" :disabled="busy || !question.trim()" @click="send()">
              {{ busy ? '推理中…' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </section>
  `,
};
