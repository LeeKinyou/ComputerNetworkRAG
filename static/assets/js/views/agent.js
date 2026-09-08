window.Views = window.Views || {};

window.Views.agent = {
  setup: function () {
    var question = Vue.ref('');
    function send() {
      // M3 接入 /api/agent/chat SSE
    }
    return { question: question, send: send };
  },
  template: `
    <section>
      <h2 class="view-title">ReAct 智能体</h2>
      <div class="split">
        <div class="card">
          <div class="side-title">历史运行</div>
          <div class="empty" style="padding: 24px 8px;">暂无运行记录</div>
        </div>
        <div class="card">
          <div class="empty">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="24" cy="24" r="14"/>
              <path d="M24 16 V24 L30 28"/>
              <path d="M8 10 L12 6 M40 10 L36 6 M24 4 V8" stroke-linecap="round"/>
            </svg>
            <p>智能体将逐步展示 思考 → 行动 → 观察 的完整推理过程</p>
            <p>支持子网计算、路由查表、DNS 解析与课程知识检索</p>
          </div>
          <div class="chat-input-row">
            <textarea v-model="question" placeholder="输入问题，Enter 发送（智能体接口尚未接入）"
                      @keydown.enter.exact.prevent="send"></textarea>
            <button class="btn primary" disabled>发送</button>
          </div>
        </div>
      </div>
    </section>
  `,
};
