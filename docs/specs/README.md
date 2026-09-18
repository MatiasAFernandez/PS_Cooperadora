# Especificaciones

El equipo acordó usar *spec-driven development*: definir el comportamiento
verificable antes de producir la implementación de una capacidad relevante.

No implica instalar automáticamente una herramienta ni generar documentación
extensa. La especificación debe ayudar a:

- validar valor y reglas con el stakeholder;
- separar módulos y responsabilidades individuales;
- convertir el alcance en Issues y pruebas;
- definir interfaces e integración antes de unir trabajo;
- conservar evidencia trazable sin duplicar el Plan de Trabajo.

## Ciclo de cada especificación

1. **Borrador:** problema, alcance y preguntas abiertas.
2. **Validación:** stakeholder, tutor o cátedra resuelven lo que corresponda.
3. **Plan:** módulos, interfaces, responsables, tareas y pruebas.
4. **Implementación:** Pull Requests vinculadas a la especificación.
5. **Convergencia:** comprobar código, pruebas y evidencia contra los criterios.

Se usa [`_template.md`](_template.md) como punto de partida. El equipo evaluará
más adelante si una herramienta como
[GitHub Spec Kit](https://github.com/github/spec-kit) aporta valor adicional.

## Autoría y trazabilidad

Cada especificación nueva identifica al responsable principal con su nombre completo
en el documento y en el nombre del archivo: `NNN-matias-<capacidad>.md` para
Matías Alejandro Fernández y `NNN-franco-<capacidad>.md` para Franco Damián
Sánchez. El número es único en este directorio. `001-demostracion-gastos.md` conserva
su nombre original y ya identifica a Franco como propietario en su encabezado.
Cuando una capacidad es compartida, el documento indica el aporte del compañero
y quién revisa el contrato; la autoría no convierte una regla pendiente en aprobada.

Las specs pueden tener un tramo de demo preparado y otros tramos todavía en
borrador. SPEC-002 concreta ahora su interfaz con SPEC-001 sin afirmar que estén
validados el proveedor institucional ni los permisos reales. Las demás specs de
Matías conservan sus pendientes. Las hipótesis explícitas permiten preparar una
demo acotada; no sustituyen la confirmación de las reglas de operación real.

La IA puede proponer arquitectura, contratos y tareas. Los alumnos revisan y
comprenden la solución; Cooperadora confirma reglas operativas y Sistemas describe
la interfaz institucional. Pruebas técnicas y devolución funcional son evidencias distintas.

| Spec | Capacidad | Referencia principal del plan |
|---|---|---|
| [002](002-matias-identidad-permisos.md) | Identidad recibida y permisos | RF-001, RNF-001, M-E03, I02 |
| [003](003-matias-documentos.md) | Documentos protegidos | RF-004, RNF-004, M-E04, I03 |
| [004](004-matias-solicitudes-facturacion.md) | Solicitudes de facturación | RF-002, M-E05 |
| [005](005-matias-facturas-notas.md) | Facturas y notas externas | RF-002, M-E06 |
| [006](006-matias-cobros.md) | Cobros y comprobantes | RF-002, M-E07 |
| [007](007-matias-seguimiento-cierre.md) | Estados, historial y cierre | RF-002, RF-006, M-E08 |
| [008](008-matias-consultas.md) | Filtros y resúmenes | RF-007, M-E09 |
| [009](009-matias-integracion-compartida.md) | Contratos e integración de módulos | I01-I05 |

## De las specs a las tareas

La secuencia inicial sugerida es acordar primero SPEC-002 con Franco para el
primer incremento de gastos; relevar y validar el recorrido de facturación de
SPEC-004; completar comprobantes, cobros, documentos y cierre con SPEC-005,
SPEC-006, SPEC-003 y SPEC-007; y abordar los resúmenes SHOULD de SPEC-008 después
de los recorridos principales. SPEC-009 acompaña cada interfaz compartida, no es
una integración única al final.

Se pueden registrar Issues en Backlog mientras una spec está en borrador. Para
pasar una tarea a Ready se requieren alcance suficiente, responsable, aceptación
verificable y dependencias resueltas para empezar; una hipótesis de demo debe quedar
identificada como tal. No se necesita cerrar todas las specs del sistema a la vez.
Las Issues indican requisitos y criterios cubiertos, dependencia, prueba y evidencia.
Un cambio de contrato entre módulos requiere una tarea de integración y revisión
cruzada explícita. Las tareas académicas de relevamiento, manuales, pruebas y
entrega se trazan al plan, aunque no todas necesitan una spec funcional propia.

El [paquete inicial de I1](../planning/i1-tareas.md) contiene siete tareas locales
para revisión, implementación futura, demostración y devolución operativa. Todavía
no son Issues publicadas. El [contrato v1](../contracts/identidad-demo-i1.md) evita
duplicar la interfaz en cada spec. Escribir o integrar documentación no inicia por
sí mismo la implementación de todo el backlog.

## Mantener una spec vigente

Actualizar o reemplazar el texto que dejó de aplicar; Git conserva el historial.
No acumular notas de conversaciones que obliguen a deducir qué decisión sigue vigente.
Mantener preguntas abiertas identificadas y conservar sólo la justificación útil
de decisiones relevantes. Un cambio de contrato exige revisar consumidores y pruebas.
