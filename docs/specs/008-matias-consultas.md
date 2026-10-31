# SPEC-008 — Búsqueda, filtros y resúmenes de facturación y cobros

- Estado: filtros implementados en PR #71/#73; resúmenes pendientes de definición/implementación. Necesidad de métricas confirmada en la demo del 29/10/2026.
- Issue: [#30](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/30), fuente del estado operativo.
- Responsable principal: Matías Alejandro Fernández.
- Rol de Franco Damián Sánchez: acordar presentación/contratos y mantener consultas y productores de gastos.
- Validador: Cooperadora para métricas y permisos; equipo para cálculo e interfaces.
- Plan: RF-007, RNF-003 y M-E09; prioridad SHOULD sin reclasificación automática.

## Problema y valor

Encontrar solicitudes y resumir actividad e importes para administrar recursos.
La [demo](../evidence/demo-2026-10-29.md), 01:48:18–01:54:00, pide comparar períodos,
promedios y mayores solicitantes/grupos/centros. La necesidad está confirmada;
las fórmulas, población y fecha de corte todavía no están acordadas.

## Alcance

### Incluye

- Filtros combinados por fecha de presentación, estado/seguimiento y búsqueda,
  según [SPEC-012](012-mejoras-demo-consultas.md), ya implementados.
- Resúmenes de facturación por período y agrupación autorizados: volúmenes,
  importe promedio y mayores solicitantes/grupos conforme al diccionario acordado.
- Definición visible de población, fechas y concepto monetario de cada resultado.

### No incluye

- Consulta global para solicitantes sin facultades sobre esos datos.
- Sustituir contabilidad externa o consolidar automáticamente Xubio/bancos.
- Importación histórica y proyección: [SPEC-017](017-matias-historicos-proyecciones.md),
  issues #82/#83. No son bloqueos retroactivos de los resúmenes operativos.
- Un gráfico específico, exportación adicional o reclasificar SHOULD como MUST sin
  definir el alcance; la demo plantea gráficos como posible presentación.

## Requisitos verificables

- `CON-R01`: resultados y filtros sólo incluyen trámites autorizados.
- `CON-R02`: cada total/promedio se reconstruye desde su conjunto declarado.
- `CON-R03`: cálculo decimal exacto; presentar regla de promedio/redondeo acordada.
- `CON-R04`: parámetros manipulados no amplían el acceso.
- `CON-R05`: distinguir solicitado, facturado/neto e ingreso confirmado; no mezclar
  esos conceptos bajo una única etiqueta.
- `CON-R06`: una agrupación por correo compartido/área no identifica a una única
  persona ni modifica titularidad o permisos del trámite.

## Reglas de negocio

Moneda operativa ARS confirmada. Definir antes de implementar cada resumen:
período, fecha usada (presentación, emisión o ingreso), población, fórmula y
tratamiento de notas, anulaciones y parciales. Cobros pendientes no son ingresos
confirmados. No adoptar un promedio global mezclando solicitudes y comprobantes.

Cooperadora usa correo para agrupar por área porque pueden operar distintas
personas desde ese correo. Conservar actor estable por acción; no fusionar
correos sólo por parecido. La consulta estadística no amplía visibilidad ni
facultades de mantenimiento. Perfil administrativo en SPEC-014/#77.

## Criterios de aceptación

1. Los filtros vigentes mantienen fechas locales, combinación, errores y
   aislamiento A/B/O/L, incluso mediante parámetros directos.
2. Cada métrica tiene diccionario validado de población, fecha, fórmula y
   tratamiento de notas/parciales/anulaciones antes de pasar ese tramo a Ready.
3. Con datos sintéticos de varios períodos/grupos, el resultado coincide con
   cálculo manual y conserva centavos según la regla definida.
4. Un correo compartido se rotula como agrupación operativa y no reasigna
   solicitudes a otra persona.
5. Interfaz y guía declaran significado y límites; revisar la presentación
   compacta con #80 y compatibilidad de datos con #76.

## Datos, permisos y sensibilidad

Fecha/período, estado, grupo/centro, importes y referencias autorizadas. Roles:
titular sobre lo propio y operador/administrador según capacidades explícitas,
sin convertir lector global en editor. Dataset sintético con centavos, notas,
parciales, anulaciones y correos compartidos; sin planillas reales en Git.

## Módulos e interfaces

Matías mantiene consultas de facturación. Entrada: filtros y actor autorizado;
salida: registros y resumen definido. Dependencias SPEC-002/004/005/006/007,
permisos de SPEC-014 y cambios externos de SPEC-018 cuando se integren.
Franco define la medida y productor de gastos; no se impone una suma común de
gastos y cobros ni un mapa único de estados.

## Estrategia de prueba y evidencia

Conjunto sintético y cálculo manual contrastado; pruebas de filtros, períodos,
permisos, errores, agrupación y decimales en PostgreSQL. Revisión visual del
resumen. Registrar SHA y resultados ejecutados, sin atribuir a esta actualización
una nueva ejecución de pruebas de aplicación.

## Preguntas abiertas

- Fecha y población para cada métrica y cantidad de decimales del promedio.
- ¿Qué se cuenta como factura/solicitud para volumen y promedio?
- Tratamiento exacto de notas, anulaciones y parciales.
- Agrupación por centro, grupo y correo; permisos administrativos concretos.
- Prioridad y presentación de cada resumen en la próxima entrega.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo | RF-007 es SHOULD. | No cambiar prioridad por inferencia. |
| 2026-10-25/26 | PR #71/#73, SPEC-012 | Filtros y consulta por solicitud implementados. | No declarar resúmenes globales terminados. |
| 2026-10-29 | Demo, 01:48:18–01:54:00 | Métricas por período, promedio y mayores solicitantes. | Precisar diccionario y continuar #30; historia/proyección en #82/#83. |
