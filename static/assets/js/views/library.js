window.Views = window.Views || {};

window.Views.library = {
  template: `
    <section>
      <h2 class="view-title">知识库管理</h2>
      <div class="card">
        <div class="dropzone">
          <p>将课程材料拖拽到此处，或点击选择文件</p>
          <p class="hint">支持 .md / .txt / .docx，单文件不超过 20MB；上传后自动解析并建立知识库</p>
        </div>
      </div>
      <div class="card">
        <div class="side-title">文档列表</div>
        <div class="empty" style="padding: 24px 8px;">
          <p>还没有上传任何文档</p>
        </div>
      </div>
    </section>
  `,
};
