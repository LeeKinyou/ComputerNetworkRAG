window.Components = window.Components || {};

// ReAct 时间线（06 §4.4.1）：按 step_no 分组，组内 思考→行动→观察 串联；
// 实时流与历史回放（/api/sessions/{sid}/runs/{rid} 的 steps）喂同一种
// groups 结构，渲染视觉一致。
window.Components.timeline = {
  props: {
    groups: { type: Array, default: function () { return []; } },
    answer: { type: String, default: '' },
    streaming: { type: Boolean, default: false },
    truncated: { type: Boolean, default: false },
  },
  setup: function () {
    var TOOL_CN = {
      subnet_calculator: '子网计算器',
      lpm_lookup: '路由查表',
      dns_lookup: '域名解析',
      course_rag_query: '课程知识检索',
    };

    function toolCn(tool) { return TOOL_CN[tool] || tool; }

    // 思考文本为空时合成一行，不伪造模型没说过的推理（03 §3.2 / 06 §4.4.1）
    function synthThought(g) {
      var names = (g.actions || []).map(function (a) { return toolCn(a.tool); });
      return names.length ? '决定调用 ' + names.join('、') : '';
    }

    function fmtArgs(args) {
      try { return JSON.stringify(args || {}, null, 2); }
      catch (e) { return String(args); }
    }

    function subnetRows(structured) {
      var s = structured || {};
      var rows = [
        ['网络地址', (s.network || '—') + '/' + (s.prefix != null ? s.prefix : '—')],
        ['子网掩码', s.netmask || '—'],
        ['广播地址', s.broadcast || '—'],
        ['可用主机范围', (s.first_host || '—') + ' ~ ' + (s.last_host || '—')],
        ['可用主机数', s.host_count != null ? s.host_count + ' 台' : '—'],
        ['地址类型', s.is_private ? '私网地址' : '公网地址'],
      ];
      if (s.note) rows.push(['说明', s.note]);
      return rows;
    }

    // lpm_lookup：逐行匹配 trace 表 + 命中路由
    function lpmRows(structured) {
      var s = structured || {};
      return (s.trace || []).map(function (t) {
        return { prefix: t.prefix, matched: t.matched, note: t.note || '' };
      });
    }

    return {
      toolCn: toolCn,
      synthThought: synthThought,
      fmtArgs: fmtArgs,
      subnetRows: subnetRows,
      lpmRows: lpmRows,
    };
  },
  template: `
    <div class="timeline">
      <div v-for="g in groups" :key="g.step_no" class="tl-group">
        <div class="tl-badge">{{ g.step_no }}</div>
        <div class="tl-body">
          <div class="tl-card thought">
            <div class="tl-card-head"><span class="tl-kind">思考</span></div>
            <div class="tl-card-text">{{ g.thought || synthThought(g) }}</div>
          </div>
          <template v-for="(a, ai) in g.actions" :key="ai">
            <div class="tl-card action">
              <div class="tl-card-head">
                <span class="tl-kind">行动</span>
                <span class="tl-tool-cn">{{ toolCn(a.tool) }}</span>
                <code class="tl-tool-name">{{ a.tool }}</code>
              </div>
              <pre class="tl-args">{{ fmtArgs(a.args) }}</pre>
            </div>
            <div v-if="a.obs" class="tl-card observation" :class="{ failed: a.obs.status === 'failed' }">
              <div class="tl-card-head">
                <span class="tl-kind">观察</span>
                <span class="tl-obs-status" :class="a.obs.status">
                  {{ a.obs.status === 'failed' ? '失败' : '成功' }}
                </span>
                <span class="tl-elapsed">{{ a.obs.elapsed_ms }} ms</span>
              </div>
              <div class="tl-card-text">{{ a.obs.result }}</div>
              <details v-if="a.tool === 'subnet_calculator'" class="tl-structured" :open="true">
                <summary>结构化结果</summary>
                <table class="tl-table">
                  <tr v-for="row in subnetRows(a.obs.structured)" :key="row[0]">
                    <td class="tl-k">{{ row[0] }}</td><td class="tl-v">{{ row[1] }}</td>
                  </tr>
                </table>
              </details>
              <details v-else-if="a.tool === 'lpm_lookup'" class="tl-structured" :open="true">
                <summary>结构化结果</summary>
                <table class="tl-table">
                  <tr><th class="tl-k">目的前缀</th><th>是否命中</th><th>说明</th></tr>
                  <tr v-for="(t, ti) in lpmRows(a.obs.structured)" :key="ti" :class="{ hit: t.matched, miss: !t.matched }">
                    <td class="tl-k">{{ t.prefix }}</td>
                    <td>{{ t.matched ? '命中' : '未命中' }}</td>
                    <td>{{ t.note }}</td>
                  </tr>
                </table>
                <div v-if="a.obs.structured && a.obs.structured.selected" class="tl-selected">
                  转发决策：下一跳 <b>{{ a.obs.structured.selected.next_hop }}</b>
                  ，出接口 <b>{{ a.obs.structured.selected.interface }}</b>
                </div>
              </details>
              <details v-else-if="a.obs.structured && Object.keys(a.obs.structured).length" class="tl-structured">
                <summary>结构化结果</summary>
                <pre class="tl-args">{{ fmtArgs(a.obs.structured) }}</pre>
              </details>
            </div>
          </template>
        </div>
      </div>

      <div v-if="truncated" class="warn-bar">
        已达最大推理轮数上限，回答可能不完整
      </div>

      <div v-if="answer || streaming" class="tl-answer" :class="{ streaming: streaming }">
        <div class="tl-answer-head">最终回答</div>
        <div class="tl-answer-text">
          {{ answer }}<span v-if="streaming" class="caret"></span>
        </div>
        <div v-if="streaming && !answer" class="loading-hint">正在组织答案…</div>
      </div>
    </div>
  `,
};
