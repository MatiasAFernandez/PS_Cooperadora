# SPEC-007 — Estados, historial, pendientes y cierre de facturación

- Estado: borrador; pendiente de validar transiciones y cierre.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: acordar contrato de eventos y presentación del historial común.
- Validador: personal de Cooperadora para decisiones, pendientes y cancelación.
- Plan: RF-002, RF-006, RNF-002 y M-E08.

## Problema y valor

Cooperadora y solicitantes necesitan conocer el estado vigente y reconstruir qué
ocurrió con cada solicitud de facturación. El cierre debe reflejar el tratamiento
de cancelación y documentación, sin perder observaciones ni operaciones previas.

## Alcance

### Incluye

- Estado actual y eventos de presentación, observación, corrección, registro de
  comprobantes/cobros, cancelación y cierre según el flujo validado.
- Visualización de pendientes y del historial después del cierre.
- Control de transiciones y consistencia de registros relacionados.

### No incluye

- Definir aquí la regla de deuda documental tras un pago de gastos (RF-005), que
  pertenece al circuito de Franco y requiere integración posterior.
- Cerrar automáticamente una solicitud al registrar una factura o un cobro sin
  una regla aprobada.
- Borrar o reescribir eventos históricos para corregir un trámite.

## Requisitos verificables

- `SEG-R01`: cada trámite muestra un estado actual coherente con sus eventos.
- `SEG-R02`: cada acción relevante conserva tipo, actor y fecha, incluso después
  del cierre.
- `SEG-R03`: una transición no permitida o repetida desde una vista obsoleta se
  rechaza sin aplicar cambios parciales ni duplicar eventos.
- `SEG-R04`: los pendientes y la cancelación son verificables desde facturas,
  notas, cobros y documentos asociados, conforme a reglas validadas.
- `SEG-R05`: sólo una persona con capacidad de cierre puede cerrar un trámite que
  satisface las condiciones acordadas.

## Reglas de negocio

- El mapa exacto de estados, cancelación, reapertura y condiciones de cierre
  requiere validación con Cooperadora.
- Una acción y su evento se guardan juntos o no se guardan.
- El historial conserva la secuencia de decisiones y operaciones sin permitir
  que un usuario ajeno lea el trámite.

## Criterios de aceptación

1. Dado un trámite con presentación, observación y corrección, cuando un usuario
   autorizado consulta el detalle, entonces ve el estado y los eventos con actor
   y fecha en orden.
2. Dado un intento de cerrar con un pendiente exigible, cuando se solicita el
   cierre, entonces se deniega y el estado e historial permanecen intactos.
3. Dada una acción enviada dos veces o desde un estado anterior, cuando llega la
   segunda petición, entonces no reemplaza la resolución ni duplica el evento.

## Datos, permisos y sensibilidad

- Datos requeridos: estado, eventos con tipo/actor/fecha, motivo cuando la regla
  lo exija, y pendientes derivados de datos asociados.
- Roles autorizados: lectores del trámite y operadores con capacidades concretas
  de observación, cancelación y cierre por validar.
- Datos sintéticos o anonimizados para pruebas: recorridos ficticios completos e
  incompletos, con intentos de transición inválida.

## Módulos e interfaces

- Módulo propietario: estados de facturación, a cargo de Matías; contrato de
  historial compartido acordado con Franco.
- Entradas y salidas: acción válida + estado vigente → nuevo estado y evento;
  consulta → estado, pendientes e historial.
- Dependencias: SPEC-004, SPEC-005, SPEC-006 y SPEC-002/003.
- Integración requerida: SPEC-009 para eventos y presentación común con gastos.

## Estrategia de prueba y evidencia

- Pruebas unitarias: transiciones y cálculo de pendientes una vez validados.
- Pruebas de integración: operaciones atómicas, petición repetida, permisos y
  persistencia del historial tras cierre.
- Demostración o evidencia: recorrido ficticio hasta cancelación/cierre y otro
  bloqueado por un pendiente.

## Preguntas abiertas

- ¿Cuáles son los estados y transiciones oficiales del circuito?
- ¿Qué significa cancelación: cobro total, decisión manual u otra condición?
- ¿Qué documentos y revisiones impiden cerrar? ¿Se puede reabrir y quién lo hace?
- ¿Qué motivos son obligatorios para observar, cancelar o cerrar?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Mantener estado e historial de cada trámite hasta después del cierre. | Se necesitan reglas de transición y cierre validadas antes de implementar. |
