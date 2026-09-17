# SPEC-002 — Identidad recibida y permisos internos

- Estado: tramo de demo concretado para revisión técnica; alcance institucional
  y de ambos circuitos todavía en borrador. No implementado. Actualizado: 17/09/2026.
- Autor y responsable principal: Matías Alejandro Fernández.
- Issue: pendiente de crear.
- Rol de Franco: revisar el contrato preparado con asistencia de IA y comprobar
  su consumo y acceso por solicitud en gastos/pagos.
- Validadores: Franco y Matías para el contrato; Cooperadora para capacidades y
  pertenencia; tutor técnico/Sistemas para la identidad institucional.
- Plan: RF-001, RNF-001, M-E03 e I02.

## Problema y valor

Los dos circuitos necesitan reconocer a un usuario autorizado y limitar sus
operaciones y trámites. Separar la identidad recibida de los permisos de negocio
permite probar los recorridos con cuentas sintéticas y adaptar más adelante el
origen institucional de la identidad.

## Alcance

### Tramo que se prepara para I1

Usar el [contrato de identidad de demo](../contracts/identidad-demo-i1.md) como
definición única de entradas, salidas, capacidades y errores. La IA propone la
interfaz; los alumnos revisan sus garantías y la implementación. No se exige que
inventen por separado qué debe entregar cada módulo.

Matías implementará después de la revisión un adaptador local con cuentas
sintéticas, sesión Django y capacidades explícitas. Franco consumirá el actor y
aplicará propiedad/estado en gastos. Staff o superusuario no implican autoridad
de negocio. La selección del origen de identidad será explícita y la demo quedará
desactivada por defecto; no se construye un login definitivo del producto.

Las tareas [T01, T02 y T06](../planning/i1-tareas.md) cubren revisión, componente
común e integración con gastos. Comprobar ID-R04 en facturación y acceso a archivos
queda para sus incrementos. Completar el tramo de I1 no completa toda SPEC-002.

### Incluye

- Contrato interno que entrega una identidad válida y capacidades de negocio a
  los módulos de gastos y facturación.
- Denegación de acceso sin identidad válida y controles en servidor para listas,
  detalle, acciones y archivos.
- Adaptador con identidades ficticias para desarrollo y demostración.

### No incluye

- Crear un sistema de autenticación institucional ni integrarlo en producción.
- Registro público de cuentas o inferir permisos de negocio del acceso a Django Admin.
- Definir sin Cooperadora qué personas pueden operar cada etapa.

## Requisitos verificables

- `ID-R01`: sin identidad válida, una solicitud a una función protegida se deniega.
- `ID-R02`: un solicitante no ve ni modifica un trámite ajeno mediante listas,
  identificadores directos o peticiones a acciones.
- `ID-R03`: sólo una capacidad explícita habilita cada acción de Cooperadora; el
  control se aplica también en el servidor.
- `ID-R04`: gastos y facturación consumen el mismo contrato interno de identidad y
  autorización, con pruebas de acceso permitido y denegado.

## Reglas de negocio

- La identidad autenticada y las capacidades de negocio son conceptos separados.
- La pertenencia a una unidad no concede por sí sola acceso a todos sus trámites;
  cualquier excepción requiere validación funcional.
- Los códigos y asignaciones sintéticas de I1 están propuestos en el contrato.
  El alcance real por persona/unidad, las delegaciones y la matriz completa de
  permisos siguen pendientes de validación; la visibilidad propia/global es sólo
  una parte de la autorización del producto.

## Criterios de aceptación

1. Dada una identidad sintética solicitante A, cuando consulta el trámite de B por
   lista o URL directa, entonces no obtiene sus datos.
2. Dada una cuenta sin capacidad de decisión, cuando envía directamente una
   acción reservada a Cooperadora, entonces no cambia el trámite.
3. Dada una sesión ausente o inválida, cuando solicita un recurso protegido,
   entonces la operación se deniega.

Para I1, completar también CT-01–CT-08 del contrato en las tareas asignadas.
La cuenta de consulta global sin permiso de decisión verifica que ambas capacidades
son independientes. Estos casos comprueban el adaptador sintético y su consumo,
no la autenticación institucional ni toda la futura configuración de permisos.

## Datos, permisos y sensibilidad

- Datos requeridos: identificador estable de identidad y capacidades; otros
  atributos, incluida la unidad, se acuerdan en la validación.
- Roles autorizados: solicitantes y personal de Cooperadora según capacidades
  explícitas todavía por definir.
- Datos sintéticos o anonimizados para pruebas: al menos dos solicitantes con
  trámites distintos y una cuenta operadora ficticia.

## Módulos e interfaces

- Módulo propietario: componente común de identidad y autorización, a cargo de Matías.
- Entradas y salidas: identidad recibida → sujeto y capacidades utilizables por
  vistas y servicios internos; operación no autorizada → denegación.
- Dependencias: revisión técnica de la interfaz v1 en T01; para I1 se conecta
  sólo gastos. No esperar la implementación de facturación para probar el adaptador.
- Integración requerida: SPEC-001 de Franco y SPEC-004 a SPEC-009; prueba cruzada I02.

## Estrategia de prueba y evidencia

- Pruebas unitarias: resolución de capacidades y denegaciones.
- Pruebas de integración: peticiones a ambos circuitos con identidades distintas,
  URL directa y acciones sin permiso.
- Demostración o evidencia: matriz de acceso acordada y casos permitidos/denegados.

## Preguntas abiertas

- ¿Qué atributos y garantía ofrecerá la identidad institucional? ¿Quién adaptará
  ese origen a la aplicación?
- ¿Qué capacidades y delegaciones existen en Cooperadora? ¿El acceso se define por
  persona, unidad o ambos?
- ¿Qué operaciones podrán realizar solicitantes y personal en cada circuito?

## Decisiones

El cuerpo mantiene la definición vigente. Esta tabla conserva sólo decisiones que
explican el diseño; no reemplaza el historial de Git ni acredita aprobación externa.

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido y SPEC-001 | Separar identidad recibida y permisos de negocio; usar identidades sintéticas en la demo. | Se especifica un contrato interno antes de conectar ambos módulos; la identidad institucional sigue pendiente. |
| 2026-09-17 | Preparación técnica autorizada por Franco, con asistencia de IA | Proponer el contrato v1 y limitar el primer consumidor a gastos. | Revisión conjunta sobre una solución concreta; permisos operativos e integración institucional siguen pendientes. |
