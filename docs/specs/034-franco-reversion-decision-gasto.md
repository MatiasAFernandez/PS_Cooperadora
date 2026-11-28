# SPEC-034 — Reversión de decisiones de Gastos

Hipótesis de demo pendiente de validación operativa con Cooperadora.
Responsable principal · Franco Damián Sánchez (Gastos).
Antecedente técnico [#6](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/6).

## Resultado

Una operadora puede corregir una decisión registrada por error y devolver la
solicitud a evaluación. El detalle ofrece **Revertir decisión** en un bloque
colapsado. La operadora debe ingresar el motivo y confirmar el cambio a
**Presentada**. La bandeja vuelve a mostrar la solicitud como pendiente de
decisión.

## Reglas

- La acción exige `gastos.decidir` y visibilidad sobre una solicitud cuyo
  titular sea otra persona. Puede revertir una decisión de otra operadora.
- Se admite desde **Aceptada** o **Rechazada**. Un `PagoExterno` registrado o
  un `CierreGasto` bloquean la acción.
- `POST /gastos/<pk>/decidir/` recibe `action=revertir`, la versión esperada
  y un motivo obligatorio. El servidor valida CSRF, visibilidad y permiso.
  Con la fila de la solicitud bloqueada, vuelve a evaluar estado, pago,
  cierre y versión. Un dato inválido devuelve 400 y un conflicto devuelve
  409. El detalle conserva el motivo ingresado para revisar el error.
- El estado, la versión incrementada y una nueva `DecisionGasto` quedan
  guardados en la misma transacción. La decisión original conserva su
  registro. El historial identifica **Decisión revertida** con actor,
  fecha, motivo y estados. El motivo es visible a quienes consultan la
  solicitud, incluido su titular y el perfil de lectura global.
- La comunicación de la reversión se realiza en el detalle y el historial.
  El productor y la recuperación de avisos de [SPEC-030](030-franco-avisos-decision-gastos.md)
  excluyen este evento.

## Aceptación

- Revertir una solicitud aceptada sin pago y una rechazada. Comprobar la
  entrada de historial y la posibilidad de decidir otra vez.
- Comprobar permiso, motivo, CSRF, versión, reenvíos y bloqueos por pago y
  cierre. En PostgreSQL, dos reversiones concurrentes registran una sola.
  Una reversión y un alta de pago en carrera sólo pueden confirmar una
  operación sobre la aceptación vigente.
- Verificar el panel inicial, su error y el historial a 1280×800 y 390×844
  simulado. Comprobar el formulario móvil con JavaScript desactivado.
