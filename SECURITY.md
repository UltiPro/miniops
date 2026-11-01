# Security Policy

## Supported versions

miniOPs has no stable release yet. Security fixes will be applied to the latest released version once releases begin.

## Reporting a vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Use GitHub's [private vulnerability reporting](https://github.com/UltiPro/miniops/security/advisories/new) instead. Include:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- the affected version or commit.

You can expect an initial response within 7 days.

## A note on model artifacts

Many machine learning serialization formats, including Python's `pickle` and `joblib`, can execute arbitrary code when a file is loaded. **Only load model artifacts from sources you trust.** This also applies to model bundles imported with `miniops import`, because they contain model artifacts. miniOPs will prefer safer formats where frameworks support them (for example `skops` for scikit-learn) and will document the risks of every format it uses.
