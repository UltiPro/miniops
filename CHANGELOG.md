# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Core domain model: models, versions with semantic version numbers, runs and aliases, with the rules for releasing, renumbering and deleting a version.
- Interfaces (ports) for the metadata store and the artifact store, and provisional ones for the executor, the serving backend and the image registry.
- Local metadata store in SQLite, the first implementation of the metadata port. Its schema is versioned and upgrades itself when a store is opened, after making a backup.
- `miniops init` creates a project in the current directory: it writes `miniops.toml` and adds `.miniops/` to `.gitignore`.
- `miniops config show` prints the configuration of the project that the current directory belongs to.
- A command that has a problem inside a project leaves its log in `.miniops/logs/miniops.log`: what it did and the error, with the full traceback when the error is a problem of the system or unexpected. A command without warnings or errors writes nothing there.
- Local artifact store, the first implementation of the artifact port: files in `.miniops/artifacts/`. A stored file is never replaced, and its content is checked against its digest when it is read.
- `miniops new <name> --flavor sklearn --task <task>` creates a model in the project: the directory `models/<name>/` with `model.toml` and a `model.py` to fill in, and the model in the store with its first draft, `1.0.0`.
- `miniops registry list` shows the models of the project, `miniops registry list <model>` the versions of one model, and `miniops registry show <model> --version <number or alias>` one version.
- `miniops doctor` checks that uv and git are installed and that git has a user name and email, and inside a project, its configuration and the schema version of its store. It changes nothing and ends with exit code 1 when it finds a problem.
- The scikit-learn flavor, installed with `miniops-ml[sklearn]` (polars, scikit-learn and skops). A model class subclasses `SklearnModel` and returns its estimator from `build`. It trains on a polars DataFrame, checks that the target column fits the task, predicts a `prediction` column and saves the model with skops, which refuses to load types that were not trusted.
- The job runner, `python -m miniops.runner <job file>`, which runs in the environment of a model. It reads a job file, trains the class that `entrypoint` names on a Parquet file and writes the model files and a result file with the signature, the types to trust when loading and where it ran. A failed training leaves a result that says why. Both files carry a protocol version.

### Changed

- An error that miniOPs reports ends with a short message and exit code 1 instead of a traceback.
- A problem of the system, such as a full disk, a missing permission or a file in the way, ends with its message, and inside a project with the path of the log. A store that another process is using is reported as busy.
- A configuration file that is missing or not saved as UTF-8 is reported as a configuration error. A UTF-8 byte order mark at its start is accepted.
- On Windows, output redirected to a file or a pipe shows a character that its code page lacks as `?`, instead of stopping the command.
- An unexpected error inside a project shows a short message with the path of the log instead of a traceback. Outside a project, where there is no log, the traceback is still shown.
- pydantic is now a dependency. It validates the configuration files.

## [0.1.0a1] - 2026-11-11

First pre-release: the project foundations and the command line skeleton. The model lifecycle features are not implemented yet.

### Added

- Initial project setup: README with the planned scope and roadmap, security policy, issue templates, `.editorconfig`, `.gitattributes` and `.gitignore`.
- Command line skeleton: `miniops --help`, `miniops --version` and `miniops version`, which reports the miniOPs and Python versions, operating system and architecture.
- Development tooling: uv project built with `uv_build`, ruff, mypy in strict mode, pytest with a coverage threshold of 85% and pre-commit hooks.
- Contributing guide with the development setup, and a pull request template.
- Continuous integration on GitHub Actions: pre-commit checks, tests on Linux, macOS and Windows with Python 3.12 to 3.14, a package build and a pull request title check. Dependabot keeps dependencies, actions and pre-commit hooks up to date.
- Release workflow: pushing a version tag builds the package and publishes it to PyPI through Trusted Publishing, with provenance attestations, and then creates the GitHub release.

[Unreleased]: https://github.com/UltiPro/miniops/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/UltiPro/miniops/releases/tag/v0.1.0a1
