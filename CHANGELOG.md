# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project setup: README with the planned scope and roadmap, security policy, issue templates, `.editorconfig`, `.gitattributes` and `.gitignore`.
- Command line skeleton: `miniops --help`, `miniops --version` and `miniops version`, which reports the miniOPs and Python versions, operating system and architecture.
- Development tooling: uv project built with `uv_build`, ruff, mypy in strict mode, pytest with a coverage threshold of 85% and pre-commit hooks.
- Contributing guide with the development setup, and a pull request template.
- Continuous integration on GitHub Actions: pre-commit checks, tests on Linux, macOS and Windows with Python 3.12 to 3.14, a package build and a pull request title check. Dependabot keeps dependencies, actions and pre-commit hooks up to date.
- Release workflow: pushing a version tag builds the package and publishes it to PyPI through Trusted Publishing, with provenance attestations, and then creates the GitHub release.
