# Flujo de coordinación

## Tablero mínimo

Se propone un único tablero con estos estados:

1. `Backlog`: necesidad registrada, todavía no lista.
2. `Ready`: alcance y criterio de aceptación suficientes.
3. `En curso`: existe un responsable y trabajo activo.
4. `Revisión`: Pull Request abierta o validación pendiente.
5. `Terminado`: integrado y verificado con evidencia.

El tablero no reemplaza las Issues ni el Plan de Trabajo académico. Su función es
mostrar el estado técnico actual sin duplicar descripciones extensas.

La herramienta propuesta es GitHub Issues con un GitHub Project compartido. Este
documento no crea el tablero ni publica tareas. El [paquete de I1](planning/i1-tareas.md)
prepara sus primeras tarjetas y las dependencias. Tras publicarlas, el estado se
actualiza en el tablero; las specs mantienen comportamiento y aceptación.

Una tarea documental puede estar Ready para revisión sin habilitar implementación.
Una tarea de demo puede usar hipótesis explícitas sin convertirlas en reglas reales.
La terminación técnica y la validación con Cooperadora se siguen por separado:
T06 demuestra técnicamente el recorrido y T07 registra la devolución operativa
en el paquete local. Si hay un bloqueo, registrar causa y responsable.

## Fuentes y actualización documental

| Fuente | Contenido |
|---|---|
| Issues/PR/Project | Estado operativo, responsables, próximos pasos y dependencias. |
| Specs y contratos | Comportamiento, aceptación, interfaces y garantías vigentes. |
| Planificación | Desglose y secuencia del trabajo, con enlaces al seguimiento operativo. |
| Guías y evidencia | Uso reproducible; versión, comprobaciones, resultados y límites de cada corte. |

Antes de proponer una PR, contrastar el cambio con sus documentos afectados y
corregir contradicciones. Tras integrar, actualizar el estado confirmado en su
fuente; no copiar el historial de PR ni el backlog completo en cada documento.
La evidencia histórica conserva su versión y resultado, sin presentarse como
estado actual. Un agente con foco documental se justifica si hay varias fuentes
o contratos afectados; un cambio menor puede comprobarlo el revisor existente.

Redactar actividades, decisiones y resultados con fuentes pertinentes, sin
juicios personales, conversaciones privadas ni descargos repetidos ajenos al
propósito del documento. Registrar la contribución de cada responsable y el
alcance concreto de una comprobación pendiente.

## Coordinación entre integrantes

Resolver por Issues, contratos y PR los resultados listos, responsables,
interfaces, bloqueos y evidencia necesaria. Proponer una conversación cuando
resuelva una decisión o ambigüedad concreta; no exigir disponibilidad simultánea
o reuniones periódicas para avanzar.

## Integración entre módulos

Antes de implementar módulos que se conectan, registrar:

- datos de entrada y salida;
- responsabilidades de cada módulo;
- estados y errores compartidos;
- pruebas de contrato o integración;
- responsable de unir los cambios y rol del revisor.

La integración es una actividad verificable, no una cantidad genérica de horas.
