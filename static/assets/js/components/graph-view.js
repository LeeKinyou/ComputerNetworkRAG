window.Components = window.Components || {};

// ECharts 力导向图封装：类型配色、hover 提示、节点点击回调
window.Components.graphView = {
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

    var TYPE_COLORS = {
      '协议': '#2B6E94',
      '设备': '#9A6B2F',
      '层次': '#3D7A33',
      '地址': '#7A4A94',
      '算法': '#B04A3A',
      '性能指标': '#2F8A83',
      '概念': '#5B7183',
      'Other': '#98A2AB',
    };
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
        return {
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
          layout: 'force',
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

    onMounted(function () {
      chart = echarts.init(el.value);
      chart.on('click', function (params) {
        if (params.dataType === 'node') {
          var n = props.nodes[params.dataIndex];
          if (n) ctx.emit('node-click', n);
        }
      });
      render();
      window.addEventListener('resize', resize);
    });
    onBeforeUnmount(function () {
      window.removeEventListener('resize', resize);
      if (chart) { chart.dispose(); chart = null; }
    });

    function resize() { if (chart) chart.resize(); }
    function relayout() { render(); }

    watch(function () { return props.nodes; }, render);
    watch(function () { return props.selectedName; }, render);

    return { el: el, relayout: relayout, resize: resize };
  },
  template: '<div ref="el" class="graph-canvas"></div>',
};
