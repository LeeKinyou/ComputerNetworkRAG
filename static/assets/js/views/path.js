window.Views = window.Views || {};

// 学习路径（09 §3.5 / Task 5.6）：章节 DAG + 必修链规划。
// 只读视图——构建走命令行脚本，演示现场不点按钮触发 LLM 批量调用。
window.Views.path = {
  components: { 'path-graph': window.Components.pathGraph },
  setup: function () {
    var ref = Vue.ref;
    var computed = Vue.computed;
    var onMounted = Vue.onMounted;

    var nodes = ref([]);
    var edges = ref([]);
    var chapters = ref([]);
    var truncated = ref(false);
    var chapter = ref(0);                 // 0 = 全部
    var mode = ref('layer');
    var loading = ref(false);
    var loadError = ref('');
    var loaded = ref(false);
    var keyword = ref('');
    var typing = ref(false);         // 选中一条建议后收起下拉，但输入框保留知识点名
    var selected = ref(null);
    var plan = ref(null);
    var planError = ref('');
    var planning = ref(false);
    var limit = ref(UI.isPhone() ? 20 : 40);

    // 环形布局只在 ≤20 节点时给开：30 个以上必然压叠（讯飞截图实测的教训）
    var RING_MAX = 20;
    var ringDisabled = computed(function () { return nodes.value.length > RING_MAX; });

    function query() {
      loading.value = true;
      loadError.value = '';
      var params = new URLSearchParams();
      params.set('chapter', String(chapter.value));
      params.set('limit', String(limit.value));
      API.getJSON('/api/path?' + params.toString()).then(function (data) {
        nodes.value = data.nodes || [];
        edges.value = data.edges || [];
        chapters.value = data.chapters || [];
        truncated.value = !!data.truncated;
        if (nodes.value.length > RING_MAX) mode.value = 'layer';
        loading.value = false;
        loaded.value = true;
      }).catch(function () {
        loading.value = false;
        loadError.value = '学习路径数据加载失败，请重试';
      });
    }

    function pickChapter(c) {
      if (chapter.value === c) return;
      chapter.value = c;
      plan.value = null;
      selected.value = null;
      keyword.value = '';
      query();
    }

    var suggestions = computed(function () {
      var kw = keyword.value.trim().toLowerCase();
      if (!kw) return [];
      return nodes.value.filter(function (n) {
        return n.name.toLowerCase().indexOf(kw) !== -1;
      }).slice(0, 8);
    });

    function nodeById(id) {
      for (var i = 0; i < nodes.value.length; i++) {
        if (nodes.value[i].kp_id === id) return nodes.value[i];
      }
      return null;
    }

    function onSuggest(n) {
      keyword.value = n.name;
      typing.value = false;
      openPlan(n);
    }

    function openPlan(node) {
      planning.value = true;
      planError.value = '';
      API.getJSON('/api/path/plan?target=' + encodeURIComponent(node.kp_id)).then(function (data) {
        plan.value = data;
        planning.value = false;
        selected.value = null;
      }).catch(function () {
        planning.value = false;
        planError.value = '必修链生成失败：目标知识点可能尚未构建前驱关系';
        plan.value = null;
      });
    }

    function planFromSelected() {
      if (selected.value && selected.value.node) openPlan(selected.value.node);
    }

    function clearPlan() {
      plan.value = null;
      planError.value = '';
      keyword.value = '';
    }

    function onNodeClick(n) {
      var prereq = [], unlock = [];
      edges.value.forEach(function (e) {
        if (e.target === n.kp_id && e.source !== n.kp_id) prereq.push(nodeById(e.source));
        if (e.source === n.kp_id && e.target !== n.kp_id) unlock.push(nodeById(e.target));
      });
      selected.value = {
        node: n,
        prereq: prereq.filter(Boolean),
        unlock: unlock.filter(Boolean),
      };
    }

    var planIds = computed(function () {
      return plan.value ? plan.value.steps.map(function (s) { return s.kp_id; }) : [];
    });

    onMounted(function () {
      if (!loaded.value) query();
    });

    return {
      nodes: nodes, edges: edges, chapters: chapters, truncated: truncated,
      chapter: chapter, mode: mode, limit: limit,
      loading: loading, loadError: loadError, loaded: loaded,
      keyword: keyword, typing: typing, suggestions: suggestions, selected: selected,
      plan: plan, planIds: planIds, planError: planError, planning: planning,
      ringDisabled: ringDisabled, RING_MAX: RING_MAX,
      pickChapter: pickChapter, onSuggest: onSuggest, openPlan: openPlan,
      planFromSelected: planFromSelected, clearPlan: clearPlan,
      onNodeClick: onNodeClick,
      refresh: query,
    };
  },
  template: `
    <section>
      <div class="view-head">
        <h2 class="view-title">学习路径</h2>
        <div class="toolbar-actions">
          <button class="btn btn-sm" @click="refresh" :disabled="loading">
            {{ loading ? '加载中…' : '刷新' }}
          </button>
        </div>
      </div>

      <div class="card graph-toolbar">
        <div class="type-filter">
          <span class="tag type-chip" :class="{ active: chapter === 0 }" @click="pickChapter(0)">全部</span>
          <span v-for="c in chapters" :key="c" class="tag type-chip"
                :class="{ active: chapter === c }" @click="pickChapter(c)">第 {{ c }} 章</span>
        </div>
        <div class="path-target">
          <input class="search-input" type="text" v-model="keyword" @input="typing = true"
                 placeholder="选定目标知识点，如 HTTP、子网划分…">
          <div class="path-suggest" v-if="typing && keyword.trim() && suggestions.length">
            <div v-for="s in suggestions" :key="s.kp_id" class="path-suggest-item" @click="onSuggest(s)">
              <span>{{ s.name }}</span><span class="hint">第 {{ s.chapter }} 章</span>
            </div>
          </div>
          <div class="path-suggest" v-else-if="typing && keyword.trim() && !suggestions.length">
            <div class="path-suggest-item hint">当前范围内没有匹配的知识点</div>
          </div>
        </div>
        <div class="toolbar-actions">
          <button class="btn btn-sm" :class="{ primary: mode === 'layer' }"
                  @click="mode = 'layer'">分层布局</button>
          <button class="btn btn-sm" :class="{ primary: mode === 'ring' }"
                  @click="mode = 'ring'" :disabled="ringDisabled"
                  :title="ringDisabled ? '节点超过 ' + RING_MAX + ' 个时环形布局必然压叠，已切回分层' : ''">
            环形布局
          </button>
        </div>
      </div>

      <div class="error-bar" v-if="loadError" style="margin: 12px 0;">{{ loadError }}
        <button class="btn btn-sm" style="margin-left: 8px;" @click="refresh">重试</button>
      </div>
      <div class="truncated-bar" v-if="truncated">
        该范围内知识点较多，已按每章 {{ limit }} 个上限截断，长尾依赖不在此图中
      </div>

      <div class="card path-plan" v-if="plan">
        <div class="path-plan-head">
          <b>{{ plan.target.name }}</b>
          <span class="tag">第 {{ plan.target.chapter }} 章</span>
          <span class="hint" v-if="plan.no_prereq">该知识点无前置依赖，可直接学习</span>
          <span class="hint" v-else>共 {{ plan.steps.length - 1 }} 个前置知识点，按下面的顺序学</span>
          <button class="btn btn-sm" style="margin-left:auto" @click="clearPlan">清除</button>
        </div>
        <ol class="path-steps">
          <li v-for="(s, i) in plan.steps" :key="s.kp_id"
              :class="{ goal: i === plan.steps.length - 1 }">
            <span class="path-step-no">{{ i + 1 }}</span>
            <div>
              <div class="path-step-name">{{ s.name }}<span class="hint">第 {{ s.chapter }} 章</span></div>
              <div class="path-step-reason" v-if="s.reason">{{ s.reason }}</div>
              <div class="path-step-reason hint" v-else>范围内无更强前置，按章节顺序排在前面</div>
            </div>
          </li>
        </ol>
      </div>
      <div class="error-bar" v-if="planError" style="margin: 12px 0;">{{ planError }}
        <button class="btn btn-sm" style="margin-left: 8px;" @click="refresh">重试</button>
      </div>

      <div class="card graph-card" style="margin-top: var(--gap);">
        <div class="path-legend">
          <span><i class="lg lg-plain"></i>未触达</span>
          <span><i class="lg lg-touched"></i>已触达</span>
          <span><i class="lg lg-planned"></i>必修链</span>
          <span class="hint">箭头方向 = 先学 → 后学；点节点看详情，点边看依据</span>
        </div>
        <div class="warn-bar" v-if="nodes.length && !edges.length">
          还没有前驱关系：这一章只画出了知识点，未画出先后依赖。
          请先执行 <code>uv run python -m scripts.build_learning_path --all</code> 构建路径
        </div>
        <path-graph v-if="nodes.length" :nodes="nodes" :edges="edges"
                    :plan-ids="planIds" :mode="mode"
                    :selected-id="selected && selected.node ? selected.node.kp_id : ''"
                    @node-click="onNodeClick"></path-graph>
        <div class="empty" v-else-if="loading" style="padding: 80px 16px;"><p>路径加载中…</p></div>
        <div class="empty" v-else style="padding: 80px 16px;">
          <p>{{ loaded ? '该范围内没有已归章的知识点' : '尚未物化知识点' }}</p>
          <p class="hint">构建命令：<code>uv run python -m scripts.build_learning_path --all</code></p>
        </div>
      </div>

      <div class="drawer-mask" v-if="selected" @click="selected = null"></div>
      <aside class="drawer" v-if="selected && selected.node">
        <div class="drawer-head">
          <h3>{{ selected.node.name }}</h3>
          <span class="tag">{{ selected.node.type }}</span>
          <button class="drawer-close" @click="selected = null">✕</button>
        </div>
        <p class="drawer-desc">{{ selected.node.description || '暂无描述' }}</p>
        <div class="drawer-section">
          <div class="side-title">第 {{ selected.node.chapter }} 章 · 图谱度数 {{ selected.node.degree }}
            · 已触达 {{ selected.node.touch_count }} 次</div>
        </div>
        <div class="drawer-section">
          <div class="side-title">必须先学 {{ selected.prereq.length }} 个</div>
          <div v-for="(p, i) in selected.prereq" :key="i" class="neighbor-item">
            <span class="neighbor-name">{{ p.name }}</span><span class="tag">第 {{ p.chapter }} 章</span>
          </div>
          <p class="hint" v-if="!selected.prereq.length">没有前置依赖，可直接学习</p>
        </div>
        <div class="drawer-section">
          <div class="side-title">解锁 {{ selected.unlock.length }} 个</div>
          <div v-for="(u, i) in selected.unlock" :key="i" class="neighbor-item">
            <span class="neighbor-name">{{ u.name }}</span><span class="tag">第 {{ u.chapter }} 章</span>
          </div>
          <p class="hint" v-if="!selected.unlock.length">它不是其他知识点的前置</p>
        </div>
        <div class="drawer-section">
          <button class="btn primary" style="width: 100%;" @click="planFromSelected"
                  :disabled="planning">{{ planning ? '生成中…' : '以此为目标生成路径' }}</button>
        </div>
      </aside>
    </section>
  `,
};
