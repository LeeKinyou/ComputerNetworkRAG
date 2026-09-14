window.Components = window.Components || {};

// 类型配色表：模块级导出，概览页迷你图复用同一套（06 §2：设计令牌全局唯一来源）
// harvest：从 echarts 内部 graph 模型读取收敛后的节点坐标。
// 供"力导布局收敛后冻结坐标"使用——layout 切到 'none' 后 roam 缩放是纯视口变换，
// 不会出现"缩放后节点聚拢、连线射向旧坐标空白区"的点线脱钩问题。
window.Components.graphView = {
  // 与 LightRAG 控制台的浅色图谱取色风格对齐：高饱和 600 阶、白底可辨
  TYPE_COLORS: {
    '协议': '#2563EB',
    '设备': '#EA580C',
    '层次': '#0D9488',
    '地址': '#7C3AED',
    '算法': '#DC2626',
    '性能指标': '#CA8A04',
    '概念': '#475569',
    'Other': '#94A3B8',
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

    // 收敛后把整张图等比缩放平移进画布：力导的稳定尺度取决于节点数/斥力，
    // 直接照搬原始坐标要么挤成中央一团、要么撑破边界（实测 1280px 下都出现过）。
    // 统一按包围盒缩放到画布内边距，留出右侧标签带与底部图例带
    function fitToCanvas(pos) {
      if (!pos || !chart) return pos;
      var w = chart.getWidth(), h = chart.getHeight();
      // 视图常驻 v-show 挂载时容器可能是 0×0，此时不冻结，等 ResizeObserver 触发
      if (!w || !h) return null;
      var keys = Object.keys(pos);
      if (!keys.length) return pos;
      var maxR = 0;
      props.nodes.forEach(function (n) {
        var size = UI.isPhone() ? 8 + Math.min(16, (n.degree || 0) * 1.8)
                                : 14 + Math.min(20, (n.degree || 0) * 2.2);
        maxR = Math.max(maxR, size / 2);
      });
      var padX = maxR + 4, padTop = maxR + 4;
      var padRight = maxR + 110;   // 标签在节点右侧
      var padBottom = maxR + 52;   // 图例带
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      keys.forEach(function (k) {
        var p = pos[k];
        if (p.x < minX) minX = p.x; if (p.x > maxX) maxX = p.x;
        if (p.y < minY) minY = p.y; if (p.y > maxY) maxY = p.y;
      });
      var bw = Math.max(maxX - minX, 1), bh = Math.max(maxY - minY, 1);
      var tw = Math.max(w - padX - padRight, 1);
      var th = Math.max(h - padTop - padBottom, 1);
      var k = Math.min(tw / bw, th / bh);
      var fitted = {};
      keys.forEach(function (key) {
        var p = pos[key];
        fitted[key] = {
          x: padX + (p.x - minX) * k + (tw - bw * k) / 2,
          y: padTop + (p.y - minY) * k + (th - bh * k) / 2,
        };
      });
      return fitted;
    }

    var TYPE_COLORS = window.Components.graphView.TYPE_COLORS;
    function colorOf(type) { return TYPE_COLORS[type] || '#94A3B8'; }

    function esc(s) {
      return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function buildOption() {
      var phone = window.UI.isPhone();
      var presentTypes = props.types.filter(function (t) {
        return props.nodes.some(function (n) { return n.type === t; });
      });
      var categories = presentTypes.map(function (t) { return { name: t }; });
      var catIndex = {};
      presentTypes.forEach(function (t, i) { catIndex[t] = i; });

      // 标签避碰：先取度数最高的候选，再按估算的标签矩形贪心装箱——
      // 度数高者先占位，被压住的直接不显示（ECharts 的 hideOverlap 对 graph
      // 系列不生效，实测照叠）。无文字测量 API：CJK 按字号、ASCII 按 0.62 估宽
      function estTextWidth(text, fs) {
        var w = 0;
        for (var i = 0; i < text.length; i++) {
          var code = text.charCodeAt(i);
          w += ((code >= 0x2E80 && code <= 0x9FFF) || (code >= 0xFF00 && code <= 0xFFEF)) ? fs : fs * 0.62;
        }
        return w;
      }
      var labelCap = phone ? 10 : 18;
      var labelSet = {};
      var placed = [];
      props.nodes.slice().sort(function (a, b) { return (b.degree || 0) - (a.degree || 0); })
        .forEach(function (n) {
          if (placed.length >= labelCap && n.id !== props.selectedName) return;
          var fs = phone ? 11 : 12;
          var p = frozenPos ? (frozenPos[n.id] || frozenPos[n.name]) : null;
          if (p) {
            var halfW = estTextWidth(n.name, fs) / 2 + 10;
            var cx = p.x + 4 + halfW, cy = p.y, halfH = fs * 0.72 + 5;
            for (var i = 0; i < placed.length; i++) {
              var q = placed[i];
              if (Math.abs(cx - q.cx) < halfW + q.halfW && Math.abs(cy - q.cy) < halfH + q.halfH) return;
            }
            placed.push({ cx: cx, cy: cy, halfW: halfW, halfH: halfH });
          }
          labelSet[n.id] = true;
        });

      var graphNodes = props.nodes.map(function (n) {
        // 节点不能太大：310 节点规模下最近中心距约 35px，直径超过它就会互相压叠
        var size = phone ? 8 + Math.min(16, (n.degree || 0) * 1.8)
                         : 14 + Math.min(20, (n.degree || 0) * 2.2);
        var selected = n.id === props.selectedName;
        var item = {
          id: n.id,
          name: n.name,
          category: catIndex[n.type] !== undefined ? catIndex[n.type] : 0,
          symbolSize: size,
          itemStyle: {
            color: colorOf(n.type),
            borderColor: selected ? '#09090B' : 'rgba(0,0,0,0)',
            borderWidth: selected ? 2 : 0,
          },
        };
        // 标签定位写在 item 级（labelLayout 函数会让标签丢回居中定位，勿用）
        item.label = {
          show: !!labelSet[n.id],
          fontSize: phone ? 11 : 12, color: '#09090B',
          position: 'right', distance: 4,
          textBorderColor: '#fff', textBorderWidth: 2,
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
          // 触屏点选即弹详情面板，tooltip 只会残留在遮罩下，手机端直接关掉
          show: !phone,
          confine: true,
          backgroundColor: '#fff',
          borderColor: '#E4E4E7',
          textStyle: { fontSize: 12, color: '#09090B' },
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
          // 小屏一行排不下会被裁掉，改分页式图例并限定左右边界
          type: phone ? 'scroll' : 'plain',
          left: phone ? 4 : 'center',
          right: phone ? 4 : undefined,
          icon: 'circle',
          itemWidth: 10,
          itemGap: phone ? 8 : undefined,
          textStyle: { fontSize: phone ? 11 : 12, color: '#71717A' },
        } : undefined,
        series: [{
          type: 'graph',
          layout: frozenPos ? 'none' : 'force',
          data: graphNodes,
          links: graphEdges,
          categories: categories,
          // 触屏下 roam:true 会把单指拖拽吞成画布平移，页面就划不动了；
          // 'scale' 只接双指捏合缩放，单指手势交还浏览器
          roam: phone ? 'scale' : true,
          draggable: true,
          // 力导只负责局部排布：尺度由收敛后的 fitToCanvas 统一缩放进画布。
          // 斥力过小会把 310 节点收成中央一团（符号压叠），过大又会被 fit 缩回，
          // 这档是在 1500×900 下实测的平衡点
          force: {
            repulsion: phone ? 300 : 800,
            edgeLength: phone ? [30, 80] : [60, 150],
            gravity: phone ? 0.18 : 0.1,
            layoutAnimation: false,
          },
          // 标签置于节点右侧并描白边：白底图上压着连线与相邻节点也能读清
          label: {
            show: true, fontSize: phone ? 11 : 12, color: '#09090B',
            position: 'right', distance: 4,
            textBorderColor: '#fff', textBorderWidth: 2,
          },
          // 不使用函数式 labelLayout：它会让标签丢回居中定位
          // （实测 position:'right' 配 labelLayout 后标签压在节点上）。
          // 标签数量已由 labelCap 控制，密度可控
          emphasis: { focus: 'adjacency', label: { fontWeight: 600 } },
          scaleLimit: { min: 0.4, max: 4 },
        }],
      };
    }

    function render() {
      if (!chart) return;
      chart.setOption(buildOption(), true);
      // 全量替换会清掉 dispatchAction 的 highlight 状态：
      // 冻结/尺寸变化触发的重渲染必须把当前选中节点的邻接焦点补回来，
      // 否则第一次点击（发生在力导收敛前）会被随后的冻结渲染冲掉
      applyFocus(props.selectedName);
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

    // 收敛后立刻冻结：不依赖 'finished'（它在容器未布局时可能拿不到坐标），
    // 力导在 layoutAnimation:false 下是同步算完的，render 后即可 harvest
    function freezeIfReady() {
      if (frozenPos || !chart || !props.nodes.length) return;
      var pos = harvest(chart);
      if (!pos || Object.keys(pos).length < props.nodes.length) return;
      var fitted = fitToCanvas(pos);
      if (!fitted) return;
      frozenPos = fitted;
      render();
    }

    onMounted(function () {
      // 关动画：力导→冻结坐标的重渲染过渡在 310 节点下既慢又会被 resize 打断，
      // 中间帧正好是"节点标签全糊成一团"的样子；直接让布局一步落位
      chart = echarts.init(el.value, null, { animation: false });
      chart.on('click', function (params) {
        if (params.dataType === 'node') {
          var n = props.nodes[params.dataIndex];
          if (n) ctx.emit('node-click', n);
        }
      });
      // 冻结已改为 render 后同步 freezeIfReady()：'finished' 在容器未布局时
      // 拿不到坐标会静默失效，不再依赖它
      if (chart.getZr()) {
        chart.getZr().on('dragend', function () {
          if (!frozenPos) return;
          var pos = harvest(chart);
          if (pos) frozenPos = pos;
        });
      }
      render();
      freezeIfReady();
      // 视图常驻 + v-show：从隐藏切到可见时容器尺寸从 0 变化，需重新布局；
      // 冻结坐标是像素坐标，尺寸变化后必须重跑力导，否则整体偏在一侧
      if (typeof ResizeObserver !== 'undefined') {
        sizeObs = new ResizeObserver(function (entries) {
          if (!entries[0].contentRect.width) return;
          chart.resize();
          frozenPos = null;
          render();
          freezeIfReady();
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
