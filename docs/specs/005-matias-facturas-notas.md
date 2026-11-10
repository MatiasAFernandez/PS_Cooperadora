# SPEC-005 — Registro de facturas y notas emitidas externamente

## Actualización local — 10/11/2026

El registro de facturas/notas Xubio admite PDF opcional con la migración 0023.
Una referencia sin archivo no exige revisión documental ni bloquea por esa ausencia
el cierre/anulación. Un PDF aportado conserva sus controles. Otro origen, cobros
y gastos mantienen sus requisitos. Esta actualización sustituye las menciones
anteriores a PDF obligatorio para Xubio; la API sigue fuera del alcance. El envío declarado y el acuse voluntario
del titular se incorporan mediante 0024, sin requisitos nuevos de cierre. Ver [SPEC-018](../specs/018-matias-registro-externo-simplificado.md).


## Validación y alcance posterior al 29/10/2026

La [demo](../evidence/demo-2026-10-29.md) solicita evitar el archivo duplicado de Xubio y conservar referencias y trazabilidad de envío. [SPEC-018](018-matias-registro-externo-simplificado.md)/#76 define el cambio por validar/implementar junto con revisión y cierre de SPEC-007. Hasta integrarlo, PDF obligatorio y sus garantías describen el código demostrado. #84 investiga exportación disponible sin asumir JSON ni autorizar API.

La [preparación documental de Xubio](../guides/preparacion-xubio.md) del 10/11/2026
registra los encabezados CSV realmente disponibles y el mapeo candidato de la API.
El [contrato de referencias sin archivo](../contracts/referencias-xubio.md) es una
propuesta para #76, sin implementación ni cambio del requisito vigente de PDF.

> Ampliación aprobada por Matías el 25/10/2026: Xubio predeterminado y Otro con aclaración para los tres tipos; etiquetas documentales neutrales y códigos históricos conservados. Ver [SPEC-012](012-mejoras-demo-consultas.md).

El formulario de factura y notas ofrece la conformidad documental en la misma
carga a la operadora con permiso de revisar y consultar metadatos. La casilla
aparece marcada y puede desmarcarse para dejar el PDF pendiente. Cuando se confirma,
se guardan el PDF, el comprobante y el resultado documental **Aceptado** en una
sola operación. El historial atribuye la conformidad a quien registró el comprobante.

- Estado: perfil provisional de demo precisado; pendiente de validación institucional.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue I2: [#25](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/25).
- Rol de Franco: revisar vínculos con documentos y modelo compartido.
- Validador: personal de Cooperadora para tipos, datos y asociaciones.
- Plan: RF-002, M-E06 e I01/I03.

## Avance de #20 recibido el 15/10/2026

El [registro de decisiones](../planning/i2-issues/01-decisiones-recibidas.md)
comunica carga manual de facturas y notas de crédito/débito de Exubio con punto
de venta, número, fecha, importe y PDF protegido. El perfil de demo se precisa
con una factura y varias notas por solicitud y una identidad global por emisor,
tipo, letra, punto de venta y número. Registrar una factura no acredita un cobro.

## Problema y valor

Las facturas y notas se emiten fuera de la aplicación, pero el trámite necesita
mostrar qué comprobantes se emitieron y cómo se relacionan con la solicitud y sus
cobros. Registrar esa relación evita búsquedas manuales entre sistemas.

## Alcance

### Incluye

- Registro de referencias y datos verificados de facturas y notas emitidas fuera
  de la aplicación.
- Asociación de cada registro con su solicitud de facturación y, cuando corresponda,
  con el documento respaldatorio protegido.
- Consulta de las asociaciones por usuarios autorizados.
- Modificación de los datos transcritos y del PDF desde **Modificar
  comprobante externo**, para solicitudes abiertas y cuentas autorizadas.

### No incluye

- Emitir, numerar, anular fiscalmente o enviar facturas/notas desde la aplicación.
- Integración directa con Exubio, ATP u otros sistemas externos.
- Efectuar emisión o anulación fiscal de comprobantes externos.

## Requisitos verificables

- `COM-R01`: una factura o nota registrada conserva su tipo, procedencia externa y
  asociación con una solicitud existente.
- `COM-R02`: la asociación con un documento permite recuperar el respaldo sólo a
  usuarios autorizados.
- `COM-R03`: datos o asociaciones inválidas se rechazan sin dejar registros
  relacionados a medias.
- `COM-R04`: el detalle del trámite permite identificar los comprobantes vinculados
  y su historial de registro.

## Reglas de negocio

- Se admite una factura por solicitud y varias notas de crédito/débito. Cada
  nota se vincula automáticamente a la factura de la misma solicitud; no puede
  elegirse una factura ajena. El perfil técnico conserva emisor y letra de origen.
- La identidad global es CUIT del emisor + tipo + letra + punto de venta + número.
  El CUIT debe validar su dígito; letra A–Z, punto de venta 1–99999 y número
  1–99999999 son límites técnicos de demo, no validación fiscal externa.
- Fecha de emisión, importe positivo de hasta dos decimales (máximo
  9999999999,99) y PDF protegido hasta 10 MiB son obligatorios.
  El formulario de alta propone el importe de la solicitud y permite editarlo.
  Un formato no admitido se indica junto al campo de carga del PDF.
- Los datos históricos, el PDF, el actor y la fecha se conservan. Si cambia
  sólo el PDF, se registra el vínculo sucesor de SPEC-007 y se conserva el neto.
  Si cambian datos, se registra el motivo y una versión sucesora del mismo tipo
  con un PDF pendiente de revisión. Sólo las versiones vigentes integran el neto
  y el diagnóstico de cierre. Las notas siguen asociadas a la factura del
  trámite, y el emisor y la letra deben ser compatibles con las notas vigentes.
  Las verificaciones de cobro conservan su resultado.
- El registro refleja una operación externa; por sí solo no acredita un cobro.
- El neto informativo suma factura y débitos y resta créditos, sin conversión de
  moneda, verificación de ingreso ni transición de estado. Puede resultar cero
  o negativo; cierre/anulación corresponde a #27. La revisión del PDF es independiente.

## Criterios de aceptación

1. Dada una solicitud existente y un comprobante externo válido, cuando un
   operador autorizado lo registra, entonces queda vinculado y visible en el detalle.
2. Dada una referencia o asociación inválida, cuando se intenta guardar, entonces
   no se crea un comprobante huérfano ni cambia el trámite.
3. Dado un usuario sin permiso sobre la solicitud, cuando solicita el comprobante
   o su archivo por URL directa, entonces se deniega el acceso.

## Datos, permisos y sensibilidad

- Datos requeridos: solicitud, identidad global, fecha de emisión, importe y PDF;
  procedencia EXTERNO_XUBIO, actor y fecha de registro se fijan en servidor.
- Registrar exige acceso al trámite y capacidades
  `facturacion.registrar_factura_externa` y `documentos.incorporar`.
  La consulta respeta visibilidad del trámite; descargar exige su capacidad
  documental independiente, también por URL directa.
- Corregir datos exige los permisos de registro. Cambiar sólo el PDF exige
  los permisos de actualización documental definidos en SPEC-007.
- Datos sintéticos o anonimizados para pruebas: comprobantes ficticios sin números
  ni datos fiscales reales.

## Módulos e interfaces

- Módulo propietario: facturación, a cargo de Matías.
- Entradas y salidas: datos de comprobante externo → registro asociado a solicitud;
  consulta → comprobantes y respaldo autorizado.
- Dependencias: SPEC-004 para solicitud, SPEC-002 para permisos y SPEC-003 para archivo.
- Integración requerida: SPEC-006 para asociación con cobros y SPEC-009 para
  integridad compartida.

## Estrategia de prueba y evidencia

- Pruebas unitarias: validación de tipo, referencia y asociación.
- Pruebas de integración: registro, consulta, descarga protegida y rechazo atómico
  de vínculos inválidos.
- Demostración o evidencia: solicitud ficticia con factura y nota externas
  identificadas por procedencia.

## Preguntas abiertas

- ¿Qué transición produce una nota de crédito que deja el neto en cero?
- Validación institucional del perfil y las monedas.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Registrar y vincular comprobantes emitidos externamente. | La aplicación no los emite; su modelo exacto se valida con Cooperadora. |
| 2026-10-20 | Confirmación del responsable para #25 | Una factura por solicitud y varias notas; identidad global CUIT + tipo + letra + punto de venta + número, importe positivo de dos decimales y PDF. | Perfil provisional de demo; notas ligadas a la factura del trámite y neto informativo sin cierre automático. |
