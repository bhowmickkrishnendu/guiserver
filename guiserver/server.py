"""
guiserver.server
-----------------
A drop-in replacement for `python -m http.server` that renders a nice-looking
GUI file/folder browser instead of the plain "Index of /" listing.

Everything else (actual file downloads, range requests, MIME handling, etc.)
is handled exactly like the standard library's http.server, we only override
how a *directory* is rendered.
"""

import cgi
import html
import io
import os
import shutil
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Extension -> emoji icon, purely cosmetic
ICONS = {
    ".py": "🐍", ".js": "📜", ".ts": "📜", ".json": "🧾", ".md": "📝",
    ".txt": "📄", ".pdf": "📕", ".doc": "📘", ".docx": "📘",
    ".xls": "📊", ".xlsx": "📊", ".csv": "📊", ".ppt": "📙", ".pptx": "📙",
    ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️", ".svg": "🖼️",
    ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬", ".mov": "🎬", ".mkv": "🎬",
    ".zip": "🗜️", ".tar": "🗜️", ".gz": "🗜️", ".rar": "🗜️", ".7z": "🗜️",
    ".html": "🌐", ".css": "🎨", ".exe": "⚙️", ".sh": "⚙️",
}
FOLDER_ICON = "📁"
FILE_ICON = "📄"


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class GuiHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with a styled, searchable directory index."""

    server_version = "GuiHTTPServer/0.1"
    upload_enabled = False

    def list_directory(self, path):
        try:
            entries = os.scandir(path)
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "No permission to list directory")
            return None

        dirs, files = [], []
        for entry in entries:
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            info = {"name": entry.name, "is_dir": is_dir}
            try:
                stat = entry.stat()
                info["size"] = stat.st_size
                info["mtime"] = stat.st_mtime
            except OSError:
                info["size"] = 0
                info["mtime"] = 0
            (dirs if is_dir else files).append(info)

        dirs.sort(key=lambda e: e["name"].lower())
        files.sort(key=lambda e: e["name"].lower())

        display_path = urllib.parse.unquote(self.path)
        display_path = html.escape(display_path or "/")

        rows = []
        # Parent directory link (unless we're at the web root).
        # Strip any query string/fragment first, then compute the parent
        # path carefully so we never emit a bare "//" href -- browsers treat
        # a leading "//" as a protocol-relative URL (same scheme, empty
        # host), which gets blocked (shows as about:blank#blocked) instead
        # of navigating up a folder.
        current = self.path.split("?", 1)[0].split("#", 1)[0]
        if current.rstrip("/") != "":
            parent = current.rstrip("/").rsplit("/", 1)[0]
            parent_href = parent + "/" if parent else "/"
            rows.append(self._row("..", parent_href, True, None, None, is_parent=True))

        for e in dirs:
            link = urllib.parse.quote(e["name"]) + "/"
            rows.append(self._row(e["name"], link, True, None, e["mtime"]))
        for e in files:
            link = urllib.parse.quote(e["name"])
            rows.append(self._row(e["name"], link, False, e["size"], e["mtime"]))

        body = PAGE_TEMPLATE.format(
            path=display_path,
          theme_controls=self._theme_controls(),
          toolbar_row=self._toolbar_row() if self.upload_enabled else "",
            upload_section=self._upload_section() if self.upload_enabled else "",
            rows="\n".join(rows) if rows else '<tr><td colspan="4" class="empty">This folder is empty</td></tr>',
            count=len(dirs) + len(files),
        )

        encoded = body.encode("utf-8", "surrogateescape")
        f = io.BytesIO(encoded)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def do_POST(self):
        if not self.upload_enabled:
            self.send_error(HTTPStatus.FORBIDDEN, "Uploads are disabled")
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(HTTPStatus.BAD_REQUEST, "Expected multipart form upload")
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )

        if "file" not in form:
            self.send_error(HTTPStatus.BAD_REQUEST, "No file selected")
            return

        field = form["file"]
        filename = os.path.basename(getattr(field, "filename", "") or "")
        if not filename or filename in {".", ".."}:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid filename")
            return

        target_dir = self.translate_path(urllib.parse.urlparse(self.path).path)
        if not os.path.isdir(target_dir):
            self.send_error(HTTPStatus.BAD_REQUEST, "Uploads must target a directory")
            return

        target_path = os.path.join(target_dir, filename)
        if os.path.exists(target_path):
            self._send_error_page(
                HTTPStatus.CONFLICT,
                "Upload conflict",
                f"File already exists: {html.escape(filename)}.",
            )
            return

        with open(target_path, "wb") as output_file:
            shutil.copyfileobj(field.file, output_file)

        redirect_target = self.path.split("?", 1)[0].split("#", 1)[0] or "/"
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", redirect_target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_error_page(self, status, title, message):
        body = self._error_page(status, title, message)
        encoded = body.encode("utf-8", "surrogateescape")
        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    @staticmethod
    def _upload_section():
        return """
    <form class="upload-form" method="post" enctype="multipart/form-data">
      <label class="upload-dropzone" for="upload-file">
        <input id="upload-file" name="file" type="file" required>
        <span class="upload-prompt">Hover here or click here to upload</span>
        <span class="upload-filename" id="selected-file-name">No file selected</span>
      </label>
      <div class="upload-actions">
        <span class="upload-note">Uploads are enabled for this server. Duplicate filenames are rejected.</span>
        <button class="upload-submit" type="submit">Start upload</button>
      </div>
    </form>
"""

    @staticmethod
    def _theme_controls():
        return """
  <nav class="theme-switcher" aria-label="Theme selector">
    <button type="button" data-theme-choice="system">System</button>
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
  </nav>
"""

    def _toolbar_row(self):
        return f"""
<div class="toolbar-row">
  <details class="upload-disclosure">
    <summary class="upload-toggle">Upload</summary>
    <div class="upload-panel">
{self._upload_section()}
    </div>
  </details>
</div>
"""

    def _error_page(self, status, title, message):
        path = html.escape(urllib.parse.unquote(self.path) or "/")
        return ERROR_PAGE_TEMPLATE.format(
            status=status,
            title=html.escape(title),
            message=message,
            path=path,
            theme_controls=self._theme_controls(),
        )

    @staticmethod
    def _row(name, link, is_dir, size, mtime, is_parent=False):
        import datetime
        icon = FOLDER_ICON if is_dir else ICONS.get(os.path.splitext(name)[1].lower(), FILE_ICON)
        display_name = ".. (parent folder)" if is_parent else name
        size_str = "-" if (is_dir or size is None) else human_size(size)
        mtime_str = "-" if not mtime else datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        row_class = "row-dir" if is_dir else "row-file"
        name_attr = html.escape(name.lower())
        return (
            f'<tr class="{row_class}" data-name="{name_attr}">'
            f'<td class="col-name"><a href="{link}">'
            f'<span class="icon">{icon}</span>{html.escape(display_name)}</a></td>'
            f'<td class="col-size">{size_str}</td>'
            f'<td class="col-date">{mtime_str}</td>'
            f'</tr>'
        )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Index of {path}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f4f7fb; --panel: #ffffff; --border: #d9deea; --text: #151a24;
    --muted: #5f687d; --accent: #2f5bff; --hover: #eaf0ff; --card: rgba(255, 255, 255, 0.92);
    --shadow: 0 20px 45px rgba(20, 30, 60, 0.08);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f1115; --panel: #161922; --border: #262b38; --text: #e6e8ee;
      --muted: #8a8fa3; --accent: #6c8cff; --hover: #1d2230; --card: rgba(22, 25, 34, 0.92);
      --shadow: 0 20px 45px rgba(0, 0, 0, 0.35);
    }}
  }}
  :root[data-theme="light"] {{
    --bg: #f4f7fb; --panel: #ffffff; --border: #d9deea; --text: #151a24;
    --muted: #5f687d; --accent: #2f5bff; --hover: #eaf0ff; --card: rgba(255, 255, 255, 0.92);
    --shadow: 0 20px 45px rgba(20, 30, 60, 0.08);
  }}
  :root[data-theme="dark"] {{
    --bg: #0f1115; --panel: #161922; --border: #262b38; --text: #e6e8ee;
    --muted: #8a8fa3; --accent: #6c8cff; --hover: #1d2230; --card: rgba(22, 25, 34, 0.92);
    --shadow: 0 20px 45px rgba(0, 0, 0, 0.35);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text);
  }}
  header {{
    padding: 24px 32px 12px; border-bottom: 1px solid var(--border);
    display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  }}
  h1 {{ font-size: 18px; font-weight: 600; margin: 0; word-break: break-all; }}
  h1 .muted {{ color: var(--muted); font-weight: 400; }}
  .header-actions {{ display: flex; align-items: flex-start; gap: 12px; margin-left: auto; flex-wrap: wrap; }}
  .theme-switcher {{
    display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 999px;
    padding: 4px; box-shadow: var(--shadow);
  }}
  .theme-switcher button {{
    border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px;
    padding: 7px 12px; border-radius: 999px;
  }}
  .theme-switcher button[aria-pressed="true"] {{ background: var(--accent); color: white; }}
  .theme-switcher button:hover {{ color: var(--text); }}
  #search {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 8px; font-size: 14px; width: 220px; outline: none;
  }}
  #search:focus {{ border-color: var(--accent); }}
  .toolbar-row {{ padding: 14px 32px 0; display: flex; justify-content: flex-end; }}
  .upload-disclosure {{ width: min(100%, 760px); display: flex; flex-direction: column; align-items: flex-end; }}
  .upload-disclosure summary {{
    list-style: none; cursor: pointer; background: var(--accent); color: white;
    border-radius: 999px; padding: 10px 18px; font-size: 14px; font-weight: 600;
    box-shadow: var(--shadow); user-select: none;
  }}
  .upload-disclosure summary::-webkit-details-marker {{ display: none; }}
  .upload-panel {{
    width: 100%; margin-top: 12px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 18px;
    background: var(--card); box-shadow: var(--shadow); backdrop-filter: blur(14px);
  }}
  .upload-form {{ display: flex; gap: 16px; align-items: stretch; flex-wrap: nowrap; }}
  .upload-dropzone {{
    position: relative; flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; justify-content: center;
    gap: 3px; padding: 12px 16px; border: 1px dashed var(--border); border-radius: 16px; background: var(--panel);
    cursor: pointer; transition: transform 0.15s ease, border-color 0.15s ease, background 0.15s ease;
  }}
  .upload-dropzone:hover {{ transform: translateY(-1px); border-color: var(--accent); background: var(--hover); }}
  .upload-dropzone input {{ position: absolute; inset: 0; opacity: 0; cursor: pointer; }}
  .upload-prompt {{ font-size: 15px; font-weight: 600; line-height: 1.2; }}
  .upload-filename, .upload-note {{ color: var(--muted); font-size: 13px; }}
  .upload-filename {{ font-style: italic; }}
  .upload-actions {{
    flex: 0 0 auto; display: flex; flex-direction: column; justify-content: space-between; align-items: flex-end;
    gap: 10px; min-width: 220px;
  }}
  .upload-submit {{
    margin-left: auto; border: 0; border-radius: 12px; background: var(--accent); color: white;
    padding: 10px 18px; font-size: 14px; cursor: pointer;
  }}
  .upload-submit:hover {{ filter: brightness(1.05); }}
  main {{ padding: 16px 32px 48px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--border);
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }}
  tr:hover {{ background: var(--hover); }}
  .col-size, .col-date {{ color: var(--muted); white-space: nowrap; width: 140px; }}
  .col-name a {{ color: var(--text); text-decoration: none; display: flex; align-items: center; gap: 10px; }}
  .col-name a:hover {{ color: var(--accent); }}
  .icon {{ font-size: 18px; }}
  .empty {{ text-align: center; color: var(--muted); padding: 40px 0; }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; padding: 20px; }}
  @media (max-width: 720px) {{
    header, .toolbar-row, main {{ padding-left: 16px; padding-right: 16px; }}
    .header-actions {{ width: 100%; }}
    #search {{ width: 100%; }}
    .upload-form {{ flex-direction: column; }}
    .upload-actions {{ min-width: 0; align-items: flex-start; }}
  }}
  @media (min-width: 721px) {{
    .toolbar-row {{ position: relative; }}
    .upload-disclosure {{ position: relative; width: min(100%, 820px); }}
    .upload-disclosure summary {{ align-self: flex-end; }}
    .upload-panel {{
      position: absolute; right: 0; top: calc(100% + 10px); width: min(100%, 760px);
      margin-top: 0; z-index: 25;
    }}
  }}
</style>
</head>
<body>
<header>
  <h1>📂 <span class="muted">Index of</span> {path}</h1>
  <div class="header-actions">
    {theme_controls}
    <input id="search" type="text" placeholder="Filter files & folders..." autocomplete="off">
  </div>
</header>
{toolbar_row}
<main>
  <table id="listing">
    <thead>
      <tr><th class="col-name">Name</th><th class="col-size">Size</th><th class="col-date">Modified</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</main>
<footer>{count} item(s) &middot; Served by GUI Server &bull; Made with &#10084;&#65039; by Krishnendu Bhowmick</footer>
<script>
  const themeKey = 'guiserver-theme';
  const themeButtons = Array.from(document.querySelectorAll('[data-theme-choice]'));
  const root = document.documentElement;
  function applyTheme(theme, persist = true) {{
    if (theme === 'system') {{
      root.removeAttribute('data-theme');
    }} else {{
      root.setAttribute('data-theme', theme);
    }}
    themeButtons.forEach(button => {{
      const selected = button.dataset.themeChoice === theme;
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    }});
    if (persist) localStorage.setItem(themeKey, theme);
  }}
  const savedTheme = localStorage.getItem(themeKey) || 'system';
  applyTheme(savedTheme, false);
  themeButtons.forEach(button => button.addEventListener('click', () => applyTheme(button.dataset.themeChoice)));

  const search = document.getElementById('search');
  const rows = Array.from(document.querySelectorAll('#listing tbody tr'));
  search.addEventListener('input', () => {{
    const q = search.value.toLowerCase();
    rows.forEach(r => {{
      const name = r.getAttribute('data-name');
      if (name === null) return;
      r.style.display = name.includes(q) ? '' : 'none';
    }});
  }});

  const uploadInput = document.getElementById('upload-file');
  const selectedFileName = document.getElementById('selected-file-name');
  if (uploadInput && selectedFileName) {{
    uploadInput.addEventListener('change', () => {{
      selectedFileName.textContent = uploadInput.files.length ? uploadInput.files[0].name : 'No file selected';
    }});
  }}
</script>
</body>
</html>
"""


ERROR_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Error {status}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f4f7fb; --panel: #ffffff; --border: #d9deea; --text: #151a24;
    --muted: #5f687d; --accent: #2f5bff; --hover: #eaf0ff; --card: rgba(255, 255, 255, 0.92);
    --shadow: 0 20px 45px rgba(20, 30, 60, 0.12);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0f1115; --panel: #161922; --border: #262b38; --text: #e6e8ee;
      --muted: #8a8fa3; --accent: #6c8cff; --hover: #1d2230; --card: rgba(22, 25, 34, 0.92);
      --shadow: 0 20px 45px rgba(0, 0, 0, 0.4);
    }}
  }}
  :root[data-theme="light"] {{
    --bg: #f4f7fb; --panel: #ffffff; --border: #d9deea; --text: #151a24;
    --muted: #5f687d; --accent: #2f5bff; --hover: #eaf0ff; --card: rgba(255, 255, 255, 0.92);
    --shadow: 0 20px 45px rgba(20, 30, 60, 0.12);
  }}
  :root[data-theme="dark"] {{
    --bg: #0f1115; --panel: #161922; --border: #262b38; --text: #e6e8ee;
    --muted: #8a8fa3; --accent: #6c8cff; --hover: #1d2230; --card: rgba(22, 25, 34, 0.92);
    --shadow: 0 20px 45px rgba(0, 0, 0, 0.4);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: radial-gradient(circle at top, rgba(108, 140, 255, 0.12), transparent 45%), var(--bg);
    color: var(--text);
  }}
  header {{ padding: 22px 32px 0; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
  .theme-switcher {{ display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 4px; box-shadow: var(--shadow); }}
  .theme-switcher button {{ border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; padding: 7px 12px; border-radius: 999px; }}
  .theme-switcher button[aria-pressed="true"] {{ background: var(--accent); color: white; }}
  .error-shell {{ min-height: calc(100vh - 86px); display: grid; place-items: center; padding: 24px 32px 40px; }}
  .error-card {{ width: min(100%, 620px); background: var(--card); border: 1px solid var(--border); border-radius: 24px; box-shadow: var(--shadow); padding: 28px; }}
  .error-badge {{ display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border-radius: 999px; background: rgba(108, 140, 255, 0.14); color: var(--accent); font-size: 13px; font-weight: 600; }}
  .error-card h1 {{ margin: 14px 0 10px; font-size: 30px; }}
  .error-message {{ color: var(--muted); line-height: 1.6; margin: 0 0 20px; }}
  .error-meta {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; padding-top: 16px; border-top: 1px solid var(--border); }}
  .error-code {{ color: var(--muted); font-size: 13px; }}
  .error-link {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 12px; background: var(--accent); color: white; text-decoration: none; padding: 10px 16px; font-weight: 600; }}
</style>
</head>
<body>
<header>
  <div class="error-badge">GUI Server</div>
  {theme_controls}
</header>
<main class="error-shell">
  <section class="error-card" role="alert" aria-live="polite">
    <div class="error-badge">Upload conflict</div>
    <h1>{title}</h1>
    <p class="error-message">{message}</p>
    <div class="error-meta">
      <div class="error-code">HTTP {status} • Conflict</div>
      <a class="error-link" href="{path}">Back to folder</a>
    </div>
  </section>
</main>
<script>
  const themeKey = 'guiserver-theme';
  const themeButtons = Array.from(document.querySelectorAll('[data-theme-choice]'));
  const root = document.documentElement;
  function applyTheme(theme, persist = true) {{
    if (theme === 'system') {{
      root.removeAttribute('data-theme');
    }} else {{
      root.setAttribute('data-theme', theme);
    }}
    themeButtons.forEach(button => {{
      const selected = button.dataset.themeChoice === theme;
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    }});
    if (persist) localStorage.setItem(themeKey, theme);
  }}
  const savedTheme = localStorage.getItem(themeKey) || 'system';
  applyTheme(savedTheme, false);
  themeButtons.forEach(button => button.addEventListener('click', () => applyTheme(button.dataset.themeChoice)));
</script>
</body>
</html>
"""


def run(port=8000, bind="", directory=None, allow_uploads=False):
    directory = directory or os.getcwd()

    class Handler(GuiHTTPRequestHandler):
        upload_enabled = allow_uploads

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    server_address = (bind, port)
    httpd = ThreadingHTTPServer(server_address, Handler)
    url_host = bind or "0.0.0.0"
    print(f"Serving GUI file browser for '{directory}'")
    print(f"  Local:   http://localhost:{port}/")
    print(f"  Network: http://{url_host}:{port}/")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()
