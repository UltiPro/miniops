# miniOPs

> Lightweight, polars-native MLOps CLI for training, versioning and deploying models locally, in Docker or on Google Cloud.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)

> [!WARNING]
> miniOPs is in the **design phase**. There is no usable release yet. The commands shown below describe the planned interface and may change.

## Why miniOPs?

Most MLOps tooling is either a heavy platform you have to host, or a set of loosely connected libraries you have to glue together yourself. miniOPs aims for the middle ground:

- **One workflow, three targets.** The same commands train, register and deploy a model on your machine, in Docker containers, or on GCP.
- **Polars-native.** Data enters as a ready-made polars DataFrame (or a Parquet file) and predictions come back as polars. No pandas required.
- **Zero servers by default.** A solo user needs nothing but the CLI. Teams can share state through a cloud backend.
- **Opinionated, not magical.** You choose the framework and the target explicitly. miniOPs generates the template, installs the dependencies and handles the plumbing. The modelling decisions stay with you.
- **Reproducible by design.** Every model gets its own locked environment (`uv`), and every version records its code, data fingerprint, parameters and dependencies.
- **Runs where you work.** Linux, macOS and Windows, on x86_64 and arm64.

## What miniOPs is not

miniOPs starts where data engineering ends. It does **not** ingest, clean, join or transform raw data, and it is not a feature store. It expects a prepared DataFrame and takes over from there: validating the input contract, splitting, training, evaluating, versioning, serving and monitoring.

## Planned features

| Area | Capabilities |
|---|---|
| Projects & models | `init`, model templates per framework and target, isolated `uv` environment per model |
| Data contract | schema validation, dataset fingerprinting, split strategies (holdout, k-fold, stratified, time-based) |
| Training | config-driven runs, experiment tracking, hyperparameter tuning (Optuna) |
| Evaluation | task-specific metrics, quality gates, self-contained HTML reports with model cards |
| Model registry | semantic versioning (`1.0.0`), immutable released versions, aliases (`champion`, `challenger`), lineage |
| Portability | export and import of model versions as single files, `migrate` between targets with lineage preserved |
| Serving | batch prediction (Parquet in/out), generated FastAPI service, Docker images |
| Deployment | deploy, list, stop, delete and roll back deployments on every target |
| Monitoring | input and prediction drift *(later)* |
| UI | read-only web dashboard *(later)* |

### Frameworks

| Framework | Status |
|---|---|
| scikit-learn | planned (first) |
| LightGBM | planned |
| PyTorch | planned |

### Targets

| Target | Training | Serving | State |
|---|---|---|---|
| `local` | subprocess in the model's venv | local FastAPI (uvicorn) | SQLite + filesystem |
| `docker` | container | container | SQLite + filesystem (mounted) |
| `gcp` | Vertex AI custom training | Cloud Run | GCS + miniOPs metadata on GCP |

`local` and `docker` share the same state, so a model trained locally can be served in Docker right away. Moving a version to GCP (or back) is a single `miniops migrate`.

## A taste of the planned CLI

```bash
pip install miniops-ml          # the command is `miniops`

miniops init
miniops new churn --flavor sklearn --target local
miniops train churn --data data/train.parquet
miniops report churn --version 1.0.0          # HTML report
miniops registry release churn --version 1.0.0
miniops deploy churn --version 1.0.0 --target docker
miniops deploy list
miniops registry bump churn --from 1.0.0 --minor   # new draft 1.1.0
miniops migrate churn --version 1.0.0 --to gcp     # copy to the team's GCP store
```

## Roadmap

| Phase | Content |
|---|---|
| 0 | Foundations: design, architecture decisions, project tooling |
| 1 | Local target + scikit-learn: train, track, evaluate, register, batch predict, export and import |
| 2 | LightGBM |
| 3 | Serving + Docker target |
| 4 | Hyperparameter tuning and quality gates |
| 5 | GCP target and migration between targets |
| 6 | PyTorch |
| 7 | Monitoring |
| 8 | Web UI |

## Contributing

The project is at an early stage, so the best way to help right now is to open an issue with ideas, use cases or feedback on the design, or start a thread in [Discussions](https://github.com/UltiPro/miniops/discussions). For the development setup and guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

miniOPs is licensed under the [Apache License 2.0](LICENSE).
