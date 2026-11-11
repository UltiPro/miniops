# Contributing to miniOPs

Thanks for your interest in miniOPs! The project is at an early (pre-alpha) stage: the command line skeleton exists and most features are still being designed, so discussion is as valuable as code.

## How to help right now

- **Share use cases.** Open an issue describing how you train and deploy models today and where miniOPs could help.
- **Discuss the design.** The planned scope and roadmap are described in the [README](README.md). Open an issue or start a [discussion](https://github.com/UltiPro/miniops/discussions) if something looks wrong or missing.
- **Report bugs** using the bug report template.

## Ground rules

- Be respectful and constructive.
- Everything in the repository is written in English: code, comments, docs, issues and commit messages.
- Larger changes, especially architectural ones, start with an issue, so we can agree on the approach before you invest time in a pull request.
- miniOPs supports Linux, macOS and Windows. Avoid OS-specific assumptions: use `pathlib` for paths, start subprocesses with argument lists instead of a shell, and read and write files with explicit UTF-8 encoding.

## Development setup

You need [uv](https://docs.astral.sh/uv/) and Git. The commands below work the same on Linux, macOS and Windows.

```bash
git clone https://github.com/UltiPro/miniops.git
cd miniops
uv sync                     # creates .venv with the project and all development tools
uv run pre-commit install   # runs the checks below before every commit
```

The project is developed on the lowest supported Python version, pinned in `.python-version`; uv installs it when needed.

| Task | Command |
|---|---|
| Run the CLI from the working tree | `uv run miniops --help` |
| Run the tests with coverage | `uv run pytest` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |
| Type check | `uv run mypy` |
| Run every pre-commit check | `uv run pre-commit run --all-files` |

Test coverage must stay at or above 85%. Public functions and classes need type hints and Google style docstrings. A docstring at the top of a file is optional: add one only when it says more than the file name does.

Write comments the way you would explain something to a colleague: in plain, natural language and as briefly as possible. Comment only where the code does not speak for itself, and say why rather than repeating what the code does.

## Pull requests

- Keep pull requests focused on one change.
- Add or update tests and documentation together with the code, and add an entry to `CHANGELOG.md` under "Unreleased".
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and PR titles, for example `feat(registry): add version bump command` or `fix(cli): handle missing config file`.
- Pull requests are squash-merged, so the PR title becomes the commit message on `main`.

## Reporting security issues

Please do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).
