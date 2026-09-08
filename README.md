# PS Cooperadora

Sistema web para la gestión y el seguimiento de solicitudes de facturación,
gastos y pagos de la Asociación Cooperadora de la UTN Facultad Regional
Resistencia.

## Estado

Bootstrap técnico inicial. El alcance funcional, la división de módulos y las
decisiones que dependan del stakeholder o de la cátedra todavía deben validarse.

La base propuesta usa:

- Python 3.11;
- Django 5.2 LTS;
- PostgreSQL 17 para desarrollo local;
- pytest y Ruff;
- GitHub Actions para validación continua.

La interfaz se mantiene, por ahora, dentro de Django. Incorporar un framework de
frontend separado requiere una necesidad concreta y una decisión del equipo.

## Puesta en marcha local en Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements/dev.txt
Copy-Item .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py runserver
```

Para validar el proyecto:

```powershell
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

## Forma de trabajo

- El acuerdo de ramas, Issues y Pull Requests está en
  [`CONTRIBUTING.md`](CONTRIBUTING.md).
- Las decisiones técnicas se registran en [`docs/decisions`](docs/decisions).
- Las funcionalidades que lo justifiquen parten de una especificación breve en
  [`docs/specs`](docs/specs).

No se deben versionar credenciales, archivos `.env`, datos reales de la
Cooperadora ni documentos con información personal o financiera.
