/* 学习路径画布布局的数值回归驱动（不是页面运行时的一部分，只被 tests/test_path_layout.py 用 node 拉起）。
   静态契约测试证明不了"方块没有叠在一起、也没有被推出画布"，所以这里用假的 Vue/echarts
   跑组件真实的排版代码，量出矩形相交数与越界数。
   用法：node path_layout_driver.js <cases.json> <graph-layout.js> <path-graph.js> */
const fs = require('fs');
const vm = require('vm');

const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

const sandbox = { JSON: JSON, Math: Math, Object: Object, Array: Array, String: String, Number: Number, Boolean: Boolean, Date: Date };
sandbox.window = sandbox;
sandbox.window.Components = {};
sandbox.window.addEventListener = function () {};
sandbox.window.removeEventListener = function () {};
vm.createContext(sandbox);

function load(p) { vm.runInContext(fs.readFileSync(p, 'utf8'), sandbox, { filename: p }); }

var lastCalls = [];
var mountFn = null;
sandbox.window.UI = { isPhone: function () { return sandbox.__phone; } };
sandbox.Vue = {
  ref: function (v) { return { value: v }; },
  watch: function () {},
  onMounted: function (fn) { mountFn = fn; },
  onBeforeUnmount: function () {},
};
sandbox.echarts = {
  init: function () {
    return {
      getWidth: function () { return sandbox.__w; },
      getHeight: function () { return sandbox.__h; },
      setOption: function (opt) { lastCalls.push(opt); },
      on: function () {},
      resize: function () {},
      dispose: function () {},
    };
  },
};

load(process.argv[3]);
load(process.argv[4]);
var comp = sandbox.window.Components.pathGraph;

function intersects(a, b) {
  return Math.abs(a.x - b.x) * 2 < (a.w + b.w) && Math.abs(a.y - b.y) * 2 < (a.h + b.h);
}

function runCase(c) {
  sandbox.__w = c.width;
  sandbox.__h = c.height;
  sandbox.__phone = !!c.phone;
  lastCalls = [];
  mountFn = null;
  var emitted = [];
  var props = {
    nodes: c.nodes, edges: c.edges || [], planIds: c.planIds || [],
    selectedId: '', mode: c.mode || 'layer',
  };
  comp.setup(props, { emit: function (name, info) { emitted.push({ name: name, info: info }); } });
  mountFn();
  var opt = lastCalls[lastCalls.length - 1];
  var data = opt.series[0].data;
  var boxes = data.map(function (n) {
    return { id: n.id, x: n.x, y: n.y, w: n.symbolSize[0], h: n.symbolSize[1] };
  });

  var overlaps = [];
  for (var i = 0; i < boxes.length; i++) {
    for (var j = i + 1; j < boxes.length; j++) {
      if (intersects(boxes[i], boxes[j])) overlaps.push([boxes[i].id, boxes[j].id]);
    }
  }
  var off = boxes.filter(function (b) {
    return b.x - b.w / 2 < 0 || b.x + b.w / 2 > c.width
        || b.y - b.h / 2 < 0 || b.y + b.h / 2 > c.height;
  });
  var cap = null;
  emitted.forEach(function (e) { if (e.name === 'cap') cap = e.info; });
  return {
    label: c.label, total: c.nodes.length, drawn: data.length,
    overlaps: overlaps.length, off: off.length,
    offIds: off.slice(0, 3).map(function (b) { return b.id; }),
    sampleOverlap: overlaps.length ? overlaps[0] : null,
    cap: cap, linkCount: opt.series[0].links.length,
  };
}

process.stdout.write(JSON.stringify(cases.map(runCase), null, 2));
