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
            self.send_error(HTTPStatus.CONFLICT, f"File already exists: {filename}")
            return

        with open(target_path, "wb") as output_file:
            shutil.copyfileobj(field.file, output_file)

        redirect_target = self.path.split("?", 1)[0].split("#", 1)[0] or "/"
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", redirect_target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    @staticmethod
    def _upload_section():
        return """
  <section class="upload-panel">
    <form class="upload-form" method="post" enctype="multipart/form-data">
      <label class="upload-label" for="upload-file">
        <span>Upload a file</span>
        <input id="upload-file" name="file" type="file" required>
      </label>
      <button type="submit">Upload</button>
    </form>
    <p class="upload-note">Uploads are enabled for this server. Duplicate filenames are rejected.</p>
  </section>
"""

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
    --bg: #0f1115; --panel: #161922; --border: #262b38; --text: #e6e8ee;
    --muted: #8a8fa3; --accent: #6c8cff; --hover: #1d2230;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text);
  }}
  header {{
    padding: 24px 32px 12px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  }}
  h1 {{ font-size: 18px; font-weight: 600; margin: 0; word-break: break-all; }}
  h1 .muted {{ color: var(--muted); font-weight: 400; }}
  #search {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 8px; font-size: 14px; width: 220px; outline: none;
  }}
  #search:focus {{ border-color: var(--accent); }}
  .upload-panel {{
    margin: 20px 32px 0; padding: 16px; border: 1px solid var(--border); border-radius: 12px;
    background: linear-gradient(180deg, rgba(108, 140, 255, 0.08), rgba(108, 140, 255, 0.02));
  }}
  .upload-form {{
    display: flex; gap: 12px; align-items: end; flex-wrap: wrap;
  }}
  .upload-label {{
    display: flex; flex-direction: column; gap: 6px; color: var(--muted); font-size: 13px;
  }}
  .upload-label input {{
    color: var(--text); background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px; min-width: min(100%, 320px);
  }}
  .upload-form button {{
    background: var(--accent); color: white; border: 0; border-radius: 8px;
    padding: 9px 16px; font-size: 14px; cursor: pointer;
  }}
  .upload-form button:hover {{ filter: brightness(1.05); }}
  .upload-note {{ margin: 10px 0 0; color: var(--muted); font-size: 12px; }}
  main {{ padding: 16px 32px 48px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
    color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--border);
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }}
  tr:hover {{ background: var(--hover); }}
  .col-size, .col-date {{ color: var(--muted); white-space: nowrap; width: 140px; }}
  .col-name a {{
    color: var(--text); text-decoration: none; display: flex; align-items: center; gap: 10px;
  }}
  .col-name a:hover {{ color: var(--accent); }}
  .icon {{ font-size: 18px; }}
  .empty {{ text-align: center; color: var(--muted); padding: 40px 0; }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>📂 <span class="muted">Index of</span> {path}</h1>
  <input id="search" type="text" placeholder="Filter files & folders..." autocomplete="off">
</header>
{upload_section}
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
  const search = document.getElementById('search');
  const rows = Array.from(document.querySelectorAll('#listing tbody tr'));
  search.addEventListener('input', () => {{
    const q = search.value.toLowerCase();
    rows.forEach(r => {{
      const name = r.getAttribute('data-name');
      if (name === null) return; // parent row
      r.style.display = name.includes(q) ? '' : 'none';
    }});
  }});
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
