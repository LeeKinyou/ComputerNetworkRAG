window.Components = window.Components || {};

// 类型配色表：模块级导出，概览页迷你图复用同一套（06 §2：设计令牌全局唯一来源）
// harvest：从 echarts 内部 graph 模型读取收敛后的节点坐标。
// 供"力导布局收敛后冻结坐标"使用——layout 切到 'none' 后 roam 缩放是纯视口变换，
// 不会出现"缩放后节点聚拢、连线射向旧坐标空白区"的点线脱钩问题。
window.Components.graphView = {
  TYPE_COLORS: {
    '协议': '#2B6E94',
    '设备': '#9A6B2F',
    '层次': '#3D7A33',
    '地址': '#7A4A94',
    '算法': '#B04A3A',
    '性能指标': '#2F8A83',
    '概念': '#5B7183',
    'Other': '#98A2AB',
  },
  harvest: function (chart) {
    if (!chart) return null;
    try {
      var series = chart.getModel().getSeriesByIndex(0);
      var graph = series && series.getGraph();
      if (!graph) return null;
      var pos = null;
      graph.eachNode(function (node) {
        // echarts 5 的 getLayout() 返回 [x, y] 数组（兼容 {x, y} 形态）；
        // 部分构建里 node.name 为 undefined，id 恒有值，以 id 为主键
        var l = node.getLayout();
        var x = Array.isArray(l) ? l[0] : l && l.x;
        var y = Array.isArray(l) ? l[1] : l && l.y;
        var key = node.id != null ? node.id : node.name;
        if (key != null && typeof x === 'number' && typeof y === 'number') {
          pos = pos || {};
          pos[key] = { x: x, y: y };
        }
      });
      return pos;
    } catch (e) { return null; }
  },
  props: {
    nodes: { type: Array, default: function () { return []; } },
    edges: { type: Array, default: function () { return []; } },
    types: { type: Array, default: function () { return []; } },
    selectedName: { type: String, default: '' },
  },
  emits: ['node-click'],
  setup: function (props, ctx) {
    var ref = Vue.ref;
    var watch = Vue.watch;
    var onMounted = Vue.onMounted;
    var onBeforeUnmount = Vue.onBeforeUnmount;

    var el = ref(null);
    var chart = null;
    var sizeObs = null;
    // 力导收敛后的坐标快照；非 null 时 layout='none' + 节点带 x/y，缩放/平移即纯变换
    var frozenPos = null;
    var harvest = window.Components.graphView.harvest;

    var TYPE_COLORS = window.Components.graphView.TYPE_COLORS;
    function colorOf(type) { return TYPE_COLORS[type] || '#98A2AB'; }

    function esc(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function buildOption() {
      var presentTypes = props.types.filter(function (t) {
        return props.nodes.some(function (n) { return n.type === t; });
      });
      var categories = presentTypes.map(function (t) { return { name: t }; });
      var catIndex = {};
      presentTypes.forEach(function (t, i) { catIndex[t] = i; });

      var graphNodes = props.nodes.map(function (n) {
        var size = 16 + Math.min(30, (n.degree || 0) * 3);
        var selected = n.id === props.selectedName;
        var item = {
          id: n.id,
          name: n.name,
          category: catIndex[n.type] !== undefined ? catIndex[n.type] : 0,
          symbolSize: size,
          itemStyle: {
            color: colorOf(n.type),
            borderColor: selected ? '#1A1B1C' : 'rgba(0,0,0,0)',
            borderWidth: selected ? 2 : 0,
          },
        };
        if (frozenPos) {
          var fp = frozenPos[n.id] || frozenPos[n.name];
          if (fp) { item.x = fp.x; item.y = fp.y; }
        }
        return item;
      });
      var graphEdges = props.edges.map(function (e) {
        return { source: e.source, target: e.target };
      });

      return {
        tooltip: {
          confine: true,
          textStyle: { fontSize: 12 },
          extraCssText: 'max-width: 380px; white-space: normal;',
          formatter: function (params) {
            if (params.dataType === 'edge') {
              var raw = props.edges[params.dataIndex] || {};
              var html = '<b>' + esc(raw.label || '关联') + '</b><br/>' + esc(raw.description || '');
              return html.length > 320 ? html.slice(0, 320) + '…' : html;
            }
            var n = props.nodes[params.dataIndex] || {};
            var h = '<b>' + esc(n.name) + '</b>（' + esc(n.type || '概念') + '）<br/>' + esc(n.description || '');
            return h.length > 320 ? h.slice(0, 320) + '…' : h;
          },
        },
        legend: presentTypes.length ? {
          data: presentTypes,
          bottom: 6,
          icon: 'circle',
          itemWidth: 10,
          textStyle: { fontSize: 12, color: '#6B7280' },
        } : undefined,
        series: [{
          type: 'graph',
          layout: frozenPos ? 'none' : 'force',
          data: graphNodes,
          links: graphEdges,
          categories: categories,
          roam: true,
          draggable: true,
          force: {
            repulsion: 260,
            edgeLength: [40, 110],
            gravity: 0.08,
            layoutAnimation: false,
          },
          label: { show: true, fontSize: 11, color: '#1A1B1C' },
          emphasis: { focus: 'adjacency', label: { fontWeight: 600 } },
          scaleLimit: { min: 0.4, max: 4 },
        }],
      };
    }

    function render() {
      if (!chart) return;
      chart.setOption(buildOption(), true);
    }

    // 选中态等轻量更新走 merge：不整体替换 option，保留当前缩放/平移视口
    function renderSoft() {
      if (!chart) return;
      chart.setOption(buildOption());
    }

    // 持久邻接高亮：选中节点及其一跳邻居保持 emphasis，其余淡出；
    // 抽屉里点关联实体时焦点随之切换（downplay 旧焦点 → highlight 新焦点）
    function applyFocus(name) {
      if (!chart) return;
      chart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
      if (name) {
        setTimeout(function () {
          if (chart && props.nodes.some(function (n) { return n.id === name; })) {
            chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: name });
          }
        }, 0);
      }
    }

    onMounted(function () {
      chart = echarts.init(el.value);
      chart.on('click', function (params) {
        if (params.dataType === 'node') {
          var n = props.nodes[params.dataIndex];
          if (n) ctx.emit('node-click', n);
        }
      });
      // 力导布局收敛（finished 且所有节点均有坐标）后冻结坐标；
      // 此后缩放/平移的 finished 不再处理。finished 会在布局早期触发，
      // 此时多数节点还没有坐标，必须等覆盖完整再冻结
      chart.on('finished', function () {
        if (frozenPos || !props.nodes.length) return;
        setTimeout(function () {
          if (frozenPos || !chart || !props.nodes.length) return;
          var pos = harvest(chart);
          if (pos && Object.keys(pos).length >= props.nodes.length) {
            frozenPos = pos;
            render();
          }
        }, 0);
      });
      // 冻结后拖拽节点：静默更新坐标快照，后续渲染沿用拖后位置
      if (chart.getZr()) {
        chart.getZr().on('dragend', function () {
          if (!frozenPos) return;
          var pos = harvest(chart);
          if (pos) frozenPos = pos;
        });
      }
      render();
      // 视图常驻 + v-show：从隐藏切到可见时容器尺寸从 0 变化，需重新布局；
      // 冻结坐标是像素坐标，尺寸变化后必须重跑力导，否则整体偏在一侧
      if (typeof ResizeObserver !== 'undefined') {
        sizeObs = new ResizeObserver(function (entries) {
          if (!entries[0].contentRect.width) return;
          chart.resize();
          frozenPos = null;
          render();
        });
        sizeObs.observe(el.value);
      }
      window.addEventListener('resize', resize);
    });
    onBeforeUnmount(function () {
      if (sizeObs) { sizeObs.disconnect(); sizeObs = null; }
      window.removeEventListener('resize', resize);
      if (chart) { chart.dispose(); chart = null; }
    });

    function resize() { if (chart) chart.resize(); }
    function relayout() { frozenPos = null; render(); }

    watch(function () { return props.nodes; }, function () { frozenPos = null; render(); });
    watch(function () { return props.selectedName; }, function (name) { renderSoft(); applyFocus(name); });

    return { el: el, relayout: relayout, resize: resize };
  },
  template: '<div ref="el" class="graph-canvas"></div>',
};
