from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import re
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

from .outline import BuildOptions, build_outline_for_pdf


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zotero PDF Outline Builder</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f5;
      --panel: #ffffff;
      --text: #1f2328;
      --muted: #667085;
      --line: #d8dbe2;
      --accent: #246bfe;
      --accent-soft: #e8efff;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 28px auto;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }
    h1 {
      font-size: 26px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }
    p { margin: 0; color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    #drop {
      display: grid;
      place-items: center;
      min-height: 220px;
      border: 2px dashed #aab3c5;
      border-radius: 8px;
      background: #fbfcff;
      text-align: center;
      cursor: pointer;
      transition: border-color .15s, background .15s;
    }
    #drop.drag {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    #drop strong {
      display: block;
      font-size: 17px;
      margin-bottom: 8px;
    }
    input[type="file"] { display: none; }
    label, .control-title {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin: 16px 0 6px;
    }
    input[type="range"] { width: 100%; }
    .check {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 14px;
      color: var(--text);
      font-size: 14px;
    }
    button, a.button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 0 13px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 600;
      cursor: pointer;
      margin-right: 8px;
      margin-top: 12px;
    }
    button.secondary, a.secondary {
      background: white;
      color: var(--accent);
    }
    button:disabled {
      opacity: .55;
      cursor: not-allowed;
    }
    .status {
      min-height: 38px;
      margin-top: 14px;
      color: var(--muted);
      font-size: 14px;
      white-space: pre-wrap;
    }
    .error { color: var(--danger); }
    .summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .stat {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fcfcfd;
    }
    .stat span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .stat strong {
      display: block;
      font-size: 24px;
      margin-top: 3px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .title-cell { max-width: 440px; }
    .level {
      display: inline-block;
      min-width: 28px;
      border-radius: 5px;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 2px 6px;
      font-weight: 700;
    }
    .empty {
      min-height: 360px;
      display: grid;
      place-items: center;
      color: var(--muted);
      text-align: center;
    }
    @media (max-width: 860px) {
      .grid { grid-template-columns: 1fr; }
      header { display: block; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Zotero PDF Outline Builder</h1>
        <p>拖入论文 PDF，生成带大纲的 PDF 和标注检测位置的 debug PDF。</p>
      </div>
      <p>本地运行，不上传到外网。</p>
    </header>

    <div class="grid">
      <section class="panel">
        <div id="drop">
          <div>
            <strong>拖 PDF 到这里</strong>
            <p>或者点击选择文件</p>
          </div>
        </div>
        <input id="file" type="file" accept="application/pdf,.pdf">

        <label for="confidence">最小置信度：<span id="confidenceValue">0.35</span></label>
        <input id="confidence" type="range" min="0.20" max="0.70" step="0.05" value="0.35">

        <label class="check">
          <input id="force" type="checkbox">
          即使 PDF 已有大纲，也重新生成
        </label>

        <button id="run" disabled>生成</button>
        <div id="status" class="status">请选择一个 PDF。</div>
      </section>

      <section class="panel">
        <div id="result" class="empty">结果会显示在这里。debug PDF 会用彩色框标出识别到的标题。</div>
      </section>
    </div>
  </main>

  <script>
    const drop = document.querySelector('#drop');
    const fileInput = document.querySelector('#file');
    const runButton = document.querySelector('#run');
    const statusBox = document.querySelector('#status');
    const resultBox = document.querySelector('#result');
    const confidence = document.querySelector('#confidence');
    const confidenceValue = document.querySelector('#confidenceValue');
    const force = document.querySelector('#force');
    let selectedFile = null;

    confidence.addEventListener('input', () => {
      confidenceValue.textContent = Number(confidence.value).toFixed(2);
    });

    drop.addEventListener('click', () => fileInput.click());
    drop.addEventListener('dragover', event => {
      event.preventDefault();
      drop.classList.add('drag');
    });
    drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
    drop.addEventListener('drop', event => {
      event.preventDefault();
      drop.classList.remove('drag');
      setFile(event.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => setFile(fileInput.files[0]));

    function setFile(file) {
      selectedFile = file && file.name.toLowerCase().endsWith('.pdf') ? file : null;
      runButton.disabled = !selectedFile;
      statusBox.className = 'status';
      statusBox.textContent = selectedFile ? `已选择：${selectedFile.name}` : '请选择 PDF 文件。';
    }

    runButton.addEventListener('click', async () => {
      if (!selectedFile) return;
      runButton.disabled = true;
      statusBox.className = 'status';
      statusBox.textContent = '正在分析 PDF...';
      resultBox.className = 'empty';
      resultBox.textContent = '处理中。';

      const form = new FormData();
      form.append('pdf', selectedFile);
      form.append('minConfidence', confidence.value);
      form.append('force', force.checked ? 'true' : 'false');

      try {
        const response = await fetch('/api/process', { method: 'POST', body: form });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '处理失败');
        renderResult(data);
        statusBox.textContent = '完成。';
      } catch (error) {
        statusBox.className = 'status error';
        statusBox.textContent = error.message;
        resultBox.className = 'empty';
        resultBox.textContent = '没有生成结果。';
      } finally {
        runButton.disabled = false;
      }
    });

    function renderResult(data) {
      const rows = data.entries.map(entry => `
        <tr>
          <td><span class="level">L${entry.level}</span></td>
          <td>${entry.page}</td>
          <td class="title-cell">${escapeHtml(entry.title)}</td>
          <td>${entry.confidence.toFixed(2)}</td>
          <td>${entry.font_size ?? ''}</td>
          <td>${entry.source}</td>
        </tr>
      `).join('');

      resultBox.className = '';
      resultBox.innerHTML = `
        <div class="summary">
          <div class="stat"><span>识别条目</span><strong>${data.entries.length}</strong></div>
          <div class="stat"><span>一级标题</span><strong>${data.entries.filter(e => e.level === 1).length}</strong></div>
          <div class="stat"><span>二级标题+</span><strong>${data.entries.filter(e => e.level > 1).length}</strong></div>
        </div>
        <a class="button" href="${data.outlined_url}" target="_blank">下载带大纲 PDF</a>
        <a class="button secondary" href="${data.debug_url}" target="_blank">下载标注 debug PDF</a>
        <table>
          <thead>
            <tr><th>层级</th><th>页</th><th>标题</th><th>置信度</th><th>字号</th><th>来源</th></tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="6">没有识别到标题</td></tr>'}</tbody>
        </table>
      `;
    }

    function escapeHtml(value) {
      return value.replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
      }[ch]));
    }
  </script>
</body>
</html>
"""


class DebugHandler(BaseHTTPRequestHandler):
    server_version = "ZoteroPdfOutlineDebug/0.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if self.path.startswith("/runs/"):
            self._serve_run_file()
            return

        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/process":
            self.send_error(404)
            return

        try:
            result = self._process_upload()
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _process_upload(self) -> dict:
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )

        if "pdf" not in form:
            raise ValueError("No PDF file uploaded.")

        file_item = form["pdf"]
        filename = safe_filename(file_item.filename or "paper.pdf")
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}"
        run_dir = self.server.output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        input_path = run_dir / filename
        with input_path.open("wb") as handle:
            handle.write(file_item.file.read())

        stem = input_path.stem
        outlined_path = run_dir / f"{stem}.outlined.pdf"
        debug_path = run_dir / f"{stem}.debug.pdf"

        min_confidence = float(form.getvalue("minConfidence", "0.35"))
        force = form.getvalue("force", "false") == "true"
        options = BuildOptions(
            dry_run=False,
            force=force,
            min_confidence=min_confidence,
        )

        build = build_outline_for_pdf(input_path, outlined_path, options, debug_pdf_path=debug_path)
        if build.skipped_reason:
            raise ValueError(build.skipped_reason)

        return {
            "entries": [entry.as_dict() for entry in build.entries],
            "outlined_url": run_file_url(run_id, outlined_path.name),
            "debug_url": run_file_url(run_id, debug_path.name),
        }

    def _serve_run_file(self) -> None:
        parts = [unquote(part) for part in self.path.split("/") if part]
        if len(parts) != 3:
            self.send_error(404)
            return

        _, run_id, filename = parts
        path = (self.server.output_root / safe_filename(run_id) / safe_filename(filename)).resolve()
        if not str(path).startswith(str(self.server.output_root.resolve())) or not path.exists():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send_bytes(path.read_bytes(), content_type)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "file"


def run_file_url(run_id: str, filename: str) -> str:
    return f"/runs/{quote(run_id)}/{quote(filename)}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local drag-and-drop debug UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-root", type=Path, default=Path("debug-runs"))
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), DebugHandler)
    server.output_root = output_root  # type: ignore[attr-defined]

    url = f"http://{args.host}:{args.port}/"
    print(f"Debug UI running at {url}")
    print(f"Outputs will be saved under {output_root}")
    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping debug UI.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
