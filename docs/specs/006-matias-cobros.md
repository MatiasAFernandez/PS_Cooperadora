# SPEC-006 — Registro de cobros y comprobantes de ingreso

- Estado: perfil provisional de demo precisado el 22/10/2026; validación
  institucional pendiente y separada del cierre técnico.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue I2: [#26](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/26).
- Rol de Franco: revisar precisión monetaria y vínculos documentales compartidos.
- Validador: personal de Cooperadora para datos, conciliación y asociaciones.
- Plan: RF-002, RNF-002, RNF-003, M-E07 e I03.

## Avance de #20 recibido el 15/10/2026

El [registro de decisiones](../planning/i2-issues/01-decisiones-recibidas.md)
comunica fecha, medio, número de operación, importe decimal, descuentos y
comprobante protegido. Se admiten varios cobros parciales de una solicitud y se
excluye imputar uno a varias solicitudes en I2. Un cobro aportado por el
solicitante queda pendiente de verificación de Cooperadora; no se cuenta como
ingreso confirmado por el mero alta. El perfil de demo acordado debajo precisa
moneda, anticipos, identidad y verificación; difiere explícitamente descuentos,
retenciones, comisiones y diferencias para otro corte validado.

## Problema y valor

Los cobros se realizan y verifican fuera de la aplicación. El trámite de
facturación debe mostrar el ingreso registrado, las facturas a las que corresponde
y su respaldo para reconstruir su situación sin conciliar archivos manualmente.

## Alcance

### Incluye

- Registro de un cobro externo con su procedencia y comprobante de ingreso.
- Asociación protegida con una solicitud y, por ella, con su factura única cuando
  exista. Se conservan anticipos sin inventar una factura ni duplicar imputaciones.
- Conservación de importes decimales y rechazo de operaciones parcialmente válidas.

### No incluye

- Ejecutar cobros bancarios o conciliar automáticamente extractos.
- Integración directa por API con bancos, Exubio o ATP.
- Imputar un cobro a solicitudes diferentes durante I2.
- Descuentos, retenciones, comisiones, conversión monetaria y corrección/anulación
  de cobros o verificaciones. No se cuentan importes no recibidos como ingresos.

## Requisitos verificables

- `COB-R01`: un cobro registrado conserva referencia externa, importe decimal,
  fecha, actor registrante y vínculo con la solicitud y su factura cuando exista.
- `COB-R02`: el comprobante de ingreso se vincula al cobro y sólo se recupera con
  permiso sobre el trámite correspondiente.
- `COB-R03`: una asociación inválida o un importe no permitido se rechaza sin
  dejar cobro, vínculo ni cambio de estado parcial.
- `COB-R04`: el detalle permite reconstruir qué cobros se relacionan con cada
  factura y sus importes registrados.

## Reglas de negocio

- Sólo ARS, importes positivos hasta 9999999999,99 con hasta dos decimales exactos.
  Se admiten varios parciales y anticipos antes de emitir la factura. Todos se
  relacionan con la factura única por la solicitud; ninguna FK se reasigna después.
- Identidad global: medio/cuenta de destino + número de operación obligatorio.
  Medios del perfil: Mercado Pago, BNA común, BNA UVT y NBCH. Cuenta corriente
  describe ausencia de cobro y no se admite como medio de ingreso. La referencia
  conserva mayúsculas, ceros y separadores; sólo se recortan espacios exteriores.
- Fecha e importe recibido son explícitos. El importe solicitado en el formulario
  inicial no se interpreta automáticamente como recibido.
- Respaldo PDF/JPEG/PNG hasta 10 MiB obligatorio: carga nueva o versión existente
  COMPROBANTE_COBRO del mismo trámite. Se puede reutilizar el respaldo inicial sin
  copiar bytes; una versión sólo respalda un cobro. El vínculo conserva esa versión
  aunque después sea reemplazada. Registrar no exige revisión documental previa.
  #27 agrega la actualización explícita del vínculo mediante un hecho auditado;
  conserva la FK original, importes y verificaciones. El cierre usa el vínculo
  actual y exige su aceptación vigente, según SPEC-007.
- Tanto solicitante como operador dan de alta ingresos PENDIENTES. Una capacidad
  independiente registra un único resultado CONFIRMADO o RECHAZADO; rechazo exige
  motivo con texto. Actor, fecha y resultado son inmutables. La capacidad no se
  deduce de poder registrar, revisar PDFs, leer, ser staff ni ser superusuario.
- La confirmación verifica el ingreso externo, no la conformidad del archivo.
  Totales pendientes, confirmados y rechazados se consultan por separado; sólo el
  confirmado es insumo de #27. El resultado del PDF no altera estos totales.
- Unicidad, pertenencia documental, importes y conservación del historial se
  protegen en PostgreSQL; el servicio controla permisos y compensa archivos nuevos
  tras rollback mediante la operación documental ya existente.
- El registro del cobro informa una operación externa; no mueve dinero.
- El estado de cancelación se determina conforme a SPEC-007, con reglas por acordar.

## Criterios de aceptación

1. Dada una solicitud con o sin factura y un cobro externo válido, cuando un actor
   autorizado lo informa, se conservan importe, procedencia, vínculo y respaldo,
   como pendiente. Una verificación explícita determina su inclusión en confirmados.
2. Dado un vínculo inexistente o un importe inválido, cuando se guarda el cobro,
   entonces la operación se rechaza sin cambios parciales.
3. Dado otro solicitante, cuando intenta consultar el cobro o descargar su
   comprobante por identificador directo, entonces se deniega el acceso.

## Datos, permisos y sensibilidad

- Datos requeridos: solicitud, medio/cuenta, operación, fecha, importe y respaldo;
  moneda ARS, procedencia del registro, actor y fecha se fijan en servidor.
- Informar exige acceso al trámite y `facturacion.informar_cobro` o
  `facturacion.registrar_cobro`. Archivo nuevo exige además `documentos.incorporar`;
  seleccionar respaldo existente exige metadatos. Verificar exige acceso y
  `facturacion.verificar_cobro`, asignada explícitamente. Consulta y descarga
  mantienen sus permisos por objeto; los importes y hechos se consultan en el detalle.
- Datos sintéticos o anonimizados para pruebas: importes y comprobantes ficticios.

## Módulos e interfaces

- Módulo propietario: facturación y cobros, a cargo de Matías.
- Entradas y salidas: operación externa informada → cobro pendiente y respaldo;
  verificación explícita → hecho confirmado/rechazado; consulta → importes y
  respaldo autorizado, sin modificar la solicitud.
- Dependencias: SPEC-002, SPEC-003 y SPEC-005.
- Integración requerida: SPEC-007 para cancelación; SPEC-009 para integridad.

## Estrategia de prueba y evidencia

- Pruebas unitarias: importes decimales, vínculos y reglas de imputación una vez
  validadas.
- Pruebas de integración: alta atómica, consulta autorizada/denegada y cálculo
  reproducible con datos ficticios.
- Demostración o evidencia: factura ficticia con cobro externo y comprobante
  asociado, más un caso de rechazo sin cambios parciales.

## Preguntas abiertas

- Validación institucional del perfil, correcciones/anulaciones, tratamiento de
  diferencias y descuentos/retenciones/comisiones antes de habilitar esos casos.
- #27 define cierre y cancelación. Un confirmado no cierra ni verifica el PDF.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Registrar cobros realizados externamente y asociarlos a facturas y comprobantes. | Las reglas de imputación y conciliación quedan pendientes de validación. |
| 2026-10-22 | Confirmación de Matías para #26 | ARS; parciales y anticipos por solicitud; unicidad medio/cuenta + operación; respaldo nuevo o existente; ingreso pendiente con verificación separada; ajustes diferidos. | Perfil provisional de demo, sin movimiento de dinero ni cierre automático. |
