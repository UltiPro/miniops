import subprocess
import sys

# Code that runs in the environment of a model may use only these modules of miniOPs, so that
# the CLI, the stores and the registry stay on the host.
MODEL_SIDE = {
    "miniops",
    "miniops.core",
    "miniops.core.entities",
    "miniops.core.errors",
    "miniops.core.versions",
    "miniops.flavors",
    "miniops.flavors.base",
    "miniops.flavors.sklearn",
    "miniops.runner",
    "miniops.runner.__main__",
    "miniops.runner.jobs",
    "miniops.runner.protocol",
}


def test_the_code_of_a_model_environment_imports_nothing_from_the_host() -> None:
    script = (
        "import sys, miniops.flavors.sklearn, miniops.runner.__main__; "
        "print(*(name for name in sys.modules if name.split('.')[0] == 'miniops'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    imported = set(result.stdout.split())

    assert {"miniops.flavors.sklearn", "miniops.runner.__main__"} <= imported
    assert imported - MODEL_SIDE == set()
