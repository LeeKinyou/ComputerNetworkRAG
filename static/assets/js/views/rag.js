window.Views = window.Views || {};

window.Views.rag = {
  setup: function () {
    var question = Vue.ref('');
    function send() {
      // M2 接入 /api/rag/chat SSE
    }
    return { question: question, send: send };
  },
  template: `
    <section>
      <h2 class="view-title">RAG 问答</h2>
      <div class="split">
        <div class="card">
          <div class="side-title">历史会话</div>
          <div class="empty" style="padding: 24px 8px;">暂无会话</div>
        </div>
        <div class="card">
          <div class="empty">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="8" y="10" width="32" height="24" rx="4"/>
              <path d="M18 40 L24 34 L30 40 M17 19 H31 M17 25 H26"/>
            </svg>
            <p>基于课程材料的检索增强问答</p>
            <p>上传课程材料后，即可提问课程概念题，回答附带来源引用</p>
          </div>
          <div class="chat-input-row">
            <textarea v-model="question" placeholder="输入问题，Enter 发送（问答接口尚未接入）"
                      @keydown.enter.exact.prevent="send"></textarea>
            <button class="btn primary" disabled>发送</button>
          </div>
        </div>
      </div>
    </section>
  `,
};
