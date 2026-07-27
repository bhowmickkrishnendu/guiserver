# Contributing to guiserver

Thanks for considering a contribution! This project is small and welcomes
bug reports, feature requests, documentation fixes, and pull requests from
anyone.

## Ground rules

- Be respectful and constructive in issues and PR discussions.
- One topic per issue/PR — keep changes focused and reviewable.
- No breaking changes to the existing CLI flags (`port`, `--bind`,
  `--directory`) without discussion in an issue first — this project's whole
  point is staying a drop-in `http.server` replacement.
- Keep it dependency-free where possible. New third-party dependencies need a
  strong justification.

## Reporting bugs

Open an issue and include:
- Your OS and Python version (`python --version`)
- The exact command you ran
- What you expected vs. what happened
- Steps to reproduce, if possible

## Suggesting features / enhancements

Open an issue describing:
- The problem you're trying to solve (not just the solution)
- Why it fits the project's scope (simple, zero-config GUI file server)

Feature ideas that fit well: better browsing (file previews, thumbnails),
usability polish, accessibility, additional CLI flags that mirror
`http.server`'s spirit. Feature ideas that likely won't fit: authentication,
file uploads/editing, or anything that turns this into a full file-management
app — open an issue first if you're unsure before writing code.

## Submitting a pull request

1. Fork the repo and create a branch from `main`:
   `git checkout -b fix/short-description` or `feat/short-description`
2. Make your changes. Keep commits small and messages descriptive.
3. Test manually:
   - Run `guiserver` (or `python -m guiserver`) against a folder with nested
     subfolders and confirm:
     - the directory listing renders correctly
     - parent folder (`..`) navigation works at every depth
     - file downloads still work
     - the search/filter box still works
4. Update the README if your change affects usage or behavior.
5. Open a PR against `main` describing:
   - What changed and why
   - How you tested it
6. Be responsive to review feedback — most PRs will need at least one round
   of small revisions.

## Code style

- Plain, readable Python (standard library only in `guiserver/`).
- Follow the existing formatting/structure in `server.py` and
  `__main__.py`.
- Docstrings/comments for anything non-obvious, especially around HTTP
  edge cases (that's where the bugs tend to hide).

## License

By contributing, you agree that your contributions will be licensed under
the project's [MIT License](LICENSE).
