import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Variables que controla cada prueba: se quitan del entorno heredado para que
# una configuración real del proceso no altere el resultado esperado.
_CONTROLLED_PREFIXES = ("POSTGRES_", "DJANGO_", "PYTHON_DOTENV_", "GASTOS_")

# Rutas punteadas sintéticas: se leen como texto, nunca se importan.
_PROVEEDOR_ARCHIVO = "ruta.sintetica.ProveedorDeArchivo"
_PROVEEDOR_PROCESO = "ruta.sintetica.ProveedorDeProceso"

_READ_SETTINGS = (
    "import json, runpy, sys; config = runpy.run_path(sys.argv[1]); "
    "print(json.dumps({'port': config['DATABASES']['default']['PORT'], "
    "'debug': config['DEBUG'], 'hosts': config['ALLOWED_HOSTS'], "
    "'provider': config['GASTOS_PAYMENT_DOCUMENT_PROVIDER']}))"
)


def _load_isolated_settings(
    tmp_path: Path, env_file: str | None, overrides: dict[str, str]
) -> dict:
    """Ejecuta una copia aislada de `settings.py` y devuelve lo configurado.

    La copia vive en `tmp_path`, así que `load_dotenv` sólo puede leer el `.env`
    sintético escrito por la prueba y nunca el del repositorio.
    """
    package = tmp_path / "cooperadora"
    package.mkdir()
    settings_copy = package / "settings.py"
    settings_copy.write_bytes((_PROJECT_ROOT / "cooperadora" / "settings.py").read_bytes())
    if env_file is not None:
        (tmp_path / ".env").write_text(env_file, encoding="utf-8")

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_CONTROLLED_PREFIXES)
    }
    environment.update(overrides)

    other_directory = tmp_path / "other-working-directory"
    other_directory.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", _READ_SETTINGS, str(settings_copy)],
        cwd=other_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("file_present", "process_port", "expected_port"),
    [(True, None, "6543"), (True, "55432", "55432"), (False, "55432", "55432")],
)
def test_settings_resolve_environment_from_project_root(
    tmp_path, file_present, process_port, expected_port
):
    env_file = (
        "POSTGRES_PORT=6543\nDJANGO_DEBUG=false\nDJANGO_ALLOWED_HOSTS=demo.invalid\n"
        if file_present
        else None
    )
    overrides = {} if process_port is None else {"POSTGRES_PORT": process_port}

    configured = _load_isolated_settings(tmp_path, env_file, overrides)

    assert configured["port"] == expected_port
    if file_present:
        assert configured["debug"] is False
        assert configured["hosts"] == ["demo.invalid"]


def _env_file_with_provider(provider_value: str | None) -> str:
    """`.env` sintético con hosts válidos y, si corresponde, el proveedor."""
    lines = ["DJANGO_ALLOWED_HOSTS=demo.invalid"]
    if provider_value is not None:
        lines.append(f"GASTOS_PAYMENT_DOCUMENT_PROVIDER={provider_value}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("file_present", "file_value", "process_value", "expected_provider"),
    [
        # Sin `.env` ni variable de proceso: la clave no existe.
        (False, None, None, None),
        # `.env` presente pero sin la clave.
        (True, None, None, None),
        # Definida vacía o con sólo espacios: se trata como ausente.
        (True, "", None, None),
        (True, "   ", None, None),
        # Ruta punteada sintética leída del `.env`, con espacios laterales.
        (True, f"  {_PROVEEDOR_ARCHIVO}  ", None, _PROVEEDOR_ARCHIVO),
        # Sólo la variable del proceso, también recortada.
        (False, None, f"  {_PROVEEDOR_PROCESO}  ", _PROVEEDOR_PROCESO),
        # La variable del proceso tiene prioridad sobre el `.env`.
        (True, _PROVEEDOR_ARCHIVO, _PROVEEDOR_PROCESO, _PROVEEDOR_PROCESO),
        # Proceso con sólo espacios: no cae al `.env`, queda sin configurar.
        (True, _PROVEEDOR_ARCHIVO, "   ", None),
    ],
)
def test_settings_read_optional_document_provider(
    tmp_path, file_present, file_value, process_value, expected_provider
):
    env_file = _env_file_with_provider(file_value) if file_present else None
    overrides = (
        {} if process_value is None else {"GASTOS_PAYMENT_DOCUMENT_PROVIDER": process_value}
    )

    configured = _load_isolated_settings(tmp_path, env_file, overrides)

    assert configured["provider"] == expected_provider
