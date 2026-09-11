window.Views = window.Views || {};

window.Views.graph = {
  components: { 'graph-view': window.Components.graphView },
  setup: function () {
    var ref = Vue.ref;
    var onMounted = Vue.onMounted;

    var nodes = ref([]);
    var edges = ref([]);
    var types = ref([]);
    var truncated = ref(false);
    var loading = ref(false);
    var loadError = ref('');
    var keyword = ref('');
    var activeTypes = ref([]);       // 类型多选
    var selected = ref(null);        // 抽屉中的实体详情
    var loaded = ref(false);         // 视图常驻：已加载则切换 Tab 不重复请求
    // 小屏按 500 节点会糊成一团且首屏很慢，手机端降密度（可搜索/筛选继续深入）
    var limit = ref(UI.isPhone() ? 160 : 500);

    var searchTimer = null;
    var graphRef = ref(null);

    function query() {
      var params = new URLSearchParams();
      if (keyword.value.trim()) params.set('keyword', keyword.value.trim());
      if (activeTypes.value.length) params.set('entity_type', activeTypes.value.join(','));
      params.set('limit', String(limit.value));
      loading.value = true;
      loadError.value = '';
      API.getJSON('/api/graph?' + params.toString()).then(function (data) {
        nodes.value = data.nodes || [];
        edges.value = data.edges || [];
        types.value = data.types || [];
        truncated.value = !!data.truncated;
        loading.value = false;
        loaded.value = true;
      }).catch(function () {
        loading.value = false;
        loadError.value = '图谱数据加载失败，请重试';
      });
    }

    function onKeywordInput() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(query, 300);
    }
    function toggleType(t) {
      var i = activeTypes.value.indexOf(t);
      if (i === -1) activeTypes.value.push(t);
      else activeTypes.value.splice(i, 1);
      query();
    }
    function typeActive(t) { return activeTypes.value.indexOf(t) !== -1; }

    function refresh() { query(); }
    function relayout() { if (graphRef.value) graphRef.value.relayout(); }

    function openEntity(name) {
      API.getJSON('/api/graph/entity/' + encodeURIComponent(name)).then(function (data) {
        selected.value = data;
      }).catch(function () {
        selected.value = null;
      });
    }
    function onNodeClick(node) { openEntity(node.id); }
    function selectNeighbor(n) { openEntity(n.name); }
    function closeDrawer() { selected.value = null; }

    onMounted(function () {
      if (!loaded.value) query();
    });

    return {
      nodes: nodes, edges: edges, types: types, truncated: truncated,
      limit: limit,
      loading: loading, loadError: loadError, keyword: keyword,
      selected: selected, graphRef: graphRef,
      onKeywordInput: onKeywordInput, toggleType: toggleType, typeActive: typeActive,
      refresh: refresh, relayout: relayout,
      onNodeClick: onNodeClick, selectNeighbor: selectNeighbor, closeDrawer: closeDrawer,
    };
  },
  template: `
    <section>
      <h2 class="view-title">知识图谱</h2>
      <div class="card graph-toolbar">
        <input class="search-input" type="text" v-model="keyword"
               @input="onKeywordInput" placeholder="搜索实体名，如 TCP、路由器…">
        <div class="type-filter">
          <span v-for="t in types" :key="t" class="tag type-chip"
                :class="{ active: typeActive(t) }" @click="toggleType(t)">{{ t }}</span>
        </div>
        <div class="toolbar-actions">
          <button class="btn btn-sm" @click="relayout">重新布局</button>
          <button class="btn btn-sm" @click="refresh" :disabled="loading">{{ loading ? '加载中…' : '刷新' }}</button>
        </div>
      </div>
      <div class="error-bar" v-if="loadError" style="margin-bottom: 12px;">{{ loadError }}
        <button class="btn btn-sm" style="margin-left: 8px;" @click="refresh">重试</button>
      </div>
      <div class="truncated-bar" v-if="truncated">
        节点较多，已按 {{ limit }} 上限截断，请搜索或筛选缩小范围
      </div>
      <div class="card graph-card">
        <graph-view v-if="nodes.length" ref="graphRef"
                    :nodes="nodes" :edges="edges" :types="types"
                    :selected-name="selected && selected.entity ? selected.entity.name : ''"
                    @node-click="onNodeClick"></graph-view>
        <div class="empty" v-else-if="loading" style="padding: 80px 16px;"><p>图谱加载中…</p></div>
        <div class="empty" v-else style="padding: 80px 16px;">
          <p>{{ loaded ? '没有匹配的实体，试试其他关键词' : '请先到知识库管理上传课程材料' }}</p>
          <p class="hint" v-if="loaded">或清除筛选条件后刷新</p>
        </div>
      </div>

      <div class="drawer-mask" v-if="selected" @click="closeDrawer"></div>
      <aside class="drawer" v-if="selected && selected.entity">
        <div class="drawer-head">
          <h3>{{ selected.entity.name }}</h3>
          <span class="tag">{{ selected.entity.type }}</span>
          <button class="drawer-close" @click="closeDrawer">✕</button>
        </div>
        <p class="drawer-desc">{{ selected.entity.description }}</p>
        <div class="drawer-section" v-if="selected.entity.sources && selected.entity.sources.length">
          <div class="side-title">来源文档</div>
          <div v-for="(s, i) in selected.entity.sources" :key="i" class="source-item">
            <span class="source-doc">{{ s.doc_name || '未知文档' }}</span>
            <span class="hint" v-if="s.chunk_id">{{ s.chunk_id }}</span>
          </div>
        </div>
        <div class="drawer-section" v-if="selected.neighbors && selected.neighbors.length">
          <div class="side-title">关联实体（{{ selected.neighbors.length }}）</div>
          <div v-for="(nb, i) in selected.neighbors" :key="i" class="neighbor-item" @click="selectNeighbor(nb)">
            <span class="neighbor-name">{{ nb.name }}</span>
            <span class="tag">{{ nb.relation }}</span>
          </div>
        </div>
      </aside>
    </section>
  `,
};
