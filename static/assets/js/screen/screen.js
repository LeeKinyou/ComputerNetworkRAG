/* 大屏渲染与动效（09 §2.1 / §2.5 / Task 5.7）：7 数字卡 + 6 张统计图 + 中央图谱 + 跑马灯。
   纯 CDN ECharts，无框架依赖，与工作台两套生命周期互不干扰（§2.2）。
   数据两条线：/api/screen/overview 每 30s，/api/graph 每 5 分钟（全量重排代价高）。
   任一图取数或渲染失败只降级自己：面板保留占位文字，其余图照常渲染（§2.1 第 2 条）。 */
(function () {
  var LAYOUT = window.Components.graphLayout;
  var TYPE_COLORS = LAYOUT.TYPE_COLORS;

  var BASE_W = 1920;
  var BASE_H = 1080;
  var POLL_MS = 30000;          // 总览轮询：数字卡与六张统计图
  var RETRY_MS = 15000;         // 取数失败后的重试间隔，比正常轮询更快
  var GRAPH_POLL_MS = 300000;   // 中央图谱 5 分钟一次，别每 30s 重排 300 个节点
  var FOCUS_MS = 8000;          // 聚焦轮播：每 8s 换一类实体（§2.5 第 2 条）
  var GRAPH_NODES = 300;        // 投屏掉帧护栏：按度数取前 300 个节点（§6）
  var GRAPH_FETCH = 500;        // /api/graph 单次上限
  var ROLL_MS = 800;            // 数字卡滚动时长（§2.5 第 1 条）

  var CHART_IDS = ['chart-graph', 'chart-entity-types', 'chart-trend',
                   'chart-tools', 'chart-chapters', 'chart-top-entities'];
  var OVERVIEW_IDS = ['chart-entity-types', 'chart-trend', 'chart-tools',
                      'chart-chapters', 'chart-top-entities'];
  var STAT_IDS = ['stat-documents', 'stat-entities', 'stat-relations',
                  'stat-chunks', 'stat-sessions', 'stat-runs'];

  var C_TEXT = '#DCE9FF';
  var C_AXIS = '#9FB6D9';
  var C_LINE = 'rgba(64,156,255,.18)';
  var C_CYAN = '#22D3EE';
  var C_BLUE = '#3B82F6';
  var C_BG = '#08111F';       // 半透明面板叠在深底上的近似底色，用于扇形/描边留缝

  var charts = {};
  var graphNodes = [];        // 图谱裁剪后的节点（按度数 Top GRAPH_NODES）
  var frozenPos = null;       // 力导收敛+适配画布后的坐标快照
  var focusQueue = [];        // 聚焦轮播：每个类型取度数最高的实体
  var focusIdx = 0;
  var focusTimer = null;
  var lastGraphAt = 0;
  var lastRuns = { total: 0, steps: 0, interrupted: 0 };
  var everLoaded = false;     // 是否成功拿到过一帧总览：失败时据此决定"保留上一帧"还是报错
  var graphDrawn = false;     // 图谱同理

  // ----- 页面适配与时钟（Task 5.1）-----
  function fit() {
    var root = document.getElementById('screenRoot');
    var scale = Math.min(window.innerWidth / BASE_W, window.innerHeight / BASE_H);
    root.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function tickClock() {
    var now = new Date();
    document.getElementById('scClock').textContent =
      pad2(now.getHours()) + ':' + pad2(now.getMinutes()) + ':' + pad2(now.getSeconds());
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ----- 每张图各自的占位与降级 -----
  // echarts.init 会清空容器，连 HTML 里的骨架占位一起带走；占位浮层因此由脚本补建，
  // 否则某张图没数据时既没有图也没有提示，只剩一块空白
  function phOf(id) {
    var box = document.getElementById(id);
    if (!box) return null;
    var ph = box.querySelector('.sc-ph');
    if (!ph) {
      ph = document.createElement('div');
      ph.className = 'sc-ph';
      box.appendChild(ph);
    }
    return ph;
  }

  function placeholder(id, text) {
    var ph = phOf(id);
    if (!ph) return;
    if (text) ph.textContent = text;
    ph.hidden = false;
  }

  function clearPlaceholder(id) {
    var box = document.getElementById(id);
    var ph = box && box.querySelector('.sc-ph');
    if (ph) ph.hidden = true;
  }

  // 渲染函数返回 false 表示"这条数据源为空"：只该图显示占位，不算故障
  function draw(id, fn, arg) {
    try {
      if (fn(arg) === false) { placeholder(id, '暂无数据'); return false; }
      clearPlaceholder(id);
      return true;
    } catch (e) {
      console.warn('[大屏] ' + id + ' 渲染失败', e);
      placeholder(id, '图表暂不可用');
      return false;
    }
  }

  function sub(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text || '';
  }

  function setStatus(ok, text) {
    var el = document.getElementById('scStatus');
    el.textContent = text;
    el.classList.toggle('is-error', !ok);
  }

  function initChart(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    // 设计稿 1920×1080 靠 transform 缩放投到任意分辨率，canvas 必须按 2 倍栅格渲染
    var c = echarts.init(el, null, { devicePixelRatio: 2 });
    charts[id] = c;
    return c;
  }

  // ----- 动效 ①：数字卡滚动进场 -----
  function rollNumber(id, target, format) {
    var el = document.getElementById(id);
    var text = format || function (v) { return v.toLocaleString('en-US'); };
    var from = el.dataset.value ? Number(el.dataset.value) : 0;
    var t0 = null;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var k = Math.min((ts - t0) / ROLL_MS, 1);
      var eased = 1 - Math.pow(1 - k, 3);
      var v = Math.round(from + (target - from) * eased);
      el.textContent = text(v);
      if (k < 1) { requestAnimationFrame(step); return; }
      el.dataset.value = String(target);
      el.textContent = text(target);
    }
    requestAnimationFrame(step);
  }

  function applyStats(stats, runs) {
    var values = [stats.documents, stats.entities, stats.relations,
                  stats.chunks, stats.sessions, runs.total];
    STAT_IDS.forEach(function (id, i) { rollNumber(id, Number(values[i] || 0)); });
  }

  // 覆盖率放大到万分位再滚动：滚动过程始终是整数，落位才除回两位小数的百分数
  function applyCoverage(coverage) {
    if (!coverage) return;   // 后端没有这个字段（改动后没重启）：停在占位符，0.00% 会被读成"没人问过"
    var c = coverage;
    rollNumber('stat-coverage', Math.round((c.rate || 0) * 10000), function (v) {
      return (v / 100).toFixed(2) + '%';
    });
    sub('coverageSub', c.total
      ? '已触达 ' + Number(c.touched).toLocaleString('en-US')
              + ' / ' + Number(c.total).toLocaleString('en-US') + ' 个知识点'
      : '尚未物化知识点');
    var bar = document.getElementById('coverageBar');
    bar.style.display = c.total ? '' : 'none';
    bar.style.width = ((c.rate || 0) * 100).toFixed(2) + '%';
  }

  function msText(ms) {
    if (ms < 1) return '<1ms';                       // 亚毫秒的本地计算（如子网划分）
    if (ms >= 1000) return (ms / 1000).toFixed(1) + 's';
    return ms + 'ms';
  }

  function axisBase(fontSize) {
    return {
      axisLabel: { color: C_AXIS, fontSize: fontSize || 16 },
      axisLine: { lineStyle: { color: C_LINE } },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: C_LINE } },
    };
  }

  // ----- ② 实体类型玫瑰图 -----
  function renderTypes(rows) {
    if (!rows || !rows.length) return false;
    var total = rows.reduce(function (s, r) { return s + r.count; }, 0);
    var countOf = {};
    rows.forEach(function (r) { countOf[r.type] = r.count; });
    sub('typesSub', '共 ' + rows.length + ' 类 · ' + total.toLocaleString('en-US') + ' 实体');
    charts['chart-entity-types'].setOption({
      tooltip: { show: false },
      // 10 类扇形挤在一起时就地标注必然互相压叠：左玫瑰 + 右竖排图例（带数值）
      legend: {
        type: 'scroll',
        orient: 'vertical',
        right: 6,
        top: 'middle',
        icon: 'circle',
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 9,
        textStyle: { color: C_AXIS, fontSize: 16 },
        formatter: function (name) { return name + '  ' + (countOf[name] || 0); },
      },
      series: [{
        type: 'pie',
        roseType: 'radius',
        radius: ['30%', '68%'],
        center: ['27%', '50%'],
        itemStyle: { borderColor: C_BG, borderWidth: 2 },
        label: { show: false },
        labelLine: { show: false },
        data: rows.map(function (r) {
          return {
            name: r.type, value: r.count,
            itemStyle: { color: TYPE_COLORS[r.type] || TYPE_COLORS.Other },
          };
        }),
        animationDuration: 900,
        animationEasing: 'cubicOut',
      }],
    }, true);
    return true;
  }

  // ----- ③ 近 14 日问答趋势（面积图，逐点瀑布入场）-----
  function renderTrend(rows) {
    if (!rows || !rows.length) return false;
    var total = rows.reduce(function (s, r) { return s + r.count; }, 0);
    sub('trendSub', '14 天共 ' + total.toLocaleString('en-US') + ' 次提问');
    charts['chart-trend'].setOption({
      tooltip: { show: false },
      grid: { left: 48, right: 22, top: 14, bottom: 26 },
      xAxis: Object.assign(axisBase(15), {
        type: 'category', boundaryGap: false,
        data: rows.map(function (r) { return r.date.slice(5); }),
        axisLabel: { color: C_AXIS, fontSize: 16, interval: 1 },
        splitLine: { show: false },
      }),
      yAxis: Object.assign(axisBase(16), { type: 'value', minInterval: 1, axisLine: { show: false } }),
      series: [{
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map(function (r) { return r.count; }),
        lineStyle: { width: 2.5, color: C_CYAN },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(34,211,238,.45)' },
            { offset: 1, color: 'rgba(34,211,238,0)' },
          ]),
        },
        animationDuration: 700,
        animationDelay: function (idx) { return idx * 40; },
      }],
    }, true);
    return true;
  }

  // ----- ④ 工具调用雷达 -----
  function renderTools(payload) {
    var tools = payload.tools || [];
    if (!tools.length) return false;
    var maxCalls = tools.reduce(function (m, t) { return Math.max(m, t.calls); }, 0);
    var fastest = null, wCalls = 0, wMs = 0;
    tools.forEach(function (t) {
      if (t.avg_ms === null || t.avg_ms === undefined) return;
      fastest = fastest === null ? t.avg_ms : Math.min(fastest, t.avg_ms);
      wCalls += t.calls;
      wMs += t.calls * t.avg_ms;
    });
    var summary = ['共 ' + tools.reduce(function (s, t) { return s + t.calls; }, 0) + ' 次调用'];
    if (fastest !== null) summary.push('最快 ' + msText(fastest));
    if (wCalls) summary.push('平均 ' + msText(Math.round(wMs / wCalls)));
    summary.push(payload.runs.steps + ' 步 · ' + payload.runs.interrupted + ' 中断');
    sub('toolsSub', summary.join(' · '));

    charts['chart-tools'].setOption({
      tooltip: { show: false },
      radar: {
        center: ['50%', '53%'],
        radius: '55%',
        indicator: tools.map(function (t) {
          // 轴名太长会顶出面板：截断到 11 字，完整名在调用次数旁仍可辨
          var name = t.name.length > 11 ? t.name.slice(0, 10) + '…' : t.name;
          return { name: name + ' ' + t.calls, max: Math.max(maxCalls * 1.15, 1) };
        }),
        axisName: { color: C_TEXT, fontSize: 16 },
        axisLine: { lineStyle: { color: C_LINE } },
        splitLine: { lineStyle: { color: C_LINE } },
        splitArea: { areaStyle: { color: ['rgba(34,211,238,.03)', 'rgba(34,211,238,.07)'] } },
      },
      series: [{
        type: 'radar',
        data: [{
          value: tools.map(function (t) { return t.calls; }),
          name: '调用次数',
        }],
        symbolSize: 5,
        lineStyle: { width: 2, color: C_CYAN },
        itemStyle: { color: C_CYAN },
        areaStyle: { color: 'rgba(34,211,238,.28)' },
        animationDuration: 900,
      }],
    }, true);
    return true;
  }

  // ----- ⑤ 章节覆盖度 -----
  function renderChapters(rows) {
    if (!rows || !rows.length) return false;
    var chunks = rows.reduce(function (s, r) { return s + r.chunks; }, 0);
    sub('chaptersSub', rows.length + ' 章已入库 · ' + chunks.toLocaleString('en-US') + ' 分块');
    charts['chart-chapters'].setOption({
      tooltip: { show: false },
      grid: { left: 52, right: 24, top: 22, bottom: 26 },
      xAxis: Object.assign(axisBase(16), {
        type: 'category',
        data: rows.map(function (r) { return '第' + r.chapter + '章'; }),
        axisLabel: {
          color: C_AXIS, fontSize: 16, interval: 0,
          formatter: function (v) { return v.replace('第', ''); },   // "1章"：9 个标签才排得下
        },
        splitLine: { show: false },
      }),
      yAxis: Object.assign(axisBase(16), { type: 'value', axisLine: { show: false } }),
      series: [{
        type: 'bar',
        barWidth: '46%',
        data: rows.map(function (r) { return r.chunks; }),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: C_CYAN },
            { offset: 1, color: 'rgba(59,130,246,.35)' },
          ]),
        },
        label: { show: true, position: 'top', color: C_TEXT, fontSize: 16 },
        animationDuration: 700,
        animationDelay: function (idx) { return idx * 70; },
      }],
    }, true);
    return true;
  }

  // ----- ⑥ 高频实体 Top 10（按类型的配色）-----
  function renderTopEntities(rows) {
    if (!rows || !rows.length) return false;
    var max = rows.reduce(function (m, r) { return Math.max(m, r.degree); }, 0) || 1;
    charts['chart-top-entities'].setOption({
      tooltip: { show: false },
      grid: { left: 108, right: 54, top: 6, bottom: 6 },
      xAxis: { type: 'value', show: false, max: Math.ceil(max * 1.18) },
      yAxis: Object.assign(axisBase(16), {
        type: 'category',
        inverse: true,                                    // 度数最高的一条排最上
        data: rows.map(function (r) { return r.name; }),
        axisLine: { show: false },
        axisLabel: { color: C_TEXT, fontSize: 16, width: 100, overflow: 'truncate' },
        splitLine: { show: false },
      }),
      series: [{
        type: 'bar',
        barWidth: 13,
        data: rows.map(function (r) {
          return {
            value: r.degree,
            itemStyle: {
              borderRadius: [0, 7, 7, 0],
              color: TYPE_COLORS[r.type] || TYPE_COLORS.Other,
            },
          };
        }),
        label: { show: true, position: 'right', color: C_TEXT, fontSize: 16 },
        animationDuration: 700,
        animationDelay: function (idx) { return idx * 60; },
      }],
    }, true);
    return true;
  }

  // ----- ⑦ 中央知识图谱：力导收敛 → 冻结坐标 → 适配画布 -----
  function graphOption() {
    var labelSet = frozenPos
      ? LAYOUT.placeLabels(graphNodes, frozenPos, { cap: 18, fontSize: 16 })
      : {};
    return {
      animation: false,   // 300 节点下布局过渡既慢又像"标签糊成一团"，一步落位
      tooltip: { show: false },
      series: [{
        type: 'graph',
        layout: frozenPos ? 'none' : 'force',
        data: graphNodes.map(function (n) {
          var p = frozenPos && (frozenPos[n.id] || frozenPos[n.name]);
          var item = {
            id: n.id,
            name: n.name,
            // 大屏比工作台远：符号整体放大一档，直径 18~46px
            symbolSize: 18 + Math.min(28, (n.degree || 0) * 2.6),
            itemStyle: {
              color: TYPE_COLORS[n.type] || TYPE_COLORS.Other,
              borderColor: 'rgba(255,255,255,.35)',
              borderWidth: 1,
            },
            label: {
              show: !!labelSet[n.id],
              fontSize: 16, color: C_TEXT,
              position: 'right', distance: 6,
              textBorderColor: '#050B1A', textBorderWidth: 3,
            },
          };
          if (p) { item.x = p.x; item.y = p.y; }
          return item;
        }),
        links: graphLinks(),
        lineStyle: { color: 'rgba(120,180,255,.22)', width: 1, curveness: .05 },
        emphasis: { focus: 'adjacency', label: { show: true, fontWeight: 600 } },
        // 力导只负责局部排布，整体尺度交给 fitToCanvas；roam/draggable 关闭：投屏无人交互
        force: { repulsion: 800, edgeLength: [60, 150], gravity: .1, layoutAnimation: false },
        roam: false,
        draggable: false,
        scaleLimit: { min: 1, max: 1 },
      }],
    };
  }

  var keptEdges = [];

  function graphLinks() {
    return keptEdges.map(function (e) { return { source: e.source, target: e.target }; });
  }

  function renderGraph(data) {
    if (!data || !data.nodes || !data.nodes.length) return false;
    var sorted = data.nodes.slice().sort(function (a, b) {
      return (b.degree || 0) - (a.degree || 0);
    });
    graphNodes = sorted.slice(0, GRAPH_NODES);
    var keep = {};
    graphNodes.forEach(function (n) { keep[n.id] = true; });
    keptEdges = (data.edges || []).filter(function (e) {
      return keep[e.source] && keep[e.target];
    });
    frozenPos = null;
    focusQueue = buildFocusQueue(graphNodes);
    focusIdx = 0;
    charts['chart-graph'].setOption(graphOption(), true);
    freezeGraph();
    sub('graphFocus', graphNodes.length + ' 实体 · ' + keptEdges.length + ' 关系');
    startFocusRotate();
    return true;
  }

  function buildFocusQueue(nodes) {
    var byType = {};
    nodes.forEach(function (n) {
      var cur = byType[n.type];
      if (!cur || (n.degree || 0) > (cur.degree || 0)) byType[n.type] = n;
    });
    return Object.keys(byType)
      .sort(function (a, b) { return (byType[b].degree || 0) - (byType[a].degree || 0); })
      .map(function (t) { return { type: t, name: byType[t].name }; });
  }

  // 收敛后立刻冻结：力导在 layoutAnimation:false 下同步算完，render 后即可 harvest；
  // 坐标不冻结则容器任何一次重排都会让整张图重新洗牌
  function freezeGraph() {
    if (frozenPos) return;
    var chart = charts['chart-graph'];
    var pos = LAYOUT.harvest(chart);
    if (!pos || Object.keys(pos).length < graphNodes.length) return;
    var fitted = LAYOUT.fitToCanvas(pos, {
      width: chart.getWidth(),
      height: chart.getHeight(),
      maxR: 24,           // 大屏符号更大，包围盒内边距要跟着放大
      padRight: 150,      // 节点右侧是标签带
      padBottom: 20,
    });
    if (!fitted) return;
    frozenPos = fitted;
    chart.setOption(graphOption(), true);
    rotateFocus(true);
  }

  // ----- 动效 ②：每 8s 换一类实体聚焦（选中+邻接高亮，其余淡出）-----
  function rotateFocus(keepIndex) {
    var chart = charts['chart-graph'];
    if (!chart || !focusQueue.length) return;
    if (!keepIndex) focusIdx = (focusIdx + 1) % focusQueue.length;
    var item = focusQueue[focusIdx];
    chart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
    chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: item.name });
    sub('graphFocus', '聚焦 · ' + item.type + ' / ' + item.name);
  }

  function startFocusRotate() {
    if (focusTimer) clearInterval(focusTimer);
    focusTimer = setInterval(rotateFocus, FOCUS_MS);
  }

  // ----- 动效 ④：底部跑马灯 -----
  function renderFeed(items) {
    // 无缝循环：往 `.sc-marquee-content` 灌两份等宽内容，CSS 位移 -50% 正好接回首份
    var el = document.getElementById('scFeed');
    var texts = (items || []).map(function (it) {
      var m = String(it.created_at || '').match(/\d{2}:\d{2}/);
      var text = String(it.text || '').replace(/\s+/g, ' ').trim();
      if (text.length > 34) text = text.slice(0, 34) + '…';
      return (m ? m[0] + ' · ' : '') + text;
    });
    if (!texts.length) texts = ['暂无问答记录，上传课程材料后从这里开始提问 …'];
    var group = '<div class="sc-feed-group">' + texts.map(function (t) {
      return '<span class="sc-feed-item">' + esc(t) + '</span>';
    }).join('') + '</div>';
    el.innerHTML = group + group;
    el.style.animationDuration = Math.max(30, texts.length * 3) + 's';
  }

  // ----- 取数：总览与图谱各自独立失败 -----
  function getJSON(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → HTTP ' + r.status);
      return r.json();
    });
  }

  function loadOverview() {
    return getJSON('/api/screen/overview').then(function (data) {
      everLoaded = true;
      lastRuns = data.runs || lastRuns;
      applyStats(data.stats || {}, lastRuns);
      applyCoverage(data.coverage);
      draw('chart-entity-types', renderTypes, data.entity_types);
      draw('chart-trend', renderTrend, data.trend);
      draw('chart-tools', renderTools, { tools: data.tools, runs: lastRuns });
      draw('chart-chapters', renderChapters, data.chapters);
      draw('chart-top-entities', renderTopEntities, data.top_entities);
      renderFeed(data.feed);
      return data;
    });
  }

  function loadGraph() {
    return getJSON('/api/graph?limit=' + GRAPH_FETCH).then(function (data) {
      if (draw('chart-graph', renderGraph, data)) graphDrawn = true;
    });
  }

  function tick() {
    var ok = true;
    loadOverview().catch(function (e) {
      ok = false;
      console.warn('[大屏] 总览取数失败，保留上一帧', e);
      // 上一帧照留；首帧就没拿到才把占位文案从"接入中"改成明确的失败提示
      if (!everLoaded) OVERVIEW_IDS.forEach(function (id) { placeholder(id, '数据暂不可用'); });
    }).then(function () {
      if (Date.now() - lastGraphAt < GRAPH_POLL_MS) return null;
      return loadGraph().then(function () { lastGraphAt = Date.now(); },
        function (e) {
          console.warn('[大屏] 图谱取数失败，保留上一帧', e);
          if (!graphDrawn) placeholder('chart-graph', '图谱暂不可用');
        });
    }).then(function () {
      var now = new Date();
      if (ok) {
        setStatus(true, '数据更新于 ' + pad2(now.getHours()) + ':' + pad2(now.getMinutes())
          + ':' + pad2(now.getSeconds()) + ' · 每 30 秒自动刷新');
      } else {
        setStatus(false, '数据获取失败，' + RETRY_MS / 1000 + ' 秒后重试（当前显示上次数据）');
      }
      pollTimer = setTimeout(tick, ok ? POLL_MS : RETRY_MS);
    });
  }

  function boot() {
    fit();
    tickClock();
    window.addEventListener('resize', fit);
    window.addEventListener('orientationchange', fit);
    setInterval(tickClock, 1000);

    if (!window.echarts) {
      setStatus(false, '图表库加载失败：请检查网络后刷新页面');
      return;
    }
    CHART_IDS.forEach(initChart);
    OVERVIEW_IDS.forEach(function (id) { placeholder(id, '数据接入中'); });
    placeholder('chart-graph', '知识图谱接入中');
    tick();
  }

  boot();
})();
