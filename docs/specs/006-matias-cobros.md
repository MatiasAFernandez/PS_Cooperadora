# SPEC-006 — Registro de cobros y comprobantes de ingreso

- Estado: borrador; pendiente de validar el circuito de ingreso.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: revisar precisión monetaria y vínculos documentales compartidos.
- Validador: personal de Cooperadora para datos, conciliación y asociaciones.
- Plan: RF-002, RNF-002, RNF-003, M-E07 e I03.

## Problema y valor

Los cobros se realizan y verifican fuera de la aplicación. El trámite de
facturación debe mostrar el ingreso registrado, las facturas a las que corresponde
y su respaldo para reconstruir su situación sin conciliar archivos manualmente.

## Alcance

### Incluye

- Registro de un cobro externo con su procedencia y comprobante de ingreso.
- Asociación verificable del cobro con facturas registradas y consulta de esos
  vínculos por usuarios autorizados.
- Conservación de importes decimales y rechazo de operaciones parcialmente válidas.

### No incluye

- Ejecutar cobros bancarios o conciliar automáticamente extractos.
- Integración directa por API con bancos, Exubio o ATP.
- Presuponer pago total, parcial o reglas de imputación sin validación.

## Requisitos verificables

- `COB-R01`: un cobro registrado conserva referencia externa, importe decimal,
  fecha, actor registrante y vínculos con facturas existentes.
- `COB-R02`: el comprobante de ingreso se vincula al cobro y sólo se recupera con
  permiso sobre el trámite correspondiente.
- `COB-R03`: una asociación inválida o un importe no permitido se rechaza sin
  dejar cobro, vínculo ni cambio de estado parcial.
- `COB-R04`: el detalle permite reconstruir qué cobros se relacionan con cada
  factura y sus importes registrados.

## Reglas de negocio

- La moneda, campos externos, pagos parciales, múltiples facturas por cobro y
  ajustes quedan pendientes de validación.
- El registro del cobro informa una operación externa; no mueve dinero.
- El estado de cancelación se determina conforme a SPEC-007, con reglas por acordar.

## Criterios de aceptación

1. Dadas facturas registradas y un cobro externo válido, cuando un operador
   autorizado lo ingresa, entonces se conservan importe, procedencia, vínculos y
   comprobante de ingreso.
2. Dado un vínculo inexistente o un importe inválido, cuando se guarda el cobro,
   entonces la operación se rechaza sin cambios parciales.
3. Dado otro solicitante, cuando intenta consultar el cobro o descargar su
   comprobante por identificador directo, entonces se deniega el acceso.

## Datos, permisos y sensibilidad

- Datos requeridos: referencia externa, fecha, importe decimal, factura(s)
  asociada(s), registrante y comprobante; moneda y distribución por factura por
  validar.
- Roles autorizados: personal registrante/verificador y lectores del trámite
  según capacidades acordadas.
- Datos sintéticos o anonimizados para pruebas: importes y comprobantes ficticios.

## Módulos e interfaces

- Módulo propietario: facturación y cobros, a cargo de Matías.
- Entradas y salidas: operación externa verificada → cobro y asociaciones;
  consulta → importes y respaldo autorizado.
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

- ¿Qué identifica de forma única un cobro y qué respaldo exige Cooperadora?
- ¿Se admiten cobros parciales, anticipos o un cobro para varias facturas?
- ¿Qué moneda y tratamiento de ajustes, retenciones o diferencias corresponde?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Registrar cobros realizados externamente y asociarlos a facturas y comprobantes. | Las reglas de imputación y conciliación quedan pendientes de validación. |
