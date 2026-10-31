# SPEC-016 — Preparación de identidad institucional

- Estado: Backlog: contrato de Sistemas pendiente.
- Issue: [#79](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/79).
- Responsable principal: Matías Alejandro Fernández.
- Rol del compañero: Franco Damián Sánchez revisa contratos compartidos y mantiene gastos/pagos.
- Validador: Cooperadora para operación; equipo/Sistemas para interfaces según el tramo.

## Problema y valor

Se ofrece un endpoint docente y se pide aislar el login para sustituir su origen, manteniendo usuarios locales para no docentes mientras se resuelve su cobertura (01:45–03:43).

## Alcance

### Incluye

Relevar el contrato ofrecido por Sistemas, documentar selección explícita del origen y preparar un límite de adaptación compatible con Actor/capacidades.

### No incluye

Implementar o activar SSO/integración de producción sin contrato; registro público; asignar permisos de negocio por autenticarse; fusionar actores automáticamente por correo.

## Requisitos verificables

- `IDP-R01`: acordar proveedor, sujeto estable, atributos, garantías de autenticación, errores y cobertura de docentes/no docentes.
- `IDP-R02`: los consumidores mantienen el contrato de actor y autorización por objeto; el cambio de origen no reasigna trámites históricos.
- `IDP-R03`: conservar el origen local de demo y documentar la convivencia/transición propuesta sin confundir cuentas sintéticas con identidad institucional.

## Reglas de negocio

La oferta verbal de API es evidencia de disponibilidad a relevar, no contrato ni acceso concedido. Correo de área compartido sirve para agrupación operativa, no para fusionar personas. No versionar credenciales ni respuestas reales.

## Criterios de aceptación

1. Sistemas confirma un contrato revisable o quedan bloqueos concretos con responsable.
2. Ejemplos sintéticos describen identidad válida/inválida, ausencia de atributos, no docente local y colisión entre orígenes.
3. Franco revisa compatibilidad del actor desde gastos y se documenta transición sin pérdida de titularidad.
4. La preparación no se presenta como login institucional implementado.

## Datos, permisos y sensibilidad

Acciones con capacidades explícitas y autorización por objeto en servidor. Datos sintéticos o anonimizados para pruebas; fuentes originales privadas. No copiar datos personales, credenciales, respuestas ni audio a GitHub.

## Módulos e interfaces

Matías: identidad; Sistemas/tutor técnico: proveedor y garantías; Franco: revisión del consumidor gastos. Reutiliza SPEC-002 y cierre técnico #21.

## Estrategia de prueba y evidencia

Revisión del contrato con casos sintéticos; pruebas de adaptador sólo cuando su contrato permita implementar. No consumir una API supuesta. La entrega debe enlazar SHA, revisión y resultados realmente ejecutados; esta especificación no acredita nuevas pruebas ni implementación.

## Preguntas abiertas

Proveedor y protocolo exactos; atributo de sujeto estable/correo; verificación de pertenencia; cuentas no docentes; disponibilidad y autorización de entorno de prueba.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-10-29 | Demo; síntesis en [acta](../evidence/demo-2026-10-29.md) | Necesidad y límites descritos arriba. Los detalles abiertos no se consideran acordados. | Seguimiento propio, sin reabrir entregas técnicas históricas por ampliación. |

Fuente: demo de Cooperadora del 29/10/2026, audio y dos transcripciones locales en `docs/fuentes/Demo/`. Matías confirmó el 31/10/2026 que el proyecto no cambió desde la demo: versión `09095a6d472bfcceeab21a4b371c7880f35e98c4`. Las transcripciones corresponden al mismo audio. No se publica el audio ni su contenido incidental. Registro operativo y síntesis de evidencia: #29.
