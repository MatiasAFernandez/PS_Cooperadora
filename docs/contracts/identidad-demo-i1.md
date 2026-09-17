# Contrato de identidad y autorización — demo I1

Estado: propuesta técnica concreta para revisión; no implementada. Fecha: 17/09/2026.
Responsable del componente: Matías Alejandro Fernández. Consumidor de gastos:
Franco Damián Sánchez. Diseño preparado con asistencia de IA; no acredita revisión
de los alumnos ni validación de Cooperadora.

## Propósito y límite

Este contrato conecta [SPEC-002](../specs/002-matias-identidad-permisos.md) con
[SPEC-001](../specs/001-demostracion-gastos.md). Es una interfaz interna Python
en la aplicación Django existente, no una API HTTP entre servicios.

Define cómo gastos recibe quién actúa y comprueba permisos. H2 sigue siendo una
hipótesis de demo. La matriz de abajo sólo cubre las acciones de I1: no es el
catálogo completo de permisos del producto ni define cargos reales de Cooperadora.
La IA propone el diseño y las tareas; los alumnos revisan y comprenden el resultado.
Cooperadora valida autoridad y reglas operativas; Sistemas confirma la interfaz
institucional. No se les pide a las operadoras diseñar interfaces de programación.

## Decisiones técnicas para implementar después de la revisión

- Mantener Django, PostgreSQL, plantillas y el usuario Django existente. Referir
  usuarios mediante la configuración de usuario de Django, sin crear ahora otro
  modelo de usuario ni un proveedor externo de autenticación.
- Matías implementará un componente `identidad`; Franco, un componente `gastos`.
  Los nombres indican ubicaciones futuras, no aplicaciones ya creadas.
- Para la demo, usar vistas estándar de entrada/salida de Django con una plantilla
  mínima y cuentas sintéticas. No crear registro público ni recuperación propia
  de contraseñas. Django Admin sirve para preparación técnica, no para decidir gastos.
- Habilitar el adaptador y las rutas de acceso de demo sólo con una opción explícita
  `DEMO_IDENTITY_ENABLED`, desactivada por defecto. Desactivarlo debe impedir también
  resolver como actor una sesión local de demo ya existente. No depender sólo de DEBUG.
- No desarrollar ahora la conexión con la Facultad. Sin adaptador habilitado y
  confiable no hay actor autorizado. No aceptar identidad o capacidades indicadas
  por parámetros, formularios o cabeceras arbitrarias del navegador.

## Interfaz interna v1

Las siguientes firmas son una especificación, no código implementado.

| Operación | Entrada | Salida y garantía |
|---|---|---|
| `resolve_actor(request)` | Sesión verificada por el adaptador habilitado. | Actor activo o ausencia de actor. Cuenta inactiva, sesión ausente o adaptador deshabilitado producen ausencia. |
| Actor | Datos obtenidos del servidor. | `subject_id`: identificador local estable del usuario; `capabilities`: conjunto inmutable de códigos permitidos para esta petición. No incluye contraseñas, tokens, ni objetos de gasto. |
| `has_capability(actor, code)` | Actor y código conocido. | Booleano; actor ausente o código desconocido devuelve falso. No decide propiedad ni estado de solicitudes. |
| `visible_expenses(actor)` | Actor resuelto. | Consulta filtrada por gastos: todos, propios o ninguno según capacidades. No se filtra sólo en el navegador. |
| `can_decide_expense(actor, expense, action)` | Actor, solicitud y acción concreta: aceptar, postergar o rechazar. | Devuelve booleano; exige visibilidad, capacidad de decisión, solicitante distinto del actor y transición permitida por SPEC-001. Actor ausente o acción desconocida devuelve falso. Es una consulta sin efectos; el servicio vuelve a comprobar las condiciones al escribir. |

`subject_id` corresponde a la clave del usuario local usada para solicitante y
actor del historial. No usar nombre, correo ni unidad como identificador o permiso.
El futuro adaptador institucional deberá asociar la identidad externa verificada
con ese sujeto local sin cambiar la titularidad ni el historial. No se define aún
el mecanismo de asociación ni se asume que Sistemas entregue estos mismos campos.

El componente de identidad no importa modelos de gastos. Gastos consume el actor
y comprueba propiedad y estado; no analiza credenciales ni nombres de grupos.
Matías define resolución y capacidades; Franco define filtrado y acciones de gastos.
`visible_expenses` devuelve todas si existe `gastos.consultar_todas`; en su defecto,
sólo propias si existe `gastos.consultar_propias`; en otro caso, una consulta vacía.
El alcance global incluye las propias. Un actor sin capacidades no equivale a una
sesión ausente: puede estar autenticado y, aun así, no tener acceso a los trámites.

## Capacidades y datos de demostración

| Código interno | Efecto en gastos |
|---|---|
| `gastos.presentar` | Permite presentar una necesidad; el servidor asigna al actor como solicitante. |
| `gastos.consultar_propias` | Permite consultar solicitudes cuyo solicitante sea el actor. |
| `gastos.consultar_todas` | Permite consultar todas las solicitudes de gastos, sin habilitar su modificación. |
| `gastos.decidir` | Permite intentar una decisión sobre una solicitud visible; además debe respetar estado y versión. |

Para la demo, el adaptador traduce pertenencias a grupos Django mediante un mapa
explícito mantenido en servidor. No se desarrollará un editor de políticas ni un
motor genérico de roles. El módulo de gastos sólo conoce los códigos anteriores.

| Perfil sintético | Grupos de demo y capacidades |
|---|---|
| Solicitantes A y B | `demo_solicitante`: presentar y consultar propias. |
| Operadora O | `demo_operadora`: consultar todas y decidir. No presenta solicitudes en este recorrido. |
| Cuenta L para prueba de separación de permisos | `demo_lectura`: consultar todas, sin decidir. Es un caso de prueba, no un nuevo rol institucional. |
| Cuenta sin grupo, inactiva o sesión ausente | Sin autorización de negocio. |

Los grupos no reconocidos no otorgan capacidades. Los grupos conocidos suman sus
capacidades explícitas; la demo normal usa sólo los perfiles de la tabla. Cambios
de grupos se reflejan en la siguiente petición: no guardar capacidades permanentes
en la sesión. `is_staff` e `is_superuser` no agregan capacidades a este contrato.
No usar los atajos de permisos de superusuario como autorización de negocio.

Consultar todas y decidir son capacidades distintas. Decidir sin visibilidad
tampoco permite operar. Editar, eliminar, pagar, cargar documentos, delegar,
consultar por unidad o decidir gastos propios no forman parte del recorrido de
esta demo; requieren especificación y validación de sus casos antes de ampliarlo.
Para que sumar grupos no habilite accidentalmente ese último caso, la demo deniega
decidir una solicitud propia incluso con ambas capacidades. Es una restricción
provisional de H2, no una política institucional de aprobación de gastos propios.

## Respuestas y consistencia

- Sin actor: las pantallas de demo redirigen al acceso habilitado sin exponer datos.
  Con demo deshabilitada, el sistema deniega el acceso y no ofrece ese login.
- Actor válido sin capacidad para presentar: denegación 403, sin crear solicitud.
- Solicitud no visible: respuesta 404 igual que para identificador inexistente.
  Esto se aplica a detalle, historial y acciones dirigidas al objeto.
- Solicitud visible sin capacidad de decidir: denegación 403, sin cambios.
- Decisión sobre solicitud propia: denegación 403 en la demo, sin cambios.
- Presentar y decidir requieren POST con protección CSRF. GET sólo muestra las
  pantallas y nunca crea solicitudes ni registra decisiones. Una petición sin CSRF
  válido se rechaza antes de ejecutar las operaciones; no se promete otro código
  de error para esa petición aunque también tenga problemas de permisos.
- La versión esperada es obligatoria y debe ser un entero no negativo. Versión
  ausente/mal formada o acción desconocida: petición inválida 400, sin cambios.
  Para peticiones con sesión y CSRF válidos, comprobar primero visibilidad y
  autorización; después validar el contenido y la transición.
- Franco hará la escritura dentro de una transacción PostgreSQL: bloquear la fila,
  comprobar versión esperada y estado actual, validar la acción y guardar decisión,
  estado y nueva versión juntos. Versión inicial cero, incrementada en cada decisión.
  Versión desactualizada o transición inválida: conflicto 409 sin nuevos eventos.
- Motivo inválido: error de formulario, sin modificar estado, versión ni historial.
  Solicitante, autor de decisión, estado inicial y fechas se asignan en servidor.
  Campos manipulados por el cliente nunca sustituyen esos valores.

## Casos compartidos de aceptación

Son pruebas por implementar; no resultados ya obtenidos.

| ID | Caso | Resultado esperado | Autor principal de la prueba |
|---|---|---|---|
| CT-01 | Entrada con cuenta sintética válida; contraseña incorrecta, cuenta inactiva y salida. | Sólo la cuenta activa con acceso correcto produce actor; tras salir no accede. | Matías |
| CT-02 | Adaptador deshabilitado, identidad/roles enviados por cliente o código desconocido. | No se conceden capacidades por datos del cliente ni códigos desconocidos; una sesión de demo previa no evita el cierre del adaptador. | Matías |
| CT-03 | Cuenta staff/superusuario sin grupos de demo; cambio de grupo entre peticiones. | No hay permiso implícito; la resolución refleja altas y revocaciones explícitas. | Matías |
| CT-04 | A intenta consultar o decidir el gasto de B por lista, URL y petición directa. | No ve el gasto ni su historial y no lo modifica. | Franco |
| CT-05 | O consulta y decide; L sólo consulta; una cuenta combina grupos y pretende decidir su propio gasto; otra tiene decidir sin visibilidad. | O puede actuar según H3; los otros intentos se deniegan sin cambios. La suma de grupos no evita las condiciones por objeto. | Franco |
| CT-06 | A altera solicitante, estado o capacidades al presentar. | Se conservan identidad del servidor y estado inicial válido; no hay escalada. | Franco |
| CT-07 | Dos decisiones concurrentes sobre la misma versión; repetición posterior; versión inválida o acción desconocida; fallo al guardar el evento. | Sólo una decisión concurrente persiste; la repetida recibe conflicto. Contenido inválido no modifica nada; un fallo de persistencia revierte estado, versión y evento. | Franco |
| CT-08 | GET o POST sin CSRF válido al presentar y al decidir desde sesión autenticada. | No crea solicitudes ni decisiones. La prueba de CSRF debe habilitar su comprobación real. | Franco |

Ambos revisan la integración. Las pruebas del contrato no prueban SSO, cierre de
sesión institucional ni permisos reales; esos recorridos requieren el proveedor
y entorno institucionales.
El caso «decidir sin visibilidad» de CT-05 utiliza un actor construido en una
prueba unitaria de la política de gastos; no agrega otro grupo ni una cuenta
operativa a la demo. Los casos de sesión y asignaciones se prueban con el adaptador real.

## Consultas externas y cambios

Con Cooperadora: acciones por persona, visibilidad por persona/unidad, delegaciones,
separación entre revisión/aprobación/pago y eventual tratamiento de solicitudes
propias de un operador. No basta con la categoría general «Cooperadora».

Con Sistemas: mecanismo de entrega de identidad, identificador estable y su
garantía, ciclo de sesión y baja de usuarios, atributos confiables, entorno de prueba
y responsable de la adaptación final. No elegir OAuth, cabeceras o sesiones
compartidas suponiendo que ya existen. Esto no bloquea el adaptador de demo.

Cambiar un nombre o garantía de esta interfaz requiere actualizar ambos consumidores,
las pruebas CT afectadas y las tareas dependientes antes de integrar. Git conserva
versiones anteriores; este documento describe la propuesta vigente.

Referencias técnicas: [autenticación y grupos Django](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
y [usuario y permisos](https://docs.djangoproject.com/en/5.2/ref/contrib/auth/).
