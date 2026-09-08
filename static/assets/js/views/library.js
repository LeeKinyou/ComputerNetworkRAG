window.Views = window.Views || {};

window.Views.library = {
  setup: function () {
    var ref = Vue.ref;
    var onMounted = Vue.onMounted;

    var ACCEPT = ['.md', '.txt', '.docx'];
    var MAX_MB = 20;
    var STATUS_META = {
      pending: { label: '排队中', cls: 'st-pending' },
      parsed: { label: '已解析', cls: 'st-parsed' },
      indexed: { label: '已建库', cls: 'st-indexed' },
      failed: { label: '失败', cls: 'st-failed' },
      unsupported: { label: '不支持', cls: 'st-unsupported' },
    };

    var docs = ref([]);
    var uploadError = ref('');
    var uploading = ref(false);
    var dragging = ref(false);
    var fileInput = ref(null);
    var expanded = ref({});
    var timer = null;

    function extOf(name) {
      var m = (name || '').match(/\.[^.]+$/);
      return m ? m[0].toLowerCase() : '';
    }
    function fmtSize(bytes) {
      if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
      if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB';
      return bytes + ' B';
    }
    function statusMeta(s) { return STATUS_META[s] || { label: s, cls: '' }; }

    function busyCount() {
      return docs.value.filter(function (d) {
        return d.status === 'pending' || d.status === 'parsed';
      }).length;
    }
    function stopPolling() {
      if (timer) { clearInterval(timer); timer = null; }
    }
    function startPolling() {
      if (timer) return;
      timer = setInterval(function () {
        if (document.visibilityState !== 'visible') return;
        load();
      }, 3000);
    }
    function load() {
      API.getJSON('/api/documents').then(function (data) {
        docs.value = data.items || [];
        if (busyCount() > 0) startPolling(); else stopPolling();
      }).catch(function () { /* 顶部状态点已提示 */ });
    }

    function uploadFiles(fileList) {
      var files = Array.prototype.slice.call(fileList || []);
      var rejected = files.filter(function (f) { return ACCEPT.indexOf(extOf(f.name)) === -1; });
      var accepted = files.filter(function (f) { return ACCEPT.indexOf(extOf(f.name)) !== -1; });
      uploadError.value = rejected.length
        ? '已跳过不支持的格式：' + rejected.map(function (f) { return f.name; }).join('、')
        : '';
      if (!accepted.length) return;
      uploading.value = true;
      Promise.all(accepted.map(function (f) {
        var form = new FormData();
        form.append('file', f);
        return fetch('/api/documents/upload', { method: 'POST', body: form })
          .then(function (resp) {
            if (resp.status === 413) return f.name + ' 超过 ' + MAX_MB + 'MB';
            if (resp.status === 415) return f.name + ' 格式不支持';
            if (!resp.ok) return f.name + ' 上传失败（HTTP ' + resp.status + '）';
            return null;
          })
          .catch(function () { return f.name + ' 上传失败，请检查服务'; });
      })).then(function (errs) {
        uploading.value = false;
        var fails = errs.filter(Boolean);
        if (fails.length) uploadError.value = fails.join('；');
        load();
        Store.refreshStats();
      });
    }

    function pick() { if (fileInput.value) fileInput.value.click(); }
    function onDrop(e) {
      dragging.value = false;
      uploadFiles(e.dataTransfer.files);
    }
    function onInputChange(e) {
      uploadFiles(e.target.files);
      e.target.value = '';
    }

    function reindex(doc) {
      API.postJSON('/api/documents/' + doc.doc_id + '/reindex').then(function () {
        doc.status = 'pending';
        doc.error = null;
        startPolling();
      }).catch(function () { uploadError.value = '重建请求失败，请重试'; });
    }
    function remove(doc) {
      if (!confirm('删除后将从知识库移除「' + doc.filename + '」及其抽取的实体关系，确认删除？')) return;
      fetch('/api/documents/' + doc.doc_id, { method: 'DELETE' }).then(function () {
        load();
        Store.refreshStats();
      }).catch(function () { uploadError.value = '删除请求失败，请重试'; });
    }
    function toggle(doc) { expanded.value[doc.doc_id] = !expanded.value[doc.doc_id]; }

    onMounted(load);

    return {
      docs: docs, uploadError: uploadError, uploading: uploading, dragging: dragging,
      fileInput: fileInput, expanded: expanded,
      accept: ACCEPT.join(','), fmtSize: fmtSize, statusMeta: statusMeta,
      pick: pick, onDrop: onDrop, onInputChange: onInputChange,
      reindex: reindex, remove: remove, toggle: toggle,
    };
  },
  template: `
    <section>
      <h2 class="view-title">知识库管理</h2>
      <div class="card">
        <div class="dropzone" :class="{ dragging: dragging }"
             @click="pick" @dragover.prevent="dragging = true"
             @dragleave="dragging = false" @drop.prevent="onDrop">
          <p>将课程材料拖拽到此处，或点击选择文件</p>
          <p class="hint">支持 .md / .txt / .docx，单文件不超过 20MB；上传后自动解析并建立知识库</p>
          <input ref="fileInput" type="file" multiple :accept="accept"
                 style="display: none" @change="onInputChange">
        </div>
        <div class="error-bar" v-if="uploadError">{{ uploadError }}</div>
        <div class="hint" style="margin-top: 8px;" v-if="uploading">正在上传，请稍候…</div>
      </div>
      <div class="card">
        <div class="side-title">文档列表</div>
        <div class="empty" v-if="!docs.length" style="padding: 24px 8px;">
          <p>还没有上传任何文档，先上传一份讲义试试</p>
        </div>
        <table class="doc-table" v-else>
          <thead>
            <tr><th>文件名</th><th>大小</th><th>解析器</th><th>状态</th><th>分块</th><th style="width: 140px;">操作</th></tr>
          </thead>
          <tbody>
            <template v-for="d in docs" :key="d.doc_id">
              <tr>
                <td class="doc-name" :title="d.filename">{{ d.filename }}</td>
                <td>{{ fmtSize(d.size_bytes) }}</td>
                <td>{{ d.parser }}</td>
                <td><span class="status-badge" :class="statusMeta(d.status).cls">{{ statusMeta(d.status).label }}</span></td>
                <td>{{ d.chunk_count || '—' }}</td>
                <td class="doc-actions">
                  <button class="btn btn-sm" @click="reindex(d)"
                          :disabled="d.status === 'pending' || d.status === 'parsed'">重建</button>
                  <button class="btn btn-sm btn-danger" @click="remove(d)">删除</button>
                </td>
              </tr>
              <tr v-if="d.status === 'failed' && d.error" @click="toggle(d)" class="error-row">
                <td colspan="6">
                  <span class="error-toggle">{{ expanded[d.doc_id] ? '▾ 收起' : '▸ 展开失败原因' }}</span>
                  <span v-if="expanded[d.doc_id]">{{ d.error }}</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
  `,
};
