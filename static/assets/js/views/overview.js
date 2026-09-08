window.Views = window.Views || {};

window.Views.overview = {
  setup: function () {
    var stats = Store.stats;
    var cards = [
      { key: 'documents', label: '课程文档' },
      { key: 'entities', label: '知识实体' },
      { key: 'relations', label: '关系' },
      { key: 'chunks', label: '文本分块' },
      { key: 'sessions', label: '问答会话' },
    ];
    return { stats: stats, cards: cards };
  },
  template: `
    <section>
      <h2 class="view-title">概览</h2>
      <div class="stat-grid">
        <div class="card stat-card" v-for="c in cards" :key="c.key">
          <div class="stat-value">{{ stats[c.key] ?? '—' }}</div>
          <div class="stat-label">{{ c.label }}</div>
        </div>
      </div>
      <div class="card">
        <div class="side-title">快速开始</div>
        <div class="steps-grid">
          <div class="step-item">
            <span class="step-no">1</span>
            <div><h4>上传课程材料</h4><p>在"知识库管理"上传 md / txt / docx 讲义，系统自动解析建库</p></div>
          </div>
          <div class="step-item">
            <span class="step-no">2</span>
            <div><h4>浏览知识图谱</h4><p>查看从课件中自动抽取的实体关系网络，可搜索与筛选</p></div>
          </div>
          <div class="step-item">
            <span class="step-no">3</span>
            <div><h4>开始问答</h4><p>在"RAG 问答"提问课程概念，或在"ReAct 智能体"提出计算复合题</p></div>
          </div>
        </div>
      </div>
    </section>
  `,
};
