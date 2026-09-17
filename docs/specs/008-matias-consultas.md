# SPEC-008 — Búsqueda, filtros y resúmenes de facturación y cobros

- Estado: borrador; capacidad SHOULD, pendiente de priorización y validación.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: acordar filtros y presentación operativa que deban ser comunes.
- Validador: personal de Cooperadora para necesidades y definiciones de totales.
- Plan: RF-007, RNF-003 y M-E09.

## Problema y valor

La información dispersa dificulta localizar solicitudes y comprobar importes.
Una consulta operativa permitiría encontrar trámites de facturación y reconstruir
resúmenes de facturas y cobros desde sus registros.

## Alcance

### Incluye

- Búsqueda y filtros sobre trámites de facturación accesibles al usuario.
- Resúmenes de importes de facturas y cobros basados en registros incluidos en la
  consulta y con precisión decimal.
- Definición visible de los filtros y del conjunto usado para calcular cada total.

### No incluye

- Indicadores gráficos, cuadros de mando o exportaciones no validados.
- Consultas globales para solicitantes si no tienen permiso sobre todos los datos.
- Consolidación automática con Exubio o sistemas bancarios.

## Requisitos verificables

- `CON-R01`: los resultados contienen sólo trámites accesibles y respetan los
  filtros seleccionados.
- `CON-R02`: cada total puede reconstruirse a partir de los registros visibles o
  del conjunto autorizado declarado para el resumen.
- `CON-R03`: los importes se calculan sin pérdida de precisión decimal.
- `CON-R04`: un filtro o parámetro manipulado no amplía el alcance autorizado.

## Reglas de negocio

- Los filtros concretos, la definición de cada total y el tratamiento de notas,
  cobros parciales y cancelaciones requieren validación.
- RF-007 tiene prioridad SHOULD en el plan y se programa tras los recorridos MUST,
  salvo que Cooperadora justifique otra prioridad.
- Los resúmenes no sustituyen la contabilidad externa.

## Criterios de aceptación

1. Dado un conjunto ficticio con trámites de distintos solicitantes, cuando uno
   filtra sus solicitudes, entonces no aparecen trámites ajenos.
2. Dado un filtro acordado y registros de facturas/cobros, cuando un operador
   consulta un resumen, entonces los resultados y totales coinciden con esos
   registros y pueden recalcularse.
3. Dado un importe decimal con centavos, cuando se incluye en un total, entonces
   el valor esperado se conserva.

## Datos, permisos y sensibilidad

- Datos requeridos: atributos de búsqueda por acordar, estados, facturas, notas,
  cobros e importes autorizados.
- Roles autorizados: solicitante sobre sus trámites y personal de Cooperadora
  según permisos validados.
- Datos sintéticos o anonimizados para pruebas: casos con estados e importes
  variados, incluidos centavos y registros de distintos propietarios.

## Módulos e interfaces

- Módulo propietario: consultas de facturación, a cargo de Matías.
- Entradas y salidas: filtros y alcance autorizado → lista y resumen verificables.
- Dependencias: SPEC-002, SPEC-004 a SPEC-007.
- Integración requerida: presentación común con Franco si se aprueban consultas
  para ambos circuitos; no presupone un modelo único de importes.

## Estrategia de prueba y evidencia

- Pruebas unitarias: cálculo decimal y reglas de filtros una vez definidas.
- Pruebas de integración: alcance por identidad, combinaciones de filtros y
  reconstrucción de totales en PostgreSQL.
- Demostración o evidencia: tabla de registros sintéticos y cálculo manual
  contrastado con el resumen.

## Preguntas abiertas

- ¿Qué preguntas operativas necesitan responder los filtros y resúmenes?
- ¿Qué campos, períodos, estados y usuarios pueden consultarse?
- ¿Cómo se tratan notas, cobros parciales y cancelaciones en cada total?
- ¿RF-007 se mantiene como SHOULD para esta entrega?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | RF-007 figura como SHOULD y exige resultados filtrados y totales reconstruibles. | Se detalla después de validar las definiciones y el alcance autorizado. |
