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
  emits: ['node-click', 'cap'],
  setup: function (props, ctx) {
    var ref = Vue.ref;
    var watch = Vue.watch;
    var onMounted = Vue.onMounted;
    var onBeforeUnmount = Vue.onBeforeUnmount;

    var el = ref(null);
    var chart = null;
    var drawnNodes = [];
    var sizeObs = null;
    var layout = window.Components.graphLayout;

    var NODE_H = 44;
    var ROW_GAP = 18;
    var COL_GAP = 18;
    var LAYER_GAP = 46;
    var MAX_ROWS = 8;          // 同层再多就切子列：40 个孤立节点竖排会拉成 2500px 的长条
    var MARGIN = 24;           // 方块边缘到容器边的最小距离

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

    function widestOf(nodes, widths) {
      var w = 0;
      nodes.forEach(function (n) { w = Math.max(w, widths[n.kp_id]); });
      return w;
    }

    // 同层竖排行数：容量估算与真实排版必须用同一个值，否则"放得下"是假的
    function rowsPerLayer() {
      return window.UI.isPhone()
        ? Math.max(4, Math.floor(MAX_ROWS * 0.75))
        : MAX_ROWS;
    }

    // 画布容量：坐标会被等比塞进容器，而 symbolSize 是绝对像素，所以"放得下几个"
    // 必须在这里算死。少算这一步，280 个节点会被缩成行距 7px 对高 44px 的一整块色块。
    // 容器尺寸还没就绪（v-show 隐藏时）返回全集，交给 ResizeObserver 重排后再裁。
    function fitCapacity(nodes, widths, w, h) {
      if (!w || !h) return nodes.length;
      var rows = Math.max(1, Math.min(rowsPerLayer(), Math.floor((h - 2 * MARGIN - ROW_GAP) / (NODE_H + ROW_GAP))));
      var cols = Math.max(1, Math.floor((w - 2 * MARGIN - COL_GAP) / (widestOf(nodes, widths) + COL_GAP)));
      return rows * cols;
    }

    // 环形的上限是圆周长，比分层更小：方块宽 ~200px 时 1000×620 的画布只绕得下几个
    function ringCapacity(nodes, widths, w, h) {
      if (!w || !h) return nodes.length;
      var r = ringRadius(w, h, widestOf(nodes, widths));
      return Math.max(1, Math.floor((2 * Math.PI * r) / (widestOf(nodes, widths) + COL_GAP)));
    }

    // 分层坐标：每层按 rowsPerLayer 切成子列，列宽取该层最宽节点，逐层累加 x
    function layerPos(nodes, widths) {
      var byLayer = {}, layers = [];
      nodes.forEach(function (n) {
        var l = n.layer || 0;
        if (!byLayer[l]) { byLayer[l] = []; layers.push(l); }
        byLayer[l].push(n);
      });
      layers.sort(function (a, b) { return a - b; });
      var rows = rowsPerLayer();
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

    function ringPos(nodes, radius) {
      var pos = {}, n = nodes.length;
      nodes.forEach(function (node, i) {
        var a = (Math.PI * 2 * i) / Math.max(n, 1) - Math.PI / 2;
        pos[node.kp_id] = { x: Math.cos(a) * radius, y: Math.sin(a) * radius };
      });
      return pos;
    }

    // 半径必须给方块自身留出半宽：否则 12 点方向的方块上半截在容器外
    function ringRadius(w, h, maxW) {
      return Math.max(40, Math.min(w, h) / 2 - MARGIN - Math.max(maxW, NODE_H) / 2);
    }

    function bbox(pos) {
      var keys = Object.keys(pos);
      var b = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
      keys.forEach(function (k) {
        var p = pos[k];
        b.minX = Math.min(b.minX, p.x); b.maxX = Math.max(b.maxX, p.x);
        b.minY = Math.min(b.minY, p.y); b.maxY = Math.max(b.maxY, p.y);
      });
      b.w = Math.max(b.maxX - b.minX, 1);
      b.h = Math.max(b.maxY - b.minY, 1);
      return b;
    }

    // 装得下 = 中心跨度 + 方块自身尺寸 ≤ 容器减去两侧留白
    function boxFits(b, maxW, w, h) {
      if (!w || !h) return true;
      return b.w + maxW <= w - 2 * MARGIN && b.h + NODE_H <= h - 2 * MARGIN;
    }

    // 包围盒等比放进画布：只允许放大，不允许缩小。symbolSize 是绝对像素，
    // k<1 意味着"坐标靠近而方块不缩"，实测 280 节点时行距 7px 对高 44px 直接叠成色块。
    // 放大上限取"画布可用宽度 ÷ 中心跨度"，且分子先扣掉方块自身半宽——
    // 否则最外一列会被推出容器（planDraw 已保证 k=1 时装得下，这里只可能再放大）。
    // 上限 2 倍：3 个节点的章被拉满整块画布会成了对角线两端的空白。
    function fitBox(pos, maxW) {
      if (!chart) return pos;
      var w = chart.getWidth(), h = chart.getHeight();
      var keys = Object.keys(pos);
      if (!w || !h || !keys.length) return pos;
      var b = bbox(pos);
      var k = Math.max(1, Math.min((w - 2 * MARGIN - maxW) / b.w, (h - 2 * MARGIN - NODE_H) / b.h, 2));
      var ox = (w - b.w * k) / 2, oy = (h - b.h * k) / 2;
      var out = {};
      keys.forEach(function (key) {
        out[key] = {
          x: ox + (pos[key].x - b.minX) * k,
          y: oy + (pos[key].y - b.minY) * k,
        };
      });
      return out;
    }

    // 决定"这一次画哪些"：容量不足就按后端给定的章号+度数顺序截断，
    // 环形放不下就退回分层。截断多少由 render() 通过 cap 事件告诉视图，
    // 不能悄悄少画——用户会以为这一章就只有这么几个知识点。
    function planDraw() {
      var w = chart ? chart.getWidth() : 0, h = chart ? chart.getHeight() : 0;
      var widths = {};
      props.nodes.forEach(function (n) { widths[n.kp_id] = widthOf(n); });
      var maxW = widestOf(props.nodes, widths);

      var mode = props.mode, fellBack = false;
      if (mode === 'ring' && props.nodes.length > ringCapacity(props.nodes, widths, w, h)) {
        mode = 'layer';
        fellBack = true;
      }
      var cap = mode === 'ring' ? props.nodes.length : fitCapacity(props.nodes, widths, w, h);
      var radius = ringRadius(w, h, maxW);
      var drawn = props.nodes;
      if (drawn.length > cap) drawn = drawn.slice(0, cap);
      var pos = mode === 'ring' ? ringPos(drawn, radius) : layerPos(drawn, widths);

      // 面积估算只保证"总数塞得进一格"，多层展开的横向游标仍可能超界：
      // 按包围盒实测收紧，直到真的装得下（只剩 1 个节点时停止）。
      while (drawn.length > 1 && !boxFits(bbox(pos), maxW, w, h)) {
        cap = Math.max(1, Math.floor(cap * 0.8));
        drawn = props.nodes.slice(0, cap);
        pos = mode === 'ring' ? ringPos(drawn, radius) : layerPos(drawn, widths);
      }

      return {
        widths: widths, mode: mode, drawn: drawn, pos: pos,
        fellBack: fellBack, maxW: maxW,
      };
    }

    function buildOption(plan) {
      var phone = window.UI.isPhone();
      var widths = plan.widths;

      var pos = fitBox(plan.pos, plan.maxW);

      var onCanvas = {};
      plan.drawn.forEach(function (n) { onCanvas[n.kp_id] = true; });
      function isDrawn(id) { return !!onCanvas[id]; }

      var graphNodes = plan.drawn.map(function (n) {
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

      // 截断后要把边一起裁到已绘制节点集内：留一条悬空边 ECharts 关系图直接报错
      var edgeList = props.edges.filter(function (e) {
        return isDrawn(e.source) && isDrawn(e.target);
      });
      var graphEdges = edgeList.map(function (e) {
        var planned = planIndexOf(e.source) !== -1 && planIndexOf(e.target) !== -1;
        return {
          source: e.source,
          target: e.target,
          lineStyle: {
            color: planned ? '#047857' : '#C9C9CF',
            width: planned ? 2.2 : 1.3,
            curveness: plan.mode === 'ring' ? 0.22 : 0,
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
              var e = edgeList[params.dataIndex] || {};
              return '<b>前置依赖</b><br/>' + esc(e.reason || '未给出依据')
                + '<br/><span style="color:#71717A">置信度 '
                + Number(e.confidence || 0).toFixed(2) + '</span>';
            }
            var n = plan.drawn[params.dataIndex] || {};
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
      var plan = planDraw();
      drawnNodes = plan.drawn;
      ctx.emit('cap', {
        drawn: plan.drawn.length,
        total: props.nodes.length,
        fellBack: plan.fellBack,
      });
      chart.setOption(buildOption(plan), true);
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
          // dataIndex 是"已绘制序列"的下标，不是 props.nodes 的下标：截断后两者不等长
          var n = drawnNodes[params.dataIndex];
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
