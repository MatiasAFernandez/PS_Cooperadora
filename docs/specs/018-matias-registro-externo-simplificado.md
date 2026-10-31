# SPEC-018 — Registro externo simplificado de facturación

- Estado: para validar detalles; cambio solicitado, sin implementar.
- Issue: [#76](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/76).
- Responsable principal: Matías Alejandro Fernández.
- Rol del compañero: Franco Damián Sánchez revisa contratos compartidos y mantiene gastos/pagos.
- Validador: Cooperadora para operación; equipo/Sistemas para interfaces según el tramo.

## Problema y valor

Cooperadora necesita rastrear la factura emitida en Xubio sin volver a cargar su archivo ni repetir controles del mismo operador (22:25–30:27).

## Alcance

### Incluye

Referencias externas, trazabilidad de envío y adaptación coherente de revisión y cierre. Mantener cobros únicos, anticipos y parciales.

### No incluye

Emisión fiscal, integración automática con Xubio, borrado de respaldos históricos, cierre automático y eliminación de verificación de ingresos.

## Requisitos verificables

- `EXT-R01`: registrar una referencia externa sin exigir duplicar el archivo de Xubio; conservar tipo, identificación, solicitud, actor y fechas acordadas.
- `EXT-R02`: distinguir emisión, registro y envío; permitir reconstruir qué comprobante se envió y a quién, sin afirmar que hubo envío por el mero registro.
- `EXT-R03`: adaptar los pendientes y el cierre para una referencia válida sin archivo; conservar revisión de respaldos efectivamente exigibles y verificación de cobros.
- `EXT-R04`: reducir operaciones repetidas del mismo agente sin atribuir una revisión independiente. Reutilizar la acción conjunta de cobros ya existente cuando corresponda.

## Reglas de negocio

La demo confirma el problema de la duplicación. La implementación vigente sigue exigiendo PDF de factura/notas y revisión al cierre hasta integrar este cambio. Los datos monetarios, unicidad, historial y autorización no se debilitan por omitir bytes. No extender la omisión a los comprobantes de cobro ni a gastos.

## Criterios de aceptación

1. Una referencia de Xubio válida puede registrarse sin archivo y permanece consultable con actor y fecha.
2. Un cierre no queda bloqueado sólo por faltar un archivo de Xubio expresamente dispensado; los cobros pendientes y documentos exigibles inválidos siguen bloqueándolo.
3. Referencias duplicadas, acceso ajeno o fallos no dejan registros parciales; los archivos y eventos anteriores se conservan.
4. Una declaración del operador que agrupa controles conserva sus hechos y autor; aportes de solicitantes siguen pendientes de control.

## Datos, permisos y sensibilidad

Acciones con capacidades explícitas y autorización por objeto en servidor. Datos sintéticos o anonimizados para pruebas; fuentes originales privadas. No copiar datos personales, credenciales, respuestas ni audio a GitHub.

## Módulos e interfaces

Facturación: Matías; contratos documentales y de cierre SPEC-003/005/006/007/009. Franco revisa efectos compartidos; su flujo de gastos no adopta esta dispensa.

## Estrategia de prueba y evidencia

Regresión de registro y cierre con/sin archivo; cobros pendientes; duplicados; permisos por objeto; migración preservando vínculos/versiones y atomicidad en PostgreSQL. La entrega debe enlazar SHA, revisión y resultados realmente ejecutados; esta especificación no acredita nuevas pruebas ni implementación.

## Preguntas abiertas

Datos mínimos definitivos; fecha y destinatario de envío; archivo opcional o sin carga en Xubio; tratamiento del origen Otro; cardinalidad de facturas y notas y reglas de anulación no confirmadas por la demo.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-10-29 | Demo; síntesis en [acta](../evidence/demo-2026-10-29.md) | Necesidad y límites descritos arriba. Los detalles abiertos no se consideran acordados. | Seguimiento propio, sin reabrir entregas técnicas históricas por ampliación. |

Fuente: demo de Cooperadora del 29/10/2026, audio y dos transcripciones locales en `docs/fuentes/Demo/`. Matías identificó el 31/10/2026 la versión demostrada: `09095a6d472bfcceeab21a4b371c7880f35e98c4`. Las transcripciones corresponden al mismo audio. No se publica el audio ni su contenido incidental. Registro operativo y síntesis de evidencia: #29.
