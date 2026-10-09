# SPEC-004 — Presentación y revisión de solicitudes de facturación

- Estado: borrador; formulario inventariado, pendiente de validar campos y recorrido.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issues I2: [#20](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20)
  para validación y [#23](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/23)
  para el recorrido funcional.
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
- Trasladar al nuevo sistema la obligatoriedad del formulario Google sin validar
  las condiciones y excepciones de cada paso.

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

- El [relevamiento inicial](../planning/i2-issues/01-relevamiento-fuentes.md)
  identifica 16 preguntas marcadas como obligatorias en el formulario actual:
  13 en la primera página y tres en la sección de comprobante. Las condiciones
  de esa sección, las validaciones para el nuevo sistema, la facultad de
  observar/corregir y el mapa de estados se definirán con Cooperadora antes de
  pasar a `listo`.
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

- Datos visibles y marcados con `*` en el formulario actual: contacto,
  solicitante, destinatario fiscal, condición IVA, detalle, importe,
  producto/servicio, centro de costo, medio/cuenta, observaciones y, en la
  sección de comprobante, fecha, número de operación y archivo. Su necesidad
  por estado y validación en el nuevo sistema siguen abiertas. El trámite agrega
  identificador, presentador, fechas, estado e historial.
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

- ¿Se mantienen los campos obligatorios del formulario actual y cuándo se exige
  la sección de comprobante, especialmente si se respondió `No` o se indicó
  cuenta corriente aún no cobrada? ¿Qué formatos se validan?
- ¿Quién puede observar y corregir, cuántas rondas se permiten y qué historial
  queda visible?
- ¿Cuáles son los estados, motivos y plazos del recorrido real? Ver preguntas
  [P01-P10 y P15](../planning/i2-issues/01-consulta-cooperadora.md).

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Matías desarrolla el recorrido completo de solicitudes de facturación. | Los campos y reglas quedan en borrador hasta el relevamiento y la validación. |
| 2026-10-09 | Formulario de factura y primera entrevista | Registrar el inventario y separar el proceso actual de propuestas para el nuevo sistema. | La spec sigue en borrador; no se aprueban todavía obligatoriedades ni transiciones para el nuevo sistema. |
| 2026-10-09 | Formulario de factura actualizado por el usuario | Registrar las 16 marcas de obligatoriedad de la fuente. | P02 queda parcialmente respondida; las condiciones y validaciones para el nuevo sistema siguen sin confirmar. |
