# 0001 — Base técnica inicial

- Estado: propuesta
- Fecha: 2026-09-08
- Responsables de decisión: Franco y Matías, con consulta al tutor técnico

## Contexto

El tutor técnico indicó Django y PostgreSQL para facilitar compatibilidad con una
integración institucional futura. El alcance funcional y la división de módulos
todavía requieren validación, por lo que la base debe ser pequeña y reversible.

## Propuesta

- Python 3.11 como versión común inicial.
- Django 5.2 LTS, fijado en la última corrección disponible al preparar el
  bootstrap.
- PostgreSQL 17 para desarrollo y CI, pendiente de confirmar la versión del
  entorno institucional.
- Monolito Django modular como punto de partida.
- Plantillas Django para la primera interfaz; evaluar un frontend separado sólo
  ante una necesidad concreta que compense integración y mantenimiento.
- pytest, Ruff y GitHub Actions como controles mínimos.

## Motivos

- Django 5.2 es una versión LTS y soporta Python 3.11.
- Una única aplicación desplegable reduce coordinación prematura entre dos
  personas, sin impedir separar capacidades del negocio en módulos Django.
- Mantener la interfaz en el mismo proyecto evita comprometer una arquitectura de
  frontend antes de conocer interacciones y responsabilidades definitivas.

## Consecuencias

- Los módulos de negocio todavía no se crean ni se asignan.
- Cambiar la versión de PostgreSQL o incorporar un frontend separado exigirá una
  nueva decisión registrada.
- La configuración local usa Docker Compose sólo para PostgreSQL; Django se
  ejecuta en un entorno virtual de Python.

## Pendientes de validación

- Versión de Python y PostgreSQL usada o aceptada por la Facultad.
- Expectativas del tutor técnico sobre arquitectura, despliegue y frontend.
- Necesidades reales de interacción que podrían justificar HTMX u otro frontend.

## Referencias

- [Descargas oficiales de Django](https://www.djangoproject.com/download/)
- [Versiones de Python compatibles con Django](https://docs.djangoproject.com/en/5.2/faq/install/#what-python-version-can-i-use-with-django)
