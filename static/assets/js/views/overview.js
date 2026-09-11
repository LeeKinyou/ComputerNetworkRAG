window.Views = window.Views || {};

window.Views.overview = {
  setup: function () {
    var ref = Vue.ref;
    var nextTick = Vue.nextTick;
    var onBeforeUnmount = Vue.onBeforeUnmount;
    var stats = Store.stats;
    var cards = [
      { key: 'documents', label: '课程文档' },
      { key: 'entities', label: '知识实体' },
      { key: 'relations', label: '关系' },
      { key: 'chunks', label: '文本分块' },
      { key: 'sessions', label: '问答会话' },
    ];

    // ----- 迷你知识图谱 + 分布图表（06 §4.1：只读、纯前端聚合、点击进入图谱页）-----
    var TYPE_COLORS = (window.Components.graphView && window.Components.graphView.TYPE_COLORS) || {};
    function colorOf(t) { return TYPE_COLORS[t] || '#98A2AB'; }
    var harvest = window.Components.graphView.harvest;

    var miniEl = ref(null);
    var miniNodes = ref([]);
    var miniEdges = ref([]);
    var miniLoading = ref(false);
    var miniError = ref('');
    var chart = null;
    var miniRO = null;
    var miniFrozen = null;   // 力导收敛后冻结坐标，避免 resize/重渲染时反复洗牌

    var distEl = ref(null);
    var relEl = ref(null);
    var distData = ref([]);
    var relData = ref([]);
    var distChart = null;
    var relChart = null;
    var chartsRO = null;

    // echarts 在首帧布局完成前 init 会测到错误宽度（实测 100px），
    // 用 ResizeObserver 保证在真实布局后建图与重渲染
    function ensureMiniChart() {
      if (chart || !miniEl.value || typeof echarts === 'undefined') return;
      if (!miniEl.value.offsetWidth) return;
      chart = echarts.init(miniEl.value);
    }

    function renderMini() {
      ensureMiniChart();
      if (!chart || !miniNodes.value.length) return;
      var w = miniEl.value.offsetWidth;
      var h = miniEl.value.offsetHeight;
      if (w && (chart.getWidth() !== w || chart.getHeight() !== h)) chart.resize();
      // 只给度数最高的前 10 个核心实体标名称，防止小卡内标签互相遮盖；
      // 手机上卡片只有 ~300px 高，10 个长中文名必然叠成一团，索性不标
      var labelSet = {};
      if (!UI.isPhone()) {
        miniNodes.value.slice().sort(function (a, b) { return (b.degree || 0) - (a.degree || 0); })
          .slice(0, 10).forEach(function (n) { labelSet[n.id] = true; });
      }
      var nodes = miniNodes.value.map(function (n) {
        var item = {
          id: n.id,
          name: n.name,
          symbolSize: 5 + Math.min(6, (n.degree || 0) * 1.2),
          itemStyle: { color: colorOf(n.type) },
          label: { show: !!labelSet[n.id] },
        };
        if (miniFrozen) {
          var fp = miniFrozen[n.id] || miniFrozen[n.name];
          if (fp) { item.x = fp.x; item.y = fp.y; }
        }
        return item;
      });
      var links = miniEdges.value.map(function (e) {
        return { source: e.source, target: e.target };
      });
      chart.setOption({
        series: [{
          type: 'graph',
          layout: miniFrozen ? 'none' : 'force',
          data: nodes,
          links: links,
          roam: false,
          silent: true,   // 只读：不响应交互，点击入口交给"进入知识图谱"按钮
          force: { repulsion: 300, edgeLength: [40, 100], gravity: 0.06, layoutAnimation: false },
          label: { show: true, fontSize: 11, color: '#1A1B1C' },
        }],
      }, true);
      // 力导收敛（所有节点均有坐标）后冻结坐标，缩放/重渲染不再洗牌
      if (!miniFrozen) {
        setTimeout(function () {
          if (miniFrozen || !chart) return;
          var pos = harvest(chart);
          if (pos && Object.keys(pos).length >= miniNodes.value.length) {
            miniFrozen = pos;
            renderMini();
          }
        }, 0);
      }
    }

    function loadMini() {
      miniLoading.value = true;
      miniError.value = '';
      miniFrozen = null;
      API.getJSON('/api/graph?limit=120').then(function (data) {
        miniNodes.value = data.nodes || [];
        miniEdges.value = data.edges || [];
        miniLoading.value = false;
        nextTick(renderMini);
      }).catch(function () {
        miniLoading.value = false;
        miniError.value = '图谱缩略图加载失败';
      });
    }

    // ----- 实体类型分布环图 + 高频关系 Top8 条图（纯前端聚合，无新端点）-----
    function ensureChart(elRef, built) {
      if (built || !elRef.value || typeof echarts === 'undefined') return built;
      if (!elRef.value.offsetWidth) return built;
      return echarts.init(elRef.value);
    }

    function fitSize(elRef, inst) {
      var w = elRef.value.offsetWidth;
      var h = elRef.value.offsetHeight;
      if (w && inst && (inst.getWidth() !== w || inst.getHeight() !== h)) inst.resize();
    }

    function renderDist() {
      distChart = ensureChart(distEl, distChart);
      if (!distChart || !distData.value.length) return;
      fitSize(distEl, distChart);
      distChart.setOption({
        tooltip: {
          trigger: 'item',
          confine: true,
          textStyle: { fontSize: 12 },
          formatter: '{b}：{c} 个（{d}%）',
        },
        legend: {
          bottom: 0, icon: 'circle', itemWidth: 10,
          textStyle: { fontSize: 12, color: '#6B7280' },
        },
        series: [{
          type: 'pie',
          radius: ['44%', '70%'],
          center: ['50%', '42%'],
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          emphasis: { label: { show: false } },
          data: distData.value.map(function (d) {
            return { name: d.name, value: d.value, itemStyle: { color: colorOf(d.name) } };
          }),
        }],
      });
    }

    function renderRel() {
      relChart = ensureChart(relEl, relChart);
      if (!relChart || !relData.value.length) return;
      fitSize(relEl, relChart);
      var rows = relData.value.slice().reverse();  // 类目轴自下而上，反转后最大值在顶
      relChart.setOption({
        tooltip: {
          trigger: 'item',
          confine: true,
          textStyle: { fontSize: 12 },
          formatter: '{b}：{c} 条',
        },
        grid: { left: 10, right: 44, top: 6, bottom: 6, containLabel: true },
        xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { show: false }, axisLine: { show: false } },
        yAxis: {
          type: 'category',
          data: rows.map(function (r) { return r.name; }),
          axisLabel: { fontSize: 12, color: '#374151' },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: '#E5E7EB' } },
        },
        series: [{
          type: 'bar',
          barWidth: 14,
          data: rows.map(function (r) { return r.value; }),
          itemStyle: { color: '#2B6E94', borderRadius: [0, 7, 7, 0] },
          label: { show: true, position: 'right', fontSize: 12, color: '#6B7280' },
        }],
      });
    }

    function renderCharts() { renderDist(); renderRel(); }

    function loadCharts() {
      API.getJSON('/api/graph?limit=500').then(function (data) {
        var nodes = data.nodes || [];
        var edges = data.edges || [];
        var tCount = {};
        nodes.forEach(function (n) {
          var t = n.type || '其他';
          tCount[t] = (tCount[t] || 0) + 1;
        });
        distData.value = Object.keys(tCount).map(function (t) {
          return { name: t, value: tCount[t] };
        }).sort(function (a, b) { return b.value - a.value; });
        var rCount = {};
        edges.forEach(function (e) {
          var l = e.label || '关联';
          rCount[l] = (rCount[l] || 0) + 1;
        });
        relData.value = Object.keys(rCount).map(function (l) {
          return { name: l, value: rCount[l] };
        }).sort(function (a, b) { return b.value - a.value; }).slice(0, 8);
        nextTick(renderCharts);
      }).catch(function () { /* 图表区留空，迷你图错误条已提示 */ });
    }

    function goGraph() { location.hash = '#/graph'; }
    function goLibrary() { location.hash = '#/library'; }

    function onActivate(fn) {
      Vue.watch(Store.currentView, function (view) { if (view === 'overview') fn(); });
      if (Store.currentView.value === 'overview') fn();
    }

    onActivate(function () {
      Store.refreshStats();
      // 视图常驻（v-show）：切进来时容器才有尺寸，nextTick 后再建图
      nextTick(function () {
        ensureMiniChart();
        if (!miniRO && miniEl.value && typeof ResizeObserver !== 'undefined') {
          miniRO = new ResizeObserver(function (entries) {
            if (!entries[0].contentRect.width) return;
            if (chart && (chart.getWidth() !== entries[0].contentRect.width)) miniFrozen = null;
            renderMini();
          });
          miniRO.observe(miniEl.value);
        }
        if (!chartsRO && typeof ResizeObserver !== 'undefined') {
          chartsRO = new ResizeObserver(function () { renderCharts(); });
          if (distEl.value) chartsRO.observe(distEl.value);
          if (relEl.value) chartsRO.observe(relEl.value);
        }
        loadMini();
        loadCharts();
      });
    });

    onBeforeUnmount(function () {
      if (miniRO) { miniRO.disconnect(); miniRO = null; }
      if (chartsRO) { chartsRO.disconnect(); chartsRO = null; }
      if (chart) { chart.dispose(); chart = null; }
      if (distChart) { distChart.dispose(); distChart = null; }
      if (relChart) { relChart.dispose(); relChart = null; }
    });

    return {
      stats: stats,
      cards: cards,
      miniEl: miniEl,
      miniNodes: miniNodes,
      miniLoading: miniLoading,
      miniError: miniError,
      distEl: distEl,
      relEl: relEl,
      distData: distData,
      relData: relData,
      goGraph: goGraph,
      goLibrary: goLibrary,
      loadMini: loadMini,
    };
  },
  template: `
    <section>
      <h2 class="view-title">概览</h2>
      <div class="stat-grid">
        <div class="card stat-card" v-for="c in cards" :key="c.key">
          <div class="stat-value">{{ stats[c.key] ?? '—' }}</div>
          <div class="stat-label">{{ c.label }}</div>
        </div>
      </div>
      <div class="ov-grid">
        <div class="card">
          <div class="side-head">
            <div class="side-title">知识图谱速览</div>
            <button class="btn btn-sm" @click="goGraph">进入知识图谱</button>
          </div>
          <div v-if="miniError" class="error-bar">
            {{ miniError }}
            <button class="btn btn-sm" style="margin-left: 8px;" @click="loadMini">重试</button>
          </div>
          <div v-else-if="!miniNodes.length && !miniLoading" class="empty" style="padding: 32px 16px;">
            <p>暂无图谱数据，请先上传课程材料建库</p>
            <button class="btn btn-sm" @click="goLibrary">去知识库管理</button>
          </div>
          <div v-show="miniNodes.length" ref="miniEl" class="mini-graph"></div>
        </div>
        <div class="card">
          <div class="side-head"><div class="side-title">实体类型分布</div></div>
          <div v-if="!distData.length" class="empty" style="padding: 32px 16px;">
            <p>暂无统计数据，建库后自动生成</p>
          </div>
          <div v-show="distData.length" ref="distEl" class="mini-graph"></div>
        </div>
        <div class="card">
          <div class="side-head"><div class="side-title">高频关系 Top 8</div></div>
          <div v-if="!relData.length" class="empty" style="padding: 32px 16px;">
            <p>暂无关系统计，建库后自动生成</p>
          </div>
          <div v-show="relData.length" ref="relEl" class="mini-graph"></div>
        </div>
        <div class="card">
          <div class="side-title">快速开始</div>
          <div class="steps-grid steps-vert">
            <div class="step-item">
              <span class="step-no">1</span>
              <div><h4>上传课程材料</h4><p>在"知识库管理"上传 md / txt / docx 讲义，系统自动解析建库</p></div>
            </div>
            <div class="step-item">
              <span class="step-no">2</span>
              <div><h4>浏览知识图谱</h4><p>查看从课件中自动抽取的实体关系网络，可搜索与筛选</p></div>
            </div>
            <div class="step-item">
              <span class="step-no">3</span>
              <div><h4>开始问答</h4><p>在"RAG 问答"提问课程概念，或在"ReAct 智能体"提出计算复合题</p></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `,
};
