# SPEC-017 — Importación histórica y proyecciones de gestión

- Estado: Backlog: dos tramos con definiciones pendientes.
- Issue: [#82](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/82), [#83](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/83).
- Responsable principal: Matías Alejandro Fernández.
- Rol del compañero: Franco Damián Sánchez revisa contratos compartidos y mantiene gastos/pagos.
- Validador: Cooperadora para operación; equipo/Sistemas para interfaces según el tramo.

## Problema y valor

Cooperadora pide importar sus Excel históricos y estimar gastos de períodos futuros usando antecedentes e inflación (01:54:00–01:59:12).

## Alcance

### Incluye

Tramo H: especificar/importar una muestra histórica para análisis. Tramo P: definir y producir proyecciones identificadas como estimaciones. Son issues distintas con dependencias explícitas.

### No incluye

Datos reales en Git/pruebas; inventar solicitudes operativas o actores para filas históricas; conciliación bancaria; API de inflación o regresión obligatorias; garantía de predicción.

## Requisitos verificables

- `HIS-R01`: acordar columnas, origen, períodos, moneda, fechas, identificadores, duplicados y errores con una muestra sintética equivalente a los formularios.
- `HIS-R02`: el administrador conoce el resultado de importar y puede distinguir historia importada de trámites operativos; una repetición no duplica silenciosamente métricas.
- `HIS-R03`: agrupación por correo/área no modifica la titularidad ni fusiona personas; no agrupar direcciones sólo por parecido sin regla validada.
- `PRO-R01`: definir período base, medida de gasto/ingreso, índice y fórmula antes de calcular; permitir la alternativa manual solicitada si se acuerda.
- `PRO-R02`: presentar por separado dato real y proyección, con período base, ajuste aplicado, fecha y límites; datos insuficientes no producen cifras engañosas.

## Reglas de negocio

La reunión menciona historia desde 2018/2019 sin confirmar cobertura completa. Que las columnas provengan de formularios no resuelve por sí solo duplicados, fechas ni calidad. Importación histórica y RF-007 operativo son alcances distintos. La inflación externa y el método predictivo requieren definición; no se fija una fuente por inferencia.

## Criterios de aceptación

1. Una muestra sintética válida produce totales reconstruibles y queda diferenciada del circuito operativo.
2. Errores y reimportación tienen resultados definidos sin inflar estadísticas ni alterar solicitudes existentes.
3. Una proyección sobre datos sintéticos coincide con un cálculo manual y explicita base/ajuste; falta de datos informa el límite.
4. No se activa consumo externo ni se declara una fórmula aprobada mientras siga pendiente.

## Datos, permisos y sensibilidad

Acciones con capacidades explícitas y autorización por objeto en servidor. Datos sintéticos o anonimizados para pruebas; fuentes originales privadas. No copiar datos personales, credenciales, respuestas ni audio a GitHub.

## Módulos e interfaces

Matías: importación/analítica común propuesta y facturación; Franco valida significado y datos de gastos y mantiene su productor. Depende de definiciones de SPEC-008/#30 y de contrato histórico acordado.

## Estrategia de prueba y evidencia

Fixtures sintéticos con errores, duplicados y variantes de correo; totales decimales y permisos; comparación manual de proyección y casos sin datos. La entrega debe enlazar SHA, revisión y resultados realmente ejecutados; esta especificación no acredita nuevas pruebas ni implementación.

## Preguntas abiertas

Plantilla y cobertura reales; carga parcial o rechazo de lote; clave de duplicado; correcciones de importación; fecha de corte y medida de gasto; agrupaciones; fórmula/índice y prioridad académica.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-10-29 | Demo; síntesis en [acta](../evidence/demo-2026-10-29.md) | Necesidad y límites descritos arriba. Los detalles abiertos no se consideran acordados. | Seguimiento propio, sin reabrir entregas técnicas históricas por ampliación. |

Fuente: demo de Cooperadora del 29/10/2026, audio y dos transcripciones locales en `docs/fuentes/Demo/`. Matías confirmó el 31/10/2026 que el proyecto no cambió desde la demo: versión `09095a6d472bfcceeab21a4b371c7880f35e98c4`. Las transcripciones corresponden al mismo audio. No se publica el audio ni su contenido incidental. Registro operativo y síntesis de evidencia: #29.
