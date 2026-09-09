window.Components = window.Components || {};

window.Components.sourceCard = {
  props: {
    items: { type: Array, default: function () { return []; } },
    question: { type: String, default: '' },
  },
  data: function () {
    return { open: false };
  },
  computed: {
    tokens: function () {
      // 从提问中提取高亮词：英文/数字词 + 中文连续段（截到 6 字），去重
      var q = this.question || '';
      var found = [];
      var re = /[A-Za-z0-9][A-Za-z0-9./-]{1,}|[\u4e00-\u9fff]{2,}/g;
      var m;
      while ((m = re.exec(q)) !== null) {
        var t = m[0].slice(0, 6);
        if (found.indexOf(t) === -1) found.push(t);
      }
      return found;
    },
  },
  methods: {
    highlight: function (snippet) {
      var esc = function (s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
          .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      };
      var text = String(snippet || '');
      if (!this.tokens.length) return esc(text);
      var pattern = this.tokens.map(function (t) {
        return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      }).join('|');
      var re = new RegExp('(' + pattern + ')', 'gi');
      var out = '';
      var last = 0;
      var m;
      while ((m = re.exec(text)) !== null) {
        out += esc(text.slice(last, m.index)) + '<mark>' + esc(m[0]) + '</mark>';
        last = m.index + m[0].length;
        if (m[0].length === 0) re.lastIndex++;
      }
      out += esc(text.slice(last));
      return out;
    },
  },
  template: `
    <div class="source-card" v-if="items.length">
      <button class="source-toggle" @click="open = !open">
        <span class="toggle-arrow">{{ open ? '▾' : '▸' }}</span>
        参考来源（{{ items.length }}）
      </button>
      <div v-show="open" class="source-list">
        <div class="source-item" v-for="(s, i) in items" :key="i">
          <div class="source-doc">{{ s.doc_name }}<span class="source-chunk" v-if="s.chunk_id"> · {{ s.chunk_id }}</span></div>
          <div class="source-snippet" v-html="highlight(s.snippet)"></div>
        </div>
      </div>
    </div>
  `,
};
