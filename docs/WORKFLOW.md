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

## Coordinación semanal

Una conversación breve entre Franco y Matías debería resolver:

- qué resultados pasan a `Ready`;
- quién es responsable principal de cada uno;
- qué interfaces necesitan acuerdo previo;
- qué bloqueos requieren a Marcos, al tutor técnico o a la cátedra;
- qué evidencia debe conservarse para las horas individuales.

## Integración entre módulos

Antes de implementar módulos que se conectan, registrar:

- datos de entrada y salida;
- responsabilidades de cada módulo;
- estados y errores compartidos;
- pruebas de contrato o integración;
- responsable de unir los cambios y rol del revisor.

La integración es una actividad verificable, no una cantidad genérica de horas.
