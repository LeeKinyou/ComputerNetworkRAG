window.API = (function () {
  async function getJSON(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  }

  async function postJSON(path, body) {
    const resp = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  }

  // POST + fetch 流式解析 SSE 帧（EventSource 仅支持 GET，故自行按空行分帧，容忍半包）
  function postSSE(url, body, handlers) {
    const ctrl = new AbortController();
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
      signal: ctrl.signal,
    }).then(async function (resp) {
      if (!resp.ok) {
        if (handlers.error) handlers.error({ message: 'HTTP ' + resp.status });
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) break;
        // sse-starlette 用 \r\n 行尾，统一归一成 \n 后按空行分帧
        buf += decoder.decode(chunk.value, { stream: true }).replace(/\r/g, '');
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          handleFrame(frame, handlers);
        }
      }
    }).catch(function (err) {
      if (err.name !== 'AbortError' && handlers.error) handlers.error({ message: '连接中断，请重试' });
    });
    return ctrl;
  }

  function handleFrame(frame, handlers) {
    let event = 'message';
    const dataLines = [];
    frame.split('\n').forEach(function (line) {
      if (line.indexOf('event:') === 0) event = line.slice(6).trim();
      else if (line.indexOf('data:') === 0) dataLines.push(line.slice(5).trimStart());
    });
    if (!dataLines.length) return;
    let payload;
    try { payload = JSON.parse(dataLines.join('\n')); }
    catch (e) { payload = dataLines.join('\n'); }
    if (handlers[event]) handlers[event](payload);
  }

  return { getJSON: getJSON, postJSON: postJSON, postSSE: postSSE };
})();
