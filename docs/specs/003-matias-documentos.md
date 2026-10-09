# SPEC-003 — Documentos protegidos de los trámites

- Estado: para validar; consistente con el Plan de Trabajo actual y pendiente de
  validación operativa con Cooperadora y de revisión de interfaz con Franco.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issues I2: [#19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19)
  para DOC-R01–R03, [#24](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/24)
  para DOC-R04 y [#28](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/28)
  para la integración I03.
- Rol de Franco: acordar tipos y momentos documentales del circuito de gastos y
  revisar la integración de acceso.
- Validadores: Cooperadora para documentos y política de archivos; Franco y Matías
  para el contrato común.
- Plan: RF-004, RNF-001, RNF-004, M-E04 e I03. RNF-002 se aplica como control
  transversal cuando una operación documental falla.

## Validación contra el Plan de Trabajo actual

El contraste documental con el Plan de Trabajo actual confirma que esta spec:

| Referencia | Cobertura en SPEC-003 | Resultado del contraste |
|---|---|---|
| RF-004 | Incorporar, clasificar, consultar y revisar documentos asociados a un trámite. | Alineada. DOC-R01 y DOC-R04 cubren asociación, clasificación y revisión. |
| RNF-001 | Autorizar en servidor la consulta, recuperación y demás operaciones sobre documentos. | Alineada. DOC-R03 exige denegación por identificador directo; las reglas extienden el control a cada operación. |
| RNF-004 | Rechazar archivos cuyo tipo o tamaño no cumpla la política definida. | Alineada. DOC-R02 exige rechazo sin documento utilizable. |
| M-E04 | Desarrollar almacenamiento, metadatos y acceso autorizado; rechazar archivos inválidos o no autorizados. | Alineada y apta para originar el primer tramo de trabajo. |
| I03 | Verificar asociaciones y recuperación autorizada en facturación/cobros y gastos. | Alineada, pero corresponde a una Issue de integración posterior y no al primer tramo de M-E04. |

El Plan separa M-E04, estimada allí en 20 horas, de I03, estimada en 8 horas.
Por eso una única Issue no debe declarar completas ambas actividades. La primera
Issue derivada de esta spec implementará el componente documental común; I03 se
registrará aparte cuando existan consumidores documentales en los dos circuitos.

## Problema y valor

Los respaldos hoy están dispersos y pueden ser sensibles. Ambos circuitos deben
incorporar, clasificar, consultar y revisar documentos ligados al trámite, con
acceso controlado y una referencia clara a su procedencia.

## Alcance

### Incluye

- Carga de archivos permitidos, metadatos de tipo y relación con el trámite.
- Consulta y recuperación de archivos a través de controles de autorización.
- Registro de la revisión documental y consulta de su resultado por usuarios
  autorizados, según las reglas validadas para cada circuito.
- Almacenamiento configurable para los archivos y persistencia de sus metadatos
  y relaciones en PostgreSQL.

### No incluye

- Publicar archivos mediante rutas estáticas abiertas.
- Aceptar automáticamente un documento por haberlo cargado.
- Definir aquí la deuda posterior a un pago ni el bloqueo de nuevas solicitudes.

## Requisitos verificables

- `DOC-R01`: cada documento se asocia a un trámite y conserva tipo y procedencia.
- `DOC-R02`: un archivo con tipo o tamaño fuera de la política acordada se rechaza
  sin crear un documento válido.
- `DOC-R03`: una persona sin permiso no puede recuperar el archivo ni consultar
  sus metadatos por un identificador directo.
- `DOC-R04`: una revisión deja trazabilidad del actor, resultado y fecha, conforme
  al contrato de historial compartido.

## Reglas de negocio

- La política de tipos, tamaño máximo, versiones y revisión queda pendiente de
  validación; los límites técnicos concretos se fijarán antes de implementar la carga.
- La autorización se comprueba en cada descarga y consulta, no sólo al mostrar
  enlaces en la interfaz. También se aplica en el servidor al incorporar, listar,
  consultar metadatos y registrar una revisión.
- Un pendiente documental sólo se considera satisfecho cuando se cumpla la regla
  de revisión validada para el circuito correspondiente.

## Criterios de aceptación

1. Dado un archivo permitido y un trámite accesible, cuando un usuario autorizado
   lo incorpora, entonces se conserva el archivo con tipo y vínculo al trámite.
2. Dado un archivo inválido, cuando se intenta cargarlo, entonces se rechaza sin
   dejar un documento utilizable ni cambios parciales.
3. Dado un usuario ajeno, cuando solicita directamente un archivo de otro trámite,
   entonces no recibe el contenido ni sus metadatos.
4. Dado un usuario sin capacidad documental suficiente, cuando intenta incorporar
   un archivo o registrar una revisión mediante una petición directa, entonces la
   operación se deniega y no deja cambios parciales.
5. Dado un documento revisado conforme a la regla del circuito, cuando se consulta
   su historial, entonces se identifican el resultado, el responsable y la fecha.

## Datos, permisos y sensibilidad

- Datos requeridos: vínculo al trámite, tipo, procedencia, referencia de archivo,
  autor y fecha; resultado de revisión cuando corresponda.
- Roles autorizados: quien aporte o revise según el circuito y permisos validados.
- Datos sintéticos o anonimizados para pruebas: archivos de ejemplo sin información
  personal ni financiera real.

## Módulos e interfaces

- Módulo propietario: componente documental común, a cargo de Matías.
- Entradas y salidas: trámite autorizado + archivo/metadatos → documento asociado;
  solicitud de recuperación → archivo o denegación.
- Dependencias: SPEC-002 para permisos y SPEC-009 para identificadores compartidos.
- Integración requerida: facturas/notas en SPEC-005, cobros en SPEC-006 y gastos de
  Franco en un incremento posterior a SPEC-001.

## Estrategia de prueba y evidencia

- Pruebas unitarias: validación de política de archivo y metadatos.
- Pruebas de integración: carga, revisión y descarga autorizada/denegada con
  almacenamiento de prueba y PostgreSQL.
- Demostración o evidencia: archivo ficticio asociado al trámite y recuperación
  permitida sólo desde una identidad autorizada.

## Primer tramo registrado en Issue #19

Este tramo se registró en [#19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19)
sin afirmar que toda SPEC-003 ni I03 están resueltas.

- Título propuesto: `M-E04 — Componente común de documentos protegidos`.
- Resultado: un usuario autorizado incorpora y recupera un archivo ficticio ligado
  a un trámite; se conservan sus metadatos en PostgreSQL y se rechazan archivos
  inválidos y operaciones no autorizadas.
- Requisitos cubiertos: tramo de RF-004 correspondiente a incorporación,
  clasificación y consulta; RNF-001, RNF-004; DOC-R01, DOC-R02 y DOC-R03. DOC-R04
  queda fuera de este primer tramo hasta validar la regla de revisión de cada circuito.
- Incluye: modelo y migración de metadatos; vínculo con un identificador de trámite;
  almacenamiento configurable; política explícita de tipo y tamaño; servicio de
  incorporación; consulta de metadatos; recuperación autorizada; manejo atómico de
  rechazos; pruebas con archivos sintéticos.
- No incluye: deuda documental, bloqueo o cierre; avisos; documentos reales;
  despliegue institucional; integración completa con facturas, cobros y gastos de
  I03; revisión documental de DOC-R04; definición de las reglas funcionales propias
  de cada circuito.
- Dependencias: contrato de identidad y capacidades de SPEC-002; identificador de
  trámite acordado con SPEC-009; política mínima de tipos y tamaños; capacidades
  necesarias para incorporar, consultar y recuperar documentos.
- Aceptación del tramo:
  1. un usuario autorizado incorpora un archivo permitido y quedan persistidos el
     archivo, su tipo, procedencia y vínculo con el trámite;
  2. un tipo o tamaño no permitido se rechaza sin archivo ni metadatos utilizables;
  3. un usuario ajeno no obtiene contenido ni metadatos aunque conozca la URL o el
     identificador directo;
  4. una incorporación no autorizada o un fallo de almacenamiento no deja cambios
     parciales ni presenta un documento como disponible.
- Pruebas y evidencia: pruebas unitarias de política y metadatos; pruebas con
  PostgreSQL para alta válida, rechazo por tipo/tamaño y fallo sin registro parcial;
  pruebas de acceso autorizado y denegado por URL o identificador directo; PR y
  salida de las verificaciones automáticas.
- Estado inicial propuesto: `Backlog`.
- Condición para pasar a `Ready`: resolver la política mínima de archivos, acordar
  las capacidades documentales y el identificador común de trámite, y confirmar
  que esas decisiones no cambiarán el modelo o los casos de aceptación del tramo.

## Preguntas abiertas

- ¿Qué tipos documentales y tamaños se permiten en cada circuito?
- ¿Quién puede aportar, reemplazar, revisar o rechazar documentos? ¿Se guardan
  versiones?
- ¿Qué criterios hacen que un documento satisfaga un pendiente?
- ¿Dónde se alojarán los archivos en el entorno institucional de prueba?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido | Documentos comunes con almacenamiento configurable y acceso controlado. | La política concreta y los tipos se validan antes de implementar. |
| 2026-10-05 | Plan de Trabajo actual, RF-004, RNF-001, RNF-004, M-E04 e I03 | La spec es consistente con el alcance académico; M-E04 e I03 se preparan como trabajos separados. | Puede crearse una Issue de Backlog para el componente común sin declarar completa la integración de ambos circuitos. |

