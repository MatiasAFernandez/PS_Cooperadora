# SPEC-001 — I1: presentación y decisión de un gasto

- Estado: paquete técnico de demo preparado para revisión; no implementado ni
  validado por Cooperadora. Actualizado: 17/09/2026.
- Issue: pendiente; no se creó una Issue remota.
- Propietario: Franco, módulo vertical de gastos/pagos.
- Aporte de Matías: componente de identidad sintética y capacidades; revisión
  de integridad e integración común.
- Validadores: equipo para el contrato técnico; operadora de Cooperadora para
  validar las hipótesis de demo, con Marcos para las reglas institucionales.
- Resultado: una demostración local con datos ficticios, sin uso productivo.

## Problema y valor

Permitir que un solicitante presente una necesidad de gasto y conozca la decisión
humana de Cooperadora y el siguiente respaldo requerido. La demostración permite
validar el recorrido antes de registrar pagos o recibir documentos reales.

## Fuentes y grado de certeza

- **Entrevista:** `01_TRANSCRIPCION_ENTREVISTA.md`, líneas 85–126: necesidad de gasto
  previa, aceptación, rechazo y postergación; líneas 127–150: solicitudes propias
  y documentación pendiente. Fuente conservada en el proyecto académico,
  `temp/paquete_astra/`; no se copia al repositorio técnico.
- **Revisión humana en la tarea de planificación:** ambos alumnos aceptaron la
  división vertical; I1 será una demostración de gastos. Según Franco, Cooperadora
  prevé uso desde 2027 y desea terminación durante 2026.
- **Responsabilidades actuales:** Franco desarrolla gastos; Matías aporta
  identidad/permisos conforme a SPEC-002. La IA concreta la interfaz y las tareas;
  ambos revisan su comprensión, coherencia y posterior implementación.
- **H1–H4, hipótesis de demostración:** decisiones acotadas descritas abajo. No
  constituyen políticas aprobadas de Cooperadora.
- **Límite vigente:** se prepara el diseño técnico y las tareas. No se autoriza
  iniciar I1 ni se considera validada la matriz real de permisos. El ejemplo de
  solicitudes propias/globales no es el conjunto completo de permisos del producto.

Este cuerpo describe el estado vigente; Git conserva versiones anteriores. El
[contrato de demo](../contracts/identidad-demo-i1.md) define una única interfaz
compartida y el [paquete de tareas](../planning/i1-tareas.md) organiza su ejecución futura.

## Alcance

Incluye un adaptador de identidad con cuentas ficticias para la demostración,
presentación, consulta, decisión humana, historial de decisiones y visualización
de documentación por aportar.

Las cuentas locales no constituyen un login propio definitivo. La aplicación
prevé recibir identidad institucional; el formato de esa identidad y la
responsabilidad de la adaptación final siguen pendientes con tutor/Sistemas.

No incluye ejecución o registro de pagos, carga/descarga de archivos, cierre
documental, bloqueo de nuevas solicitudes, correcciones y reaperturas, correo,
facturación/cobros ni integración institucional. No se simulará un pago para
generar deuda de factura definitiva.

## Datos, permisos e hipótesis de demostración

| Hipótesis | Regla provisional para la demo | Validación pendiente |
|---|---|---|
| H1. Datos mínimos | Concepto obligatorio, importe estimado único positivo en ARS y unidad de prueba. Identificador, solicitante y fecha se asignan en el servidor. | La operadora valida campos reales, unidades y necesidad de rangos. |
| H2. Acceso | Dos solicitantes ficticios ven sólo sus trámites. Una cuenta con capacidad de decidir gastos consulta ambos y decide. No se habilita registro público. | Matías revisa el contrato; la operadora valida personas, capacidades y pertenencia por persona/unidad. |
| H3. Decisión | Aceptar, postergar o rechazar. Motivo obligatorio en postergación/rechazo; opcional en aceptación. Se conserva actor, fecha y resolución. | La operadora valida decisiones y política de motivos. |
| H4. Pendiente | Tras aceptar, mostrar «Respaldo del gasto (presupuesto o factura): por aportar». En otras etapas: «No se solicita documentación en esta etapa de la demostración». | La operadora valida documento y momento. No equivale a deuda posterior a un pago. |

Importes, nombres, unidades y cuentas serán sintéticos. La pertenencia a una unidad
no concede por sí sola acceso a solicitudes ajenas. Tener acceso al administrador
de Django no concede automáticamente la capacidad de decidir gastos.
Como restricción provisional de la demo, el contrato deniega decidir solicitudes
propias aunque se combinen grupos. No se presume que ésa sea la política real:
el tratamiento de operadores que también solicitan queda pendiente de validación.

## Reglas de estado

La tabla y los criterios de aceptación siguientes concretan H1–H4 exclusivamente
para la demo. Su especificación o aprobación técnica no valida reglas reales.

| Estado actual | Acción autorizada | Estado resultante |
|---|---|---|
| Sin solicitud | Presentar | Presentada |
| Presentada | Aceptar / postergar / rechazar | Aceptada / postergada / rechazada |
| Postergada | Aceptar / rechazar | Aceptada / rechazada |

Aceptada y rechazada no tienen nuevas transiciones en I1. Aceptada significa
autorización dentro del ejemplo, no pago, reserva presupuestaria ni cierre.
Las transiciones no listadas se rechazan también en el servidor.

## Requisitos verificables y aceptación

| ID | Requisito | Ejemplo de aceptación |
|---|---|---|
| I1-R01 | Presentar una necesidad de gasto. | Con concepto, importe positivo y unidad de prueba se crea una solicitud presentada, atribuida a la sesión; datos inválidos no generan trámite. |
| I1-R02 | Consultar solicitudes propias. | A ve el estado y detalle de sus trámites; B no accede a ellos por lista ni identificador directo. Sin sesión no se accede. |
| I1-R03 | Registrar la decisión humana autorizada. | La cuenta decisora acepta, posterga o rechaza según la tabla; un solicitante no puede hacerlo mediante una petición directa. |
| I1-R04 | Conservar las decisiones del trámite. | Una postergación y una aceptación posterior quedan visibles con responsable, fecha y motivos correspondientes. |
| I1-R05 | Mostrar la documentación por aportar. | Al aceptar aparece el pendiente H4; no se ofrecen carga de archivo, marca manual de cumplimiento ni cierre. |
| I1-R06 | Respetar el estado vigente al decidir. | Una acción desde un estado no permitido o una decisión repetida desde una pantalla desactualizada no sobrescribe la resolución ni agrega otro evento. |

La interfaz ofrece listados y detalle propios de gastos. El administrador queda
para preparar las cuentas de prueba; no sustituye el recorrido de la demo.

## Módulos e interfaces

| Componente | Responsable principal propuesto | Integración verificable |
|---|---|---|
| Gastos, decisiones, estados y pantallas | Franco, propiedad acordada | Presentación → decisión → consulta e historial. |
| Repositorio, entorno, CI y navegación común | Franco | Matías comprueba instalación y coherencia con su futuro módulo. |
| Contrato de identidad recibida y permisos internos | Matías | Para I1, provee identidad y capacidades mediante el adaptador ficticio; Franco valida acceso por solicitud y decisiones de gasto. |
| Documentos y descarga autorizada | Matías | Diferido: I1 expone un requisito pendiente, no un archivo ni su conformidad. |
| Contratos | Franco: ejemplos y recorrido; Matías: estructura e integridad | Acordar identidad, permisos y eventos antes de implementar sus dependencias. |

Los contratos son internos a una aplicación Django. No requieren una API HTTP,
servicios separados ni anticipar la estructura completa de facturación.
Gastos consume `resolve_actor` y capacidades; conserva el filtrado por solicitante,
las transiciones y la escritura atómica con versión descritos en el contrato.
Consultar todas las solicitudes no concede automáticamente permiso para decidir.

## Estrategia de prueba y evidencia

- Pruebas funcionales con PostgreSQL para I1-R01 a I1-R06, incluidas denegaciones
  por identidad/objeto y transiciones inválidas. Las pruebas de base técnica y
  configuración no acreditan estos requisitos.
- Demo: presentar A → postergar con motivo → aceptar → consultar pendiente;
  presentar otra → rechazar; intentar acceso con B y decisión sin permiso.
- Cada Issue/PR enlazará los requisitos que cubre, autor, revisor y resultado.
  La devolución de la operadora y las confirmaciones de Marcos se registrarán
  separadas de las pruebas técnicas.
- Cada alumno registrará tiempo real y evidencia; este documento no asigna horas
  ejecutadas ni fechas de aprobación. Las 200 horas son un mínimo individual,
  según la confirmación de Franco.

## Preguntas abiertas y condición de inicio

| Pendiente | Cuándo se necesita | Efecto |
|---|---|---|
| Revisar el paquete técnico y el contrato propuesto por la IA | T01, antes de implementar dependencias | Los alumnos revisan la solución concreta; no necesitan diseñar por separado sus interfaces ni dar H1–H4 por validadas. |
| La operadora valida H1–H4; las reglas institucionales se confirman con Marcos | En la validación del incremento; antes de consolidar reglas reales | Puede cambiar la demo. Si contradice el recorrido principal, revisar la especificación antes de continuar. |
| Reglas de pagos, cierre, deuda documental y bloqueo | Antes de sus incrementos | No bloquean I1. |
| Fechas, evidencia y condiciones académicas | Consulta paralela a cátedra | No se inventan fechas ni acreditaciones; no bloquea preparar esta especificación. |
| Alojamiento e identidad institucional | Antes de despliegue o integración institucional | No bloquean la demostración local ni la publicación del repositorio. |

La preparación será revisable mediante T01. Las tareas podrán pasar a Ready para
implementación cuando se resuelvan sus dependencias técnicas y se autorice ejecutar
ese trabajo, manteniendo H1–H4 como hipótesis explícitas. No requieren aprobación
institucional de esas hipótesis para construir la demo. I1 estará implementado
cuando complete pruebas y revisión cruzada; la devolución de Cooperadora se registra
aparte en T07. Ninguno de esos hitos se declara cumplido por escribir esta spec.
