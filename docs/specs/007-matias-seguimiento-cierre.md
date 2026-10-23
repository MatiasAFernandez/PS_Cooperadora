# SPEC-007 — Estados, historial, pendientes y cierre de facturación

- Estado: perfil provisional de demo confirmado para #27; validación institucional
  separada. No incluye regularización de diferencias ni devolución de ingresos.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue I2: [#27](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/27).
- Rol de Franco: acordar contrato de eventos y presentación del historial común.
- Validador: personal de Cooperadora para decisiones, pendientes y cancelación.
- Plan: RF-002, RF-006, RNF-002 y M-E08.

## Avance de #20 recibido el 15/10/2026

El [registro de decisiones](../planning/i2-issues/01-decisiones-recibidas.md)
comunica estados `PRESENTADA`, `OBSERVADA`, `FACTURADA_PENDIENTE_COBRO`,
`COBRADA_EN_REVISION`, `CERRADA` y `ANULADA`, sin reapertura de estados
terminales. Para cerrar se exige factura, neto cubierto por cobros verificados o
nota de crédito total, y comprobantes de cobro aceptados. El perfil del
22/10/2026 precisa las condiciones técnicas descritas abajo. Las asignaciones
institucionales y retenciones/comisiones siguen pendientes. La resolución y su
evento se guardan juntos o no se guardan.

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
- Cerrar automáticamente una solicitud al registrar una factura o un cobro.
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

- Se aplica el perfil explícito descrito a continuación. Registrar una factura,
  cobro, revisión o nota nunca cierra ni anula automáticamente.
- Una acción y su evento se guardan juntos o no se guardan.
- El historial conserva la secuencia de decisiones y operaciones sin permitir
  que un usuario ajeno lea el trámite.

### Estado de solicitud y seguimiento financiero

PRESENTADA y OBSERVADA conservan el flujo de #23. Corregir una observación vuelve
a PRESENTADA. Mientras está PRESENTADA, el seguimiento se deriva de hechos:
sin factura, Presentada; con factura y cobertura insuficiente,
FACTURADA_PENDIENTE_COBRO; con neto no negativo cubierto,
COBRADA_EN_REVISION. Cerrar exige igualdad exacta aunque el seguimiento indique
cobertura por exceso. Neto negativo bloquea resolución y requiere regularización.

La lista y el detalle muestran el estado de solicitud y su seguimiento. Estos
intermedios se calculan al consultar; no se duplican columnas ni se escriben
transiciones durante GET, ni se inventan eventos o actores para datos históricos.
OBSERVADA conserva prioridad y bloquea el cierre normal hasta corregirse.

CERRADA y ANULADA son resoluciones persistidas, explícitas y terminales. No
admiten reapertura, cambios de datos, facturas/notas, cobros/verificaciones,
aportes/reemplazos, nuevas revisiones documentales ni cambios de respaldo. Se
conservan historial, metadatos y descargas según sus capacidades independientes.

### Cierre normal

- Factura registrada y neto estrictamente positivo en ARS.
- Cobros CONFIRMADOS exactamente iguales al neto, sin tolerancia ni redondeo
  adicional. Pendientes bloquean; rechazados no cuentan como ingreso.
- Respaldos vinculados de factura, todas sus notas y todos los cobros confirmados
  vigentes con última revisión ACEPTADO. Archivos históricos o sin relación con
  esos hechos no se convierten en requisitos adicionales.
- La operación bancaria/Mercado Pago declarada inicialmente debe registrarse como
  cobro con su medio/cuenta y operación y recibir verificación explícita. No se
  ignora la declaración ni se convierte automáticamente su importe en recibido.
- Descuentos, retenciones, comisiones y diferencias siguen fuera del perfil.

### Anulación

Se admite sin factura y sin ingresos pendientes/confirmados; o con factura cuyo
neto sea exactamente cero por notas, con todos sus respaldos vigentes aceptados
y sin ingresos pendientes/confirmados. La operación declarada inicialmente
también requiere resolución como cobro. Los rechazados quedan auditados.
Una nota de crédito no acredita devolución: si hubo ingreso confirmado, se
bloquea hasta definir regularización. Neto negativo no se anula ni se cierra.
La anulación del trámite no ejecuta una anulación fiscal en Xubio.

### Actualización trazable de respaldo

Los registros de #25/#26 y sus FK originales siguen inmutables. Una
ActualizacionRespaldo agrega un hecho con registro afectado, versión anterior,
versión nueva, actor, fecha y motivo. La versión nueva debe ser sucesora vigente
del mismo trámite, tipo y serie y no respaldar otro registro. El PDF continúa
siendo obligatorio para comprobantes externos. No se reescriben importes,
operaciones, verificaciones ni archivos anteriores.

El operador puede seleccionar una sucesora existente o subir el archivo y vincularlo
en una operación documental atómica. Una carga nueva exige incorporación; no
hereda aceptación. El diagnóstico exige la aceptación de la versión vinculada
actual. La declaración inicial conserva su historia; una corrección explícita con
archivo continúa la serie vigente si su versión compartida ya fue reemplazada.

### Permisos y concurrencia

Cerrar, anular y actualizar respaldo tienen capacidades explícitas separadas:
`facturacion.cerrar`, `facturacion.anular`, `facturacion.actualizar_respaldo`.
No se deducen de registrar comprobantes/cobros o revisar PDFs. El comando demo
asigna el grupo de resolución sólo a O cuando se usa `--resolucion-facturacion`;
sin la opción no amplía permisos ni revoca un grupo previamente asignado.
Resolver o actualizar requiere también metadatos y cada acción exige acceso al objeto.
Una cuenta sin metadatos consulta el diagnóstico financiero autorizado, pero no
recibe los motivos de actualizaciones, identificadores ni resultados documentales;
la sección documental se presenta neutral, sin inferir presencia o suficiencia.
Las tres acciones exigen motivo con texto de hasta 2000 caracteres.

La resolución recibe una huella de revisión calculada desde estado/versión,
comprobantes, cobros/verificaciones, aportes/revisiones y actualizaciones de vínculo.
Revalida bajo la cabecera bloqueada: cualquier cambio relevante invalida la pantalla
anterior (409). La huella controla frescura, no sustituye autorización.
Facturación toma cabecera antes de solicitud y raíces documentales. Revisión y
reemplazo de facturación toman la misma cabecera antes de la raíz; gastos/C01
mantienen su contrato y orden. SQL protege operaciones posteriores a terminales,
las condiciones de resolución, motivo y preservación del evento terminal.

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

- Validación institucional del perfil y de las personas/cargos facultados.
- Regularización de excesos, faltantes, devoluciones, retenciones y comisiones;
  quedan bloqueados los cierres/anulaciones que los requieren, sin inferir reglas.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Mantener estado e historial de cada trámite hasta después del cierre. | Se necesitan reglas de transición y cierre validadas antes de implementar. |
| 2026-10-22 | Confirmación de Matías para #27 | Cierre con igualdad exacta y respaldos aceptados; anulación restringida; capacidades explícitas, motivos y terminales sin reapertura; actualización documental trazable. | Perfil provisional de demo, sin regularización monetaria ni cambios en gastos. |
