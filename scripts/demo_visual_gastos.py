"""Recrea o sirve la demo visual aislada de Gastos."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from psycopg import connect, sql

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "ps_cooperadora_demo_visual_gastos"
STORAGE = ROOT / ".local" / "demo-visual-gastos"
MARKER = "PS_Cooperadora: demo visual sintetica de Gastos"
PORT = "127.0.0.1:8017"


def preparar_entorno():
    config = {**dotenv_values(ROOT / ".env"), **os.environ}
    host = config.get("POSTGRES_HOST", "localhost")
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("La demo visual requiere PostgreSQL local.")
    if STORAGE.resolve() != STORAGE:
        raise SystemExit("El directorio de demo visual apunta fuera de su ruta reservada.")
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "cooperadora.settings",
        "POSTGRES_DB": DATABASE,
        "DOCUMENT_STORAGE_ROOT": str(STORAGE / "documentos"),
        "DEMO_IDENTITY_ENABLED": "true",
        "DJANGO_DEBUG": "true",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "GASTOS_PAYMENT_DOCUMENT_PROVIDER": "documentos.c01.ProveedorDocumentalGastos",
        "PYTHONUTF8": "1",
    }
    connection = connect(
        dbname="postgres",
        host=host,
        port=config.get("POSTGRES_PORT", "5432"),
        user=config.get("POSTGRES_USER", "cooperadora"),
        password=config.get("POSTGRES_PASSWORD", "cooperadora_local"),
        autocommit=True,
    )
    return env, connection


def ejecutar(env, *args):
    subprocess.run([sys.executable, *args], cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("reiniciar", "servir"))
    args = parser.parse_args()
    env, connection = preparar_entorno()
    marker_file = STORAGE / ".demo-visual"
    with connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(62170617)")
        if not cursor.fetchone()[0]:
            raise SystemExit("Ya hay otra preparación de la demo visual en curso.")
        cursor.execute(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
            (DATABASE,),
        )
        existente = cursor.fetchone()
        if existente and existente[0] != MARKER:
            raise SystemExit("La base reservada existe y no pertenece a esta demo visual.")
        if STORAGE.exists() and (
            not marker_file.is_file()
            or marker_file.is_symlink()
            or marker_file.read_text(encoding="utf-8") != MARKER
        ):
            raise SystemExit("El directorio reservado existe y no pertenece a esta demo visual.")

        if args.accion == "reiniciar":
            nombre = sql.Identifier(DATABASE)
            if existente:
                cursor.execute(sql.SQL("DROP DATABASE {}").format(nombre))
            if STORAGE.exists():
                shutil.rmtree(STORAGE)
            STORAGE.mkdir(parents=True)
            marker_file.write_text(MARKER, encoding="utf-8")
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(nombre))
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(nombre, sql.Literal(MARKER))
            )
            ejecutar(env, "manage.py", "migrate", "--noinput")
            ejecutar(env, "scripts/prepare_e2e_i3_fixtures.py", "--visual")
            (STORAGE / ".lista").touch()
            print(f"Demo visual preparada. Ejecutá servir y abrí http://{PORT}/demo/acceso/.")
            return

        if not existente or not (STORAGE / ".lista").is_file():
            raise SystemExit("Primero ejecutá reiniciar para preparar la demo visual.")

    ejecutar(env, "manage.py", "runserver", PORT, "--noreload")


if __name__ == "__main__":
    main()
