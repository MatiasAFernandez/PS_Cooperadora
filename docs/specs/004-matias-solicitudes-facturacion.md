# SPEC-004 — Presentación y revisión de solicitudes de facturación

- Estado: decisiones condicionales y de acceso recibidas; faltan campos,
  transiciones y trazabilidad de la validación.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issues I2: [#20](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20)
  para validación y [#23](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/23)
  para el recorrido funcional.
- Rol de Franco: revisar navegación compartida y contrato de historial y acceso.
- Validador: personal de Cooperadora para campos, actores y observaciones.
- Plan: RF-002, M-E01, M-E02 y M-E05.

## Avance de #20 recibido el 15/10/2026

Según el [registro de decisiones](../planning/i2-issues/01-decisiones-recibidas.md),
fecha, número de operación y archivo son obligatorios al declarar un pago ya
presentado por banco o Mercado Pago; quedan opcionales si no se presentó o se
elige cuenta corriente. Se comunicaron CUIT de 11 dígitos con verificador,
importe positivo de dos decimales y validación del correo destinatario. El
solicitante consulta sólo sus trámites y corrige los observados. Un pago
declarado en el alta sólo crea información preliminar pendiente de verificación.
Falta confirmar si las otras 13 preguntas del formulario actual conservan su
obligatoriedad, los catálogos y las transiciones de observación, corrección y
rechazo.

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
  identifica 13 preguntas marcadas como obligatorias en la primera página del
  formulario actual. Fecha, número de operación y archivo de la sección de
  comprobante no llevan `*`. Para I2, los tres campos son obligatorios cuando
  se declara un pago ya presentado por banco o Mercado Pago. Falta confirmar
  qué exigencias se conservan para las otras 13 preguntas y completar las
  transiciones y facultades de observación/corrección.
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

- Datos visibles y marcados con `*` en la primera página del formulario actual:
  correo del presentador, respuesta sobre comprobante presentado, solicitante,
  CUIT y nombre del destinatario, condición IVA, correo de envío, detalle,
  importe, producto/servicio, centro de costo, medio/cuenta y observaciones.
  Fecha, número de operación y archivo de la
  sección de comprobante son visibles pero no llevan `*`. Su necesidad por
  estado y validación en el nuevo sistema siguen abiertas. El trámite agrega
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

- ¿Se mantienen las 13 exigencias del formulario actual y qué catálogos se usan?
- ¿Cuántas rondas de observación/corrección se permiten y qué motivo se exige?
- ¿Qué transiciones, motivos y plazos completan los estados base? Ver preguntas
  [P01-P10 y P15](../planning/i2-issues/01-consulta-cooperadora.md).

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Matías desarrolla el recorrido completo de solicitudes de facturación. | Los campos y reglas quedan en borrador hasta el relevamiento y la validación. |
| 2026-10-09 | Formulario de factura y primera entrevista | Registrar el inventario y separar el proceso actual de propuestas para el nuevo sistema. | La spec sigue en borrador; no se aprueban todavía obligatoriedades ni transiciones para el nuevo sistema. |
| 2026-10-09 | Corrección del formulario de factura por el usuario | Registrar 13 marcas de obligatoriedad en la primera página y ninguna en los tres campos de comprobante. | P02 queda parcialmente respondida; las condiciones y validaciones para el nuevo sistema siguen sin confirmar. |
