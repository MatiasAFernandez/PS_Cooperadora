# SPEC-004 — Presentación y revisión de solicitudes de facturación

- Estado: borrador; pendiente de relevar formularios y validar el recorrido.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: revisar navegación compartida y contrato de historial y acceso.
- Validador: personal de Cooperadora para campos, actores y observaciones.
- Plan: RF-002, M-E01, M-E02 y M-E05.

## Problema y valor

El formulario actual y las comunicaciones posteriores no brindan una vista única
de la solicitud. Un solicitante debe poder presentarla y seguirla; Cooperadora
debe poder revisarla, observarla y recibir una corrección trazable.

## Alcance

### Incluye

- Presentación, consulta y detalle de una solicitud de facturación.
- Observación por personal autorizado y corrección por quien tenga permiso.
- Estado visible y trazabilidad de presentación, observación y corrección.
- Pantallas propias del recorrido; Django Admin sólo para tareas técnicas.

### No incluye

- Emitir facturas o notas desde el sistema; su registro se trata en SPEC-005.
- Registrar cobros, cancelación o cierre; se tratan en SPEC-006 y SPEC-007.
- Fijar campos del formulario sin relevar el formulario y ejemplos actuales.

## Requisitos verificables

- `FAC-R01`: una solicitud válida se crea con identidad presentadora y fecha
  asignadas por el servidor; una inválida no genera trámite.
- `FAC-R02`: el solicitante autorizado consulta estado y detalle de sus solicitudes
  sin acceder a las ajenas.
- `FAC-R03`: sólo personal autorizado registra una observación; la corrección
  conserva la observación previa y el actor de cada acción.
- `FAC-R04`: una acción enviada desde un estado incompatible se rechaza sin
  sobrescribir información vigente.

## Reglas de negocio

- Los datos obligatorios, la facultad de observar/corregir y el mapa de estados
  se definirán con Cooperadora antes de pasar a `listo`.
- Una corrección no borra el historial de lo presentado ni la observación.
- La protección de acceso se aplica a listas, detalle y acciones del servidor.

## Criterios de aceptación

1. Dado un formulario válido y una identidad autorizada, cuando se presenta,
   entonces aparece una solicitud consultable con su estado e historial inicial.
2. Dada una solicitud propia observada, cuando se corrige conforme a la regla
   validada, entonces se ve la nueva información y la observación anterior.
3. Dada una identidad ajena o sin facultad de observar, cuando intenta actuar
   mediante una petición directa, entonces no altera la solicitud.

## Datos, permisos y sensibilidad

- Datos requeridos: campos del formulario por relevar, identificador de solicitud,
  presentador, fechas, estado y observaciones.
- Roles autorizados: solicitante y personal de Cooperadora con capacidades de
  presentación, revisión o corrección por validar.
- Datos sintéticos o anonimizados para pruebas: dos solicitantes, solicitudes y
  observaciones ficticias.

## Módulos e interfaces

- Módulo propietario: facturación, a cargo de Matías.
- Entradas y salidas: formulario de solicitud → trámite; observación/corrección →
  estado y evento consultables.
- Dependencias: SPEC-002 y contrato de historial de SPEC-007/009.
- Integración requerida: navegación común de Franco y documentos de SPEC-003.

## Estrategia de prueba y evidencia

- Pruebas unitarias: validación de datos y acciones permitidas por estado.
- Pruebas de integración: presentación, observación, corrección, acceso ajeno y
  petición desde estado desactualizado.
- Demostración o evidencia: recorrido solicitante → Cooperadora → solicitante con
  información sintética y devolución registrada.

## Preguntas abiertas

- ¿Cuáles son los campos y documentos del formulario actual, y cuáles son
  obligatorios?
- ¿Quién puede observar y corregir? ¿Cuántas rondas de corrección se permiten?
- ¿Cuáles son los estados, motivos y plazos del recorrido real?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Matías desarrolla el recorrido completo de solicitudes de facturación. | Los campos y reglas quedan en borrador hasta el relevamiento y la validación. |
