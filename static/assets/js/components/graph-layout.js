/* 图谱布局共用件（09 §2.3 / §2.5）：大屏中央图谱与工作台图谱视图共用一份实现，
   避免"力导收敛后冻结坐标""标签贪心避碰""包围盒等比适配"三处逻辑各自漂移。
   纯函数、无 Vue 依赖、不碰 DOM —— 大屏与工作台两套生命周期都能用。 */
window.Components = window.Components || {};

window.Components.graphLayout = {
  // 类型配色：设计令牌全局唯一来源。浅色 600 阶、白底可辨；
  // 深色大屏直接沿用，靠节点描边与辉光拉开层次。
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

  // 节点直径：度数映射到 14~34px（手机端整体收一档）。
  // 节点不能太大：300+ 节点规模下最近中心距约 35px，直径超过它就会互相压叠。
  nodeSize: function (degree, phone) {
    return phone ? 8 + Math.min(16, (degree || 0) * 1.8)
                 : 14 + Math.min(20, (degree || 0) * 2.2);
  },

  // 无文字测量 API：CJK 按字号、ASCII 按 0.62 估宽
  estimateTextWidth: function (text, fontSize) {
    var w = 0;
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      w += ((code >= 0x2E80 && code <= 0x9FFF) || (code >= 0xFF00 && code <= 0xFFEF))
        ? fontSize : fontSize * 0.62;
    }
    return w;
  },

  // 从 echarts 内部 graph 模型读取收敛后的节点坐标。
  // 供"力导布局收敛后冻结坐标"使用——layout 切到 'none' 后 roam 缩放是纯视口变换，
  // 不会出现"缩放后节点聚拢、连线射向旧坐标空白区"的点线脱钩问题。
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

  // 标签贪心避碰：先取度数最高的候选，再按估算的标签矩形装箱——
  // 度数高者先占位，被压住的直接不显示（ECharts 的 hideOverlap 对 graph
  // 系列不生效，实测照叠）。返回 {节点 id: true} 的显示集合。
  // opts: { cap, fontSize, keep }——keep 为当前选中/聚焦节点，超上限也保留。
  placeLabels: function (nodes, frozenPos, opts) {
    var cap = (opts && opts.cap) || 18;
    var fontSize = (opts && opts.fontSize) || 12;
    var keep = (opts && opts.keep) || '';
    var labelSet = {};
    var placed = [];
    nodes.slice().sort(function (a, b) { return (b.degree || 0) - (a.degree || 0); })
      .forEach(function (n) {
        if (placed.length >= cap && n.id !== keep) return;
        var p = frozenPos ? (frozenPos[n.id] || frozenPos[n.name]) : null;
        if (p) {
          var halfW = window.Components.graphLayout.estimateTextWidth(n.name, fontSize) / 2 + 10;
          var cx = p.x + 4 + halfW, cy = p.y, halfH = fontSize * 0.72 + 5;
          for (var i = 0; i < placed.length; i++) {
            var q = placed[i];
            if (Math.abs(cx - q.cx) < halfW + q.halfW
                && Math.abs(cy - q.cy) < halfH + q.halfH) return;
          }
          placed.push({ cx: cx, cy: cy, halfW: halfW, halfH: halfH });
        }
        labelSet[n.id] = true;
      });
    return labelSet;
  },

  // 收敛后把整张图等比缩放平移进画布：力导的稳定尺度取决于节点数/斥力，
  // 直接照搬原始坐标要么挤成中央一团、要么撑破边界（实测 1280px 下都出现过）。
  // opts: { width, height, maxR, padRight, padBottom }；
  // 容器 0×0（v-show 隐藏时）返回 null，调用方不冻结、等尺寸就绪再跑。
  fitToCanvas: function (pos, opts) {
    if (!pos) return pos;
    var w = opts.width, h = opts.height;
    if (!w || !h) return null;
    var keys = Object.keys(pos);
    if (!keys.length) return pos;
    var maxR = opts.maxR || 8;
    var padX = maxR + 4, padTop = maxR + 4;
    var padRight = maxR + (opts.padRight || 0);    // 标签在节点右侧，留标签带
    var padBottom = maxR + (opts.padBottom || 0);  // 图例带
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
  },
};
