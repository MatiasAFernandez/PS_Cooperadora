import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("file_present", "process_port", "expected_port"),
    [(True, None, "6543"), (True, "55432", "55432"), (False, "55432", "55432")],
)
def test_settings_resolve_environment_from_project_root(
    tmp_path, file_present, process_port, expected_port
):
    project_root = Path(__file__).resolve().parents[1]
    package = tmp_path / "cooperadora"
    package.mkdir()
    settings_copy = package / "settings.py"
    settings_copy.write_bytes((project_root / "cooperadora" / "settings.py").read_bytes())
    if file_present:
        (tmp_path / ".env").write_text(
            "POSTGRES_PORT=6543\nDJANGO_DEBUG=false\n"
            "DJANGO_ALLOWED_HOSTS=demo.invalid\n",
            encoding="utf-8",
        )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "DJANGO_", "PYTHON_DOTENV_"))
    }
    if process_port is not None:
        environment["POSTGRES_PORT"] = process_port
    other_directory = tmp_path / "other-working-directory"
    other_directory.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, runpy, sys; config = runpy.run_path(sys.argv[1]); "
            "print(json.dumps({'port': config['DATABASES']['default']['PORT'], "
            "'debug': config['DEBUG'], 'hosts': config['ALLOWED_HOSTS']}))",
            str(settings_copy),
        ],
        cwd=other_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    configured = json.loads(result.stdout)
    assert configured["port"] == expected_port
    if file_present:
        assert configured["debug"] is False
        assert configured["hosts"] == ["demo.invalid"]
