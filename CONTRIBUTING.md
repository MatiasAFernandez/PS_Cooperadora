# Acuerdo de trabajo propuesto

Este documento es una propuesta inicial para Franco y Matías. Las reglas que
afecten responsabilidades académicas, revisiones obligatorias o herramientas se
consideran acordadas recién cuando ambos las acepten.

## Flujo Git

Se propone GitHub Flow, sin una rama `develop` permanente:

1. Crear o seleccionar una Issue con un resultado verificable.
2. Abrir una rama corta desde `main` actualizada.
3. Implementar un cambio coherente con sus pruebas y documentación necesaria.
4. Abrir una Pull Request vinculada a la Issue.
5. Obtener checks verdes y revisión del compañero cuando el cambio sea
   sustantivo o afecte una interfaz compartida.
6. Integrar mediante *squash merge* y eliminar la rama remota.

Después del bootstrap inicial no se trabaja directamente sobre `main`.

## Nombres de ramas

Formato: `tipo/numero-descripcion-breve`.

- `feat/12-registrar-solicitud`
- `fix/27-validar-adjunto`
- `docs/8-aclarar-regla-pago`
- `test/31-integracion-estados`
- `chore/4-configurar-ci`

## Issues y división académica

Cada Issue debe indicar:

- resultado esperado y criterio de cierre;
- responsable principal: Franco o Matías;
- rol del compañero, si existe;
- dependencia o interfaz con otro módulo;
- evidencia que permitirá demostrar el trabajo;
- estimación de horas sólo cuando pueda fundamentarse.

La división debe realizarse por capacidades o módulos demostrables, no asignando
automáticamente todo el backend a una persona y todo el frontend a la otra.

## Especificaciones

Una especificación breve es obligatoria cuando el cambio introduce o altera una
capacidad del negocio, una regla relevante, un modelo de datos compartido o una
integración. Correcciones pequeñas, documentación y mantenimiento pueden partir
directamente de una Issue si el resultado es inequívoco.

La especificación describe el problema y el comportamiento verificable antes de
elegir detalles de implementación. Se usa la plantilla de
[`docs/specs/_template.md`](docs/specs/_template.md).

## Pull Requests

Las Pull Requests deben ser pequeñas y explicar:

- qué resultado producen;
- qué especificación o Issue satisfacen;
- quién realizó el trabajo principal y qué colaboración existió;
- cómo se probó;
- qué evidencia o captura resulta pertinente;
- qué queda fuera o pendiente.

No se aprueba una Pull Request generada por IA sólo porque compile. La revisión
debe comprobar el diff, las pruebas, la coherencia con la especificación y la
comprensión del integrante responsable.

## Datos y secretos

- No usar datos personales, financieros ni documentos reales en fixtures o
  pruebas.
- Utilizar datos sintéticos o anonimizados.
- No versionar `.env`, contraseñas, tokens ni respaldos de base de datos.
- Ante una duda sobre sensibilidad o autorización, detener la carga y consultar.
