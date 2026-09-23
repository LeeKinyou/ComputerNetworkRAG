window.Components = window.Components || {};

// 学习路径画布（09 §3.5）：手工坐标 + layout:'none'，绝不用力导向。
// 层号由后端 /api/path 算好（path_service._layers），这里只做"层 → 像素"的排版与适配；
// 拓扑逻辑只有一份实现，前端再跑一遍迟早跟后端对不上。
window.Components.pathGraph = {
  props: {
    nodes: { type: Array, default: function () { return []; } },
    edges: { type: Array, default: function () { return []; } },
    planIds: { type: Array, default: function () { return []; } },
    selectedId: { type: String, default: '' },
    mode: { type: String, default: 'layer' },      // layer | ring
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
    var layout = window.Components.graphLayout;

    var NODE_H = 44;
    var ROW_GAP = 18;
    var COL_GAP = 18;
    var LAYER_GAP = 46;
    var MAX_ROWS = 8;          // 同层再多就切子列：40 个孤立节点竖排会拉成 2500px 的长条

    // 三态：颜色 + 文字双通道（06 §2 不允许只靠颜色区分语义）
    var STATE = {
      planned: { fill: '#ECFDF5', border: '#047857', rich: 'done', weight: 2.4 },
      touched: { fill: '#ECFDF5', border: '#34D399', rich: 'done', weight: 1.4 },
      plain: { fill: '#FAFAFA', border: '#D4D4D8', rich: 'idle', weight: 1 },
    };

    function esc(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function planIndexOf(kpId) {
      return props.planIds.indexOf(kpId);
    }

    function stateOf(node) {
      if (planIndexOf(node.kp_id) !== -1) return 'planned';
      return (node.touch_count || 0) > 0 ? 'touched' : 'plain';
    }

    function statusText(node) {
      var head = '第' + node.chapter + '章';
      var i = planIndexOf(node.kp_id);
      if (i !== -1) return head + ' · 必修链第 ' + (i + 1) + ' 步';
      return (node.touch_count || 0) > 0 ? head + ' · 已触达 ' + node.touch_count + ' 次' : head + ' · 未触达';
    }

    function widthOf(node) {
      return Math.min(240, Math.max(
        layout.estimateTextWidth(node.name, 12.5),
        layout.estimateTextWidth(statusText(node), 11),
      ) + 26);
    }

    // 分层坐标：每层按 MAX_ROWS 切成子列，列宽取该层最宽节点，逐层累加 x
    function layerPos(nodes, widths) {
      var byLayer = {}, layers = [];
      nodes.forEach(function (n) {
        var l = n.layer || 0;
        if (!byLayer[l]) { byLayer[l] = []; layers.push(l); }
        byLayer[l].push(n);
      });
      layers.sort(function (a, b) { return a - b; });
      var rows = window.UI.isPhone() ? Math.max(4, Math.floor(MAX_ROWS * 0.75)) : MAX_ROWS;
      var pos = {}, cursor = 0;
      layers.forEach(function (l) {
        var group = byLayer[l], colW = 0;
        group.forEach(function (n) { colW = Math.max(colW, widths[n.kp_id]); });
        group.forEach(function (n, i) {
          pos[n.kp_id] = {
            x: cursor + Math.floor(i / rows) * (colW + COL_GAP) + colW / 2,
            y: (i % rows) * (NODE_H + ROW_GAP) + NODE_H / 2,
          };
        });
        cursor += Math.ceil(group.length / rows) * (colW + COL_GAP) + LAYER_GAP;
      });
      return pos;
    }

    function ringPos(nodes) {
      var pos = {}, n = nodes.length;
      nodes.forEach(function (node, i) {
        var a = (Math.PI * 2 * i) / Math.max(n, 1) - Math.PI / 2;
        pos[node.kp_id] = { x: Math.cos(a) * 100, y: Math.sin(a) * 100 };
      });
      return pos;
    }

    // 包围盒等比放进画布。上限 2 倍：共用件的 fitToCanvas 会放满整块画布，
    // 3 个节点的章会被拉成对角线两端的空白。
    function fitBox(pos) {
      if (!chart) return pos;
      var w = chart.getWidth(), h = chart.getHeight();
      var keys = Object.keys(pos);
      if (!w || !h || !keys.length) return pos;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      keys.forEach(function (k) {
        var p = pos[k];
        if (p.x < minX) minX = p.x;
        if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.y > maxY) maxY = p.y;
      });
      var bw = Math.max(maxX - minX, 1), bh = Math.max(maxY - minY, 1);
      var k = Math.min((w - 100) / bw, (h - 110) / bh, 2);
      var ox = (w - bw * k) / 2, oy = (h - bh * k) / 2;
      var out = {};
      keys.forEach(function (key) {
        out[key] = {
          x: ox + (pos[key].x - minX) * k + (bw * k) / 2,
          y: oy + (pos[key].y - minY) * k + (bh * k) / 2,
        };
      });
      return out;
    }

    function buildOption() {
      var phone = window.UI.isPhone();
      var widths = {};
      props.nodes.forEach(function (n) { widths[n.kp_id] = widthOf(n); });

      var rawPos = props.mode === 'ring' ? ringPos(props.nodes) : layerPos(props.nodes, widths);
      var pos = fitBox(rawPos);

      var graphNodes = props.nodes.map(function (n) {
        var state = STATE[stateOf(n)];
        var selected = n.kp_id === props.selectedId;
        var line = '{title|' + n.name + '}\n{' + state.rich + '|' + statusText(n) + '}';
        return {
          id: n.kp_id,
          name: n.name,
          x: pos[n.kp_id].x,
          y: pos[n.kp_id].y,
          symbol: 'roundRect',
          symbolSize: [widths[n.kp_id], NODE_H],
          itemStyle: {
            color: state.fill,
            borderColor: selected ? '#09090B' : state.border,
            borderWidth: selected ? 2.4 : state.weight,
          },
          label: { formatter: function () { return line; } },
        };
      });

      var graphEdges = props.edges.map(function (e) {
        var planned = planIndexOf(e.source) !== -1 && planIndexOf(e.target) !== -1;
        return {
          source: e.source,
          target: e.target,
          lineStyle: {
            color: planned ? '#047857' : '#C9C9CF',
            width: planned ? 2.2 : 1.3,
            curveness: props.mode === 'ring' ? 0.22 : 0,
          },
        };
      });

      return {
        tooltip: {
          show: !phone,
          confine: true,
          backgroundColor: '#fff',
          borderColor: '#E4E4E7',
          textStyle: { fontSize: 12, color: '#09090B' },
          extraCssText: 'max-width: 380px; white-space: normal;',
          formatter: function (params) {
            if (params.dataType === 'edge') {
              var e = props.edges[params.dataIndex] || {};
              return '<b>前置依赖</b><br/>' + esc(e.reason || '未给出依据')
                + '<br/><span style="color:#71717A">置信度 '
                + Number(e.confidence || 0).toFixed(2) + '</span>';
            }
            var n = props.nodes[params.dataIndex] || {};
            var html = '<b>' + esc(n.name) + '</b>（' + esc(n.type || '概念') + '）<br/>'
              + '第 ' + n.chapter + ' 章 · 图谱度数 ' + (n.degree || 0) + '<br/>'
              + esc(n.description || '');
            return html.length > 320 ? html.slice(0, 320) + '…' : html;
          },
        },
        series: [{
          type: 'graph',
          layout: 'none',
          data: graphNodes,
          links: graphEdges,
          roam: phone ? 'scale' : true,
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: phone ? 6 : 9,
          label: {
            show: true,
            position: 'inside',
            align: 'center',
            rich: {
              title: { fontSize: 12.5, fontWeight: 600, color: '#09090B', lineHeight: 16 },
              done: { fontSize: 11, color: '#047857', lineHeight: 14 },
              idle: { fontSize: 11, color: '#A1A1AA', lineHeight: 14 },
            },
          },
          emphasis: { focus: 'adjacency' },
          scaleLimit: { min: 0.4, max: 4 },
        }],
      };
    }

    function render() {
      if (!chart || !props.nodes.length) return;
      chart.setOption(buildOption(), true);
    }

    function resize() {
      if (!chart) return;
      chart.resize();
      render();
    }

    onMounted(function () {
      chart = echarts.init(el.value, null, { animation: false });
      chart.on('click', function (params) {
        if (params.dataType === 'node') {
          var n = props.nodes[params.dataIndex];
          if (n) ctx.emit('node-click', n);
        }
      });
      render();
      // 视图常驻 + v-show：从隐藏切到可见时容器尺寸从 0 变化，坐标是像素值，必须重排
      if (typeof ResizeObserver !== 'undefined') {
        sizeObs = new ResizeObserver(function (entries) {
          if (!entries[0].contentRect.width) return;
          resize();
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

    watch(function () { return [props.nodes, props.edges, props.planIds, props.mode]; }, render);
    watch(function () { return props.selectedId; }, render);

    return { el: el };
  },
  template: '<div ref="el" class="graph-canvas path-canvas"></div>',
};
