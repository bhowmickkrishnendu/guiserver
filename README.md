# guiserver

A drop-in replacement for Python's built-in `http.server` — same one-command
simplicity, except instead of a plain "Index of /" text listing, you get a
clean, dark-themed, searchable **GUI file browser**.

```bash
pip install guiserver
guiserver 8080
```

Open `http://localhost:8080/` and browse your folder with icons, file sizes,
last-modified dates, and a live search box — instead of a bare list of links.

![status](https://img.shields.io/badge/status-active-brightgreen) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.8%2B-blue)

## Why this exists

Every developer knows the muscle memory: `cd` into a folder, run
`python -m http.server`, share the port, done. It's fast and it always works —
but the actual directory listing it produces is about as bare as web pages get.

One day, staring at that plain "Index of /" page for the hundredth time, it
just felt... boring. So this project adds a proper GUI on top of the exact
same idea: zero config, one command, serve a folder — just with a browser
experience that doesn't look like it's from 1996.

`guiserver` is **inspired directly by `http.server`** and built on top of the
same standard-library `http.server` module under the hood. It only replaces
how the directory listing page is rendered — downloads, byte-range requests,
MIME type handling, etc. all work exactly the way they do in `http.server`.

## Features

- 🎨 Dark-themed, responsive GUI file/folder browser
- 🔍 Instant client-side search/filter box
- 📁 Folders sorted first, then files, alphabetically
- 📏 File size and last-modified date columns
- ⬅️ Working parent-folder (`..`) navigation at any depth
- ⚙️ Same CLI usage pattern as `python -m http.server`
- 📦 Zero dependencies — pure Python standard library

## Install

Via pip (recommended):

```bash
pip install guiserver
```

From source:

```bash
git clone https://github.com/bhowmickkrishnendu/guiserver.git
cd guiserver
pip install .
```

## Usage

Same usage pattern as `python -m http.server`:

```bash
# Serve current folder on default port 8000
guiserver

# Serve current folder on a specific port
guiserver 8080

# Serve a specific folder
guiserver 8080 --directory "/path/to/folder"

# Bind to localhost only (not accessible on your network)
guiserver 8080 --bind 127.0.0.1
```

Or run it as a module, without the console script:

```bash
python -m guiserver 8080
```

## Contributing

Bug reports, feature requests, and pull requests are all welcome — this is a
small project built for anyone to use and improve. See
[CONTRIBUTING.md](https://github.com/bhowmickkrishnendu/guiserver?tab=contributing-ov-file) for guidelines on filing issues and
submitting PRs.

## License

MIT — see [LICENSE](https://github.com/bhowmickkrishnendu/guiserver?tab=MIT-1-ov-file). Use it, fork it, ship it.

---

Served by GUI Server • Made with ❤️ by Krishnendu Bhowmick
