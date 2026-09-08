window.Views = window.Views || {};

window.Views.graph = {
  template: `
    <section>
      <h2 class="view-title">知识图谱</h2>
      <div class="card">
        <div class="empty">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="5"/><circle cx="36" cy="10" r="5"/>
            <circle cx="24" cy="30" r="5"/><circle cx="40" cy="34" r="5"/>
            <path d="M16.5 14.5 L20 26 M28 26 L33 13 M28.5 32 L35.5 33.5"/>
          </svg>
          <p>暂无知识图谱数据</p>
          <p>请先到"知识库管理"上传课程材料，建库完成后此处展示实体关系网络</p>
        </div>
      </div>
    </section>
  `,
};
