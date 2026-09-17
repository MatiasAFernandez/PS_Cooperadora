# SPEC-005 — Registro de facturas y notas emitidas externamente

- Estado: borrador; pendiente de validar datos y procedencia.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: revisar vínculos con documentos y modelo compartido.
- Validador: personal de Cooperadora para tipos, datos y asociaciones.
- Plan: RF-002, M-E06 e I01/I03.

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

### No incluye

- Emitir, numerar, anular fiscalmente o enviar facturas/notas desde la aplicación.
- Integración directa con Exubio, ATP u otros sistemas externos.
- Definir todavía cómo una nota ajusta importes o cancelación.

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

- Los campos identificatorios y la unicidad de comprobantes deben validarse con
  Cooperadora antes de implementar.
- El registro refleja una operación externa; por sí solo no acredita un cobro.
- El efecto de notas de crédito/débito sobre importes y estados queda pendiente.

## Criterios de aceptación

1. Dada una solicitud existente y un comprobante externo válido, cuando un
   operador autorizado lo registra, entonces queda vinculado y visible en el detalle.
2. Dada una referencia o asociación inválida, cuando se intenta guardar, entonces
   no se crea un comprobante huérfano ni cambia el trámite.
3. Dado un usuario sin permiso sobre la solicitud, cuando solicita el comprobante
   o su archivo por URL directa, entonces se deniega el acceso.

## Datos, permisos y sensibilidad

- Datos requeridos: solicitud, tipo, referencia externa, procedencia y fecha;
  importes, numeración y datos fiscales exactos pendientes de relevamiento.
- Roles autorizados: personal que registre/verifique comprobantes y lectores del
  trámite según permisos validados.
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

- ¿Qué comprobantes y campos se toman de Exubio u otras fuentes?
- ¿Puede haber varias facturas o notas por solicitud? ¿Cómo se detectan duplicados?
- ¿Qué efecto tiene cada clase de nota sobre el importe a cobrar o la cancelación?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Registrar y vincular comprobantes emitidos externamente. | La aplicación no los emite; su modelo exacto se valida con Cooperadora. |
