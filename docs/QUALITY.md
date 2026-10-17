# Calidad de las entregas

Estado: propuesta de procedimiento compartido para revisar con el equipo, preparada
el 14/10/2026 a partir del criterio de calidad expresado por Franco. No define
reglas institucionales ni cambia por sí sola el alcance de las especificaciones.

## Objetivo

Entregar software seguro, usable y mantenible por otra persona. Las decisiones
deben tener fundamento y ser proporcionales al problema, al volumen esperado y al
equipo. Los patrones y las abstracciones se introducen cuando aportan una ventaja
concreta; no se agrega infraestructura para aparentar sofisticación.

## Criterios que se consideran en cada cambio

| Aspecto | Evidencia pertinente |
|---|---|
| Comportamiento | Casos esperados, errores y estados definidos; distinguir hechos, hipótesis y acuerdos. |
| Mantenibilidad | Responsabilidades claras, nombres comprensibles, dependencias justificadas y ausencia de duplicación que pueda divergir. Reglas de negocio separadas de HTTP y presentación. |
| Seguridad y datos | Autorización por actor, acción y objeto en servidor; consistencia y trazabilidad. Probar denegaciones y fallos con datos sintéticos cuando el cambio los afecte. |
| Experiencia de usuario | Acciones posibles según estado/permiso, mensajes claros sin duplicación, conservación de datos ingresados, navegación y resultado comprensibles. Etiquetas, teclado y errores accesibles cuando corresponda. |
| Rendimiento | Considerar consultas, carga de datos, paginación, bloqueos y concurrencia en los escenarios afectados. Medir problemas concretos antes de introducir optimizaciones complejas. |
| Evolución | Usar migraciones y contratos cuando sean necesarios; declarar límites. Escalar según necesidades verificables, sin diseñar una plataforma genérica por anticipación. |

La pertinencia depende del cambio. Una corrección de etiqueta no exige pruebas
de concurrencia; una escritura financiera no se aprueba sólo por verse bien.
Los checks verdes aportan evidencia, pero no prueban por sí solos usabilidad,
coherencia del alcance ni comprensión de las decisiones.

## Proporcionalidad y escenarios de fallo

En el plan o la PR existentes, indicar brevemente qué fallos relevantes cubre
el cambio y qué límites conserva. No crear otra plantilla o fase de aprobación.
Elegir la solución directa que satisfaga los criterios acordados y justificar
una capa adicional por el escenario que resuelve y su costo de mantenimiento.

Permisos, entradas inválidas, reenvíos, concurrencia y rollback se comprueban
cuando afectan el recorrido. Caídas abruptas del proceso, commits inciertos,
reconciliación de archivos y recuperación operativa no se agregan por defecto:
requieren una necesidad concreta dentro del alcance. Si esa garantía ya forma
parte de un contrato aceptado, cambiarla exige revisar ese contrato y sus
consumidores; una simplificación no autoriza debilitarlo unilateralmente.

Una transacción SQL no revierte archivos. Tampoco una validación de servicio
protege automáticamente escrituras por otras vías. Evaluar qué garantías cubren
servicios, constraints y triggers antes de agregar o retirar alguno. La repetición
de una comprobación en dos capas no demuestra por sí sola que sea innecesaria.

Al modificar vistas, reutilizar el layout, estilos y componentes compartidos
disponibles. Comprobar coherencia de navegación, formularios, mensajes y formato
visible con el otro circuito. Si falta una base común, delimitar el ajuste mínimo
o su tarea de integración, sin resolver cada pantalla como un diseño independiente
ni bloquear una entrega funcional por un rediseño general.

## Aplicación al flujo existente

**Plan:** señalar resultado, componentes afectados, decisiones relevantes,
interfaces, casos de prueba y límites. Presentar la opción recomendada y el
motivo; registrar acuerdos necesarios sin inventarlos. No repetir todo este
documento en cada plan.

**Implementación:** construir el alcance definido, mantener las garantías y
revisar el diff. Verificar los criterios afectados antes de entregar; no trasladar
errores conocidos al revisor. La interfaz se desarrolla con el comportamiento;
el pulido visual puede evolucionar progresivamente.

**Revisión:** comprobar criterios, código, integración y evidencia de la versión
entregada. Comunicar juntos los defectos materiales con escenario, impacto y
condición de corrección; separar sugerencias opcionales. No reimplementar el
producto, exigir preferencias personales ni abrir ciclos cosméticos indefinidos.
Una mejora opcional debe explicar su beneficio concreto; la conformidad sin
modificaciones también es un resultado válido. Al corregir, verificar el delta y
sus efectos pertinentes; ampliar la revisión sólo por riesgo o evidencia nuevos.

**Entrega:** explicar qué cambió, por qué, cómo se verificó y qué sigue pendiente.
La enseñanza o producción de tutoriales no es una obligación del implementador.
Las preferencias personales de acompañamiento se gestionan fuera de estas reglas.

## Deuda técnica y mejoras futuras

Cuando se difiera un problema técnico concreto, registrar en la Issue o PR:
ubicación, impacto, motivo de diferirlo y condición para resolverlo. Si afecta un
criterio material de aceptación, corregirlo antes de aprobar la entrega.

Una nueva funcionalidad solicitada no es automáticamente deuda técnica. Tampoco
una hipótesis de demo se convierte en política institucional por estar implementada.
Mantener ambos tipos de pendientes diferenciados para priorizar con fundamento.

## Uso por distintas herramientas

Cada integrante elige sus herramientas, modelos y forma de organizar el trabajo.
Estos criterios no exigen un orquestador, múltiples agentes ni un ejecutor
determinado. Los roles de implementación y revisión describen responsabilidades
del trabajo; no fijan una cantidad o tipo de agentes.

`AGENTS.md` dirige a este documento y a las fuentes de cada tarea. En el encargo
inicial a cualquier herramienta incluir: «Leé AGENTS.md, CONTRIBUTING.md,
docs/WORKFLOW.md y docs/QUALITY.md; después la Issue y sus specs/contratos.
Aplicá los criterios pertinentes al plan, implementación y revisión».

No asumir que todas las herramientas descubren instrucciones de la misma forma.
Quien inicie o delegue la tarea asegura la lectura; las fuentes comunes viven en Git,
sin duplicarlas en skills o configuraciones personales.
