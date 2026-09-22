window.Components = window.Components || {};

// 布局共用件（类型配色/节点尺寸/坐标冻结/标签避碰/包围盒适配）见 components/graph-layout.js：
// 大屏中央图谱与工作台图谱视图共用同一份实现，本文件只保留 Vue 组件外壳。
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
    var sizeObs = null;
    // 力导收敛后的坐标快照；非 null 时 layout='none' + 节点带 x/y，缩放/平移即纯变换
    var frozenPos = null;
    var layout = window.Components.graphLayout;
    var harvest = layout.harvest;

    // 收敛后把整张图等比缩放平移进画布：包围盒与内边距规则见共用件。
    // 视图常驻 v-show 挂载时容器可能是 0×0，此时不冻结，等 ResizeObserver 触发
    function fitToCanvas(pos) {
      if (!pos || !chart) return pos;
      var phone = UI.isPhone();
      var maxR = 0;
      props.nodes.forEach(function (n) {
        maxR = Math.max(maxR, layout.nodeSize(n.degree, phone) / 2);
      });
      return layout.fitToCanvas(pos, {
        width: chart.getWidth(), height: chart.getHeight(),
        maxR: maxR, padRight: 110, padBottom: 52,
      });
    }

    var TYPE_COLORS = layout.TYPE_COLORS;
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

      var labelCap = phone ? 10 : 18;
      var labelSet = layout.placeLabels(props.nodes, frozenPos, {
        cap: labelCap, fontSize: phone ? 11 : 12, keep: props.selectedName,
      });

      var graphNodes = props.nodes.map(function (n) {
        var size = layout.nodeSize(n.degree, phone);
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
