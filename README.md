# PS Cooperadora

Sistema web para la gestión y el seguimiento de solicitudes de facturación,
gastos y pagos de la Asociación Cooperadora de la UTN Facultad Regional
Resistencia.

## Estado

Base técnica para el primer incremento de demostración, todavía sin funcionalidad
de negocio. Franco y Matías acordaron la propiedad vertical: gastos/pagos para
Franco y facturación/cobros para Matías.

La [especificación de I1](docs/specs/001-demostracion-gastos.md) define el recorrido
propuesto, sus hipótesis de demostración y las consultas pendientes. El reparto
inicial de componentes comunes requiere revisión breve con Matías. El uso
productivo se prevé para 2027, con terminación deseada durante 2026, según Franco.
H1–H4 siguen pendientes de validación con la operadora de Cooperadora; conservar
esta preparación en Git no las convierte en reglas definitivas ni inicia I1.

La base propuesta usa:

- Python 3.11;
- Django 5.2 LTS;
- PostgreSQL 17 para desarrollo local;
- pytest y Ruff;
- GitHub Actions para validación continua.

La interfaz se mantiene, por ahora, dentro de Django. Incorporar un framework de
frontend separado requiere una necesidad concreta y una decisión del equipo.

## Puesta en marcha local en Windows

Requisitos: Python 3.11 y Docker Desktop iniciado con el motor de contenedores
Linux disponible. Ejecutar desde la raíz de este repositorio. Crear el entorno
virtual sólo si todavía no existe.

```powershell
if (-not (Test-Path -LiteralPath .venv)) { py -3.11 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements/dev.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Revisar `.env` antes de continuar. Django carga exclusivamente el archivo `.env`
de la raíz del proyecto mediante `python-dotenv`; Docker Compose lo usa para
resolver su configuración. En ambos casos las variables del proceso tienen
prioridad. Para mantener la misma interpretación, usar valores literales simples
en este archivo. No se necesita `.env` cuando todas las variables se proporcionan
desde el proceso, como en CI.

```powershell
docker compose config --quiet
docker compose up -d --wait db
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

PostgreSQL se publica sólo en `127.0.0.1`; el puerto local se define con
`POSTGRES_PORT`. Si ese puerto está ocupado, elegir otro en `.env` antes de iniciar
el servicio. El volumen `postgres_data` conserva la base: modificar sus variables
de inicialización no cambia las credenciales de una base ya creada. No borrar el
volumen para resolver un problema de conexión sin revisar primero su contenido.

Los valores de ejemplo y la configuración con depuración son para desarrollo
local con datos sintéticos. Las condiciones de despliegue y uso real se
definirán con Sistemas antes de habilitarlos.

Para validar el proyecto:

```powershell
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

Al terminar, detener el servidor con `Ctrl+C` y PostgreSQL con
`docker compose stop db`. Esto conserva los datos del volumen.

El contrato de configuración sigue la documentación de
[python-dotenv](https://pypi.org/project/python-dotenv/) y la
[precedencia de Docker Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).

## Forma de trabajo

- El acuerdo de ramas, Issues y Pull Requests está en
  [`CONTRIBUTING.md`](CONTRIBUTING.md).
- Las decisiones técnicas se registran en [`docs/decisions`](docs/decisions).
- Las funcionalidades que lo justifiquen parten de una especificación breve en
  [`docs/specs`](docs/specs).

No se deben versionar credenciales, archivos `.env`, datos reales de la
Cooperadora ni documentos con información personal o financiera.
