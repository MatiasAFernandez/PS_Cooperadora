# Plan consolidado de implementación — #21 y #23

Fecha: 16/10/2026. Responsable: Matías Alejandro Fernández.
Base técnica contrastada: `main` en `d65beda83e2bc056800c87778224c7fe23d06287`.

Este documento fija el plan técnico del alcance de Matías. Sustituye, para este
trabajo, las alternativas e instrucciones contradictorias de los documentos
locales `#21-#23.md` y `actualización.md`. No acredita implementación, pruebas
nuevas, aprobación de Franco ni validación institucional adicional.

## 1. Fuentes, alcance y decisiones

Fuentes de comportamiento: cuerpos de las issues #21/#23; SPEC-002/004;
decisiones D01–D05 registradas para #20; contrato de identidad I1; contrato
`docs/contracts/i2-tramites-provider-matias.md`; código integrado por #19/#22.
El formulario relevado es fuente de campos y opciones, no aprobación automática
de nuevas restricciones operativas.

### Se implementa

- Extensión compatible de identidad para el correo de presentación.
- Preparación explícita de cuentas sintéticas de facturación.
- Presentación, listado, detalle, observación y corrección de solicitudes.
- Validación en servidor, propiedad, capacidades, CSRF e historial inmutable.
- Respaldo declarado en el alta y su conservación/reemplazo durante corrección.
- Control de doble presentación, conflictos y compensación documental.

### Se conserva sin ampliar

- El pago declarado es información preliminar pendiente de verificación. #23 no
  crea un cobro contable confirmado ni cambia saldos o acredita cancelación.
- Facturas/notas, cobros formales, revisión documental, anulación y cierre
  funcional permanecen en #24–#27.
- No se implementa SSO, envío de correos, emisión fiscal ni operaciones externas.
- No se cambian capacidades, decisiones o modelos de gastos.

### Decisiones necesarias para concretar #23

| Decisión | Carácter y fundamento |
|---|---|
| Presentar produce PRESENTADA; observar PRESENTADA produce OBSERVADA; corregir una propia OBSERVADA vuelve a PRESENTADA. | Decisión mínima de implementación para materializar el recorrido exigido. Registrar en SPEC-004 como propuesta técnica del incremento; no atribuirla a una validación previa inexistente. |
| Observar requiere motivo no vacío; corregir admite nota opcional. | La observación necesita contenido para ser subsanable; no existe fundamento previo para exigir un descargo adicional al corregir. |
| D01 exige fecha, operación y archivo solo con respuesta Sí y banco/Mercado Pago. | Regla previa confirmada. |
| Cuenta corriente con Sí no se rechaza por esa sola combinación; los respaldos opcionales se conservan. | No introducir restricciones ajenas a D01. La interfaz explica que declarar no verifica el ingreso. |
| Campos marcados obligatorios en el formulario se usan como perfil provisional de demo, incluida observaciones. | Hipótesis explícita y reversible para ejecutar el recorrido; sigue pendiente confirmar si se mantienen las 13 exigencias. No presentar esa hipótesis como decisión operativa aprobada. |

La aclaración de obligatoriedades y catálogos puede ajustar el perfil provisional
antes de la validación funcional. No bloquea la infraestructura ni las pruebas
del recorrido con datos sintéticos completos. No hay decisión nueva sobre cargos
reales, visibilidad por área, rechazo definitivo, plazos ni cantidad de rondas.

## 2. Responsabilidades y forma de trabajo

| Entrega | Matías | Franco |
|---|---|---|
| Identidad y capacidades comunes | Implementar extensión compatible, cuentas y pruebas. | Revisar el contrato y verificar su consumo desde gastos. |
| Solicitudes de facturación | Modelos, formularios, políticas, servicios, vistas, plantillas y pruebas. | Revisión cruzada de interfaces comunes afectadas. |
| Documentos comunes usados por facturación | Compensación, vínculos, versiones y regresión del proveedor. | Revisar compatibilidad con su consumidor; mantener su integración de gastos. |
| Historial | Eventos y DTO de facturación; parcial local compatible si hace falta. | Navegación y componente visual común. |
| Integración de ambos circuitos | Aportar casos y contrato de facturación. | Implementar sus adaptaciones de gastos y aportar sus casos. |

Matías no implementa OneToOne ni guardas de SolicitudGasto, deuda/cierre de gastos,
adaptación de sus eventos ni navegación global de Franco. Su terminación no
bloquea el recorrido propio de #23. #28 conserva la verificación conjunta.

Implementar en una rama de tarea desde `main` actualizado. Preservar los cambios
locales actuales; no trasladarlos ni sobrescribirlos automáticamente. Antes de
codificar, volver a comparar el contrato con el `main` disponible: este plan no
supone que el commit de referencia sea para siempre la última versión.

## 3. Identidad y capacidades — #21

### Actor y resolución

Conservar `Actor` en `identidad/services.py`, `frozen=True`, `slots=True`, orden
posicional y tipos existentes:

```python
subject_id: int
capabilities: frozenset[str]
email_registrado: str | None = None
```

`resolve_actor` conserva sesión verificada, cuenta activa, adaptador habilitado y
lectura de grupos desde base en cada resolución. Completa `email_registrado`
desde `user.email.strip()`; un valor vacío produce None. No promete verificación
institucional. No cambia identidad, historial ni propiedad por correo.

El alta de facturación valida el correo no vacío y su formato. La falta de
correo no invalida al actor para gastos, consultas o correcciones: estas últimas
conservan el correo histórico de presentación. No agregar username ni otro
modelo de identidad. No hacer del correo parte de la autorización.

Mantener todas las defensas actuales de `has_capability`: tipo Actor, actor
ausente, código conocido y pertenencia explícita. Staff/superusuario no aportan
autoridad de negocio. La revocación se refleja al resolver nuevamente el actor;
no modifica instancias ya creadas durante una petición.

### Catálogo y cuentas

Reutilizar las capacidades existentes de facturación y documentos. No introducir
`facturacion.anular` ni `documentos.revisar` en esta entrega: sus acciones y
asignaciones se concretan en #27 y #24. No renombrar los códigos vigentes.
`KNOWN_CAPABILITIES` sigue derivándose del mapa en código, no se mantiene una
lista paralela editable en base.

Conservar los grupos actuales, incluido `demo_facturacion_operadora`. Su capacidad
de cierre existente no activa ninguna acción de cierre en #23; separar cargos o
crear C no es necesario para este alcance. No reconfigurar permisos futuros por
suposiciones de autoridad institucional.

Extender `preparar_identidad_demo` con opción explícita `--facturacion`. Sin esa
opción conserva el comportamiento I1; con ella prepara las cuentas de facturación
con los grupos siguientes, además de sus grupos de gastos actuales:

| Cuenta existente | Grupos adicionales con --facturacion | Correo sintético |
|---|---|---|
| demo_a | demo_facturacion_solicitante, demo_documentos_aporte, demo_documentos_metadatos, demo_documentos_descarga | solicitante.a@example.invalid |
| demo_b | Los mismos de demo_a | solicitante.b@example.invalid |
| demo_o | demo_facturacion_operadora, demo_documentos_aporte, demo_documentos_metadatos, demo_documentos_descarga | operador.o@example.invalid |
| demo_l | demo_facturacion_lectura | lectura.l@example.invalid |

L no recibe descarga documental global como nueva política. Casos documentales
con lectores autorizados se preparan explícitamente en fixtures, sin ampliar la
cuenta I1 por defecto. La preparación conserva contraseñas y guardas de colisión;
crea usuarios nuevos con contraseña inutilizable. No sobrescribe un correo no
vacío diferente: informa colisión para revisión manual. Al repetir el comando
preserva grupos adicionales conocidos ya asignados; nunca borra permisos de un
circuito al preparar el otro. Probar expresamente esa idempotencia.

## 4. Modelo, formulario y catálogos

Conservar aplicaciones en la raíz y relaciones de #22:

- `SolicitudFacturacion.tramite_base` es OneToOne protegido.
- El titular vive solo en `TramiteBase.solicitante_actor_id`, CharField con
  `str(actor.subject_id)`. No duplicarlo ni migrarlo a otra identidad.
- El centro de costo vive solo en `TramiteBase.centro_costo_codigo`; el formulario
  ofrece `centro_costo` como ChoiceField y el servicio persiste en la cabecera.
- Mantener `estado` con longitud 40 para no reducir innecesariamente el campo
  integrado. Añadir BORRADOR_TECNICO, PRESENTADA y OBSERVADA al enumerado de #23.

### Campos de solicitud

| Campo | Persistencia y validación operativa |
|---|---|
| clave_idempotencia | UUID no nulo, editable=False; UniqueConstraint explícita `uq_facturacion_clave_idempotencia`, sin unique=True redundante. |
| version_concurrencia | Entero positivo, inicial 1, aumenta en observación/corrección. |
| correo_solicitante | EmailField, copia histórica del alta, inmutable por servicios y formularios. |
| fecha_presentacion | DateTimeField anulable para técnicos; fijada por servidor una vez al presentar. |
| presento_comprobante_pago | BooleanField anulable para técnicos; respuesta explícita requerida al presentar/corregir. |
| nombre_solicitante | CharField(200), no vacío tras strip en perfil operativo. |
| cuit_receptor | CharField(11), exactamente 11 dígitos ASCII y verificador módulo 11. |
| nombre_receptor | CharField(255), no vacío tras strip. |
| condicion_iva | CharField(30), código del catálogo. |
| email_envio_factura | EmailField(254), formato válido. |
| detalle_factura | TextField, no vacío tras strip. |
| importe_factura | DecimalField(12,2), finito, positivo, máximo 9999999999.99; rechazar precisión excedente, sin redondeo silencioso ni float. |
| producto_servicio | CharField(60), código del catálogo. |
| modalidad_cobro | CharField(30), código del catálogo. |
| observaciones | TextField, obligatorio solo conforme al perfil provisional indicado en sección 1. |
| fecha_operacion_declarada | DateField opcional salvo D01. |
| numero_operacion_declarado | CharField(100), opcional salvo D01. |
| documento_comprobante_inicial | FK Documento PROTECT anulable, related_name='+'; referencia al respaldo actualmente asociado, incluso versión posterior a 1. |
| observacion_vigente | TextField, vacío al presentar; motivo al observar; se limpia al corregir. |

Los campos escalares nuevos admiten vacío/NULL en registros técnicos. Reutilizar
las 10/38/35/5 opciones de condición IVA, producto, centro y modalidad del formulario
relevado y de la corrección, con códigos estables en `facturacion/choices.py`.
Usar max_length 30/60/50/30 respectivamente; el centro permanece en cabecera.
Conservar códigos aunque se corrija una etiqueta. `OPCION_35` se conserva como
valor relevado, marcado para aclaración C02; no inventar su significado. Los
catálogos son perfil de demo hasta confirmación operativa, no reglas fiscales.

El formulario excluye PK, cabecera, titular, correo histórico, fecha de
presentación, estado y control interno de versión. El token y versión esperada
son campos de control separados. Las escrituras usan lista explícita de campos
editables: los datos operativos de la tabla, salvo metadatos y controles. Nunca
asignar indiscriminadamente todo el POST al modelo.

Para Sí/No usar TypedChoiceField con selección vacía, True y False; ausencia no
equivale a No. El valor de servicio debe ser booleano real, no bool('False').

### D01 sin reglas adicionales

| Respuesta y modalidad | Exigencia de respaldo |
|---|---|
| Sí y MERCADO_PAGO/BNA_COMUN/BNA_UVT/NBCH | Fecha, operación no vacía y archivo o versión vigente ya asociada, los tres obligatorios. |
| No, cualquiera de las modalidades | Los tres datos son opcionales. |
| Cuenta corriente, sea Sí o No | Los tres datos son opcionales. |

Cuando sean opcionales, conservar cada dato válido enviado, incluso un conjunto
parcial. Validar formato/tamaño de todo archivo suministrado. No exigir los otros
dos datos ni rechazar la combinación por inferencia. La interfaz aclara que no
constituye un cobro verificado. No borrar respaldos automáticamente por cambiar
Sí a No o elegir cuenta corriente.

En corrección, la ausencia de nuevo archivo conserva el asociado. Reemplazar usa
la cadena de versiones de #22. Ofrecer retirada explícita del vínculo vigente,
permitida solo si el resultado satisface D01; conserva bytes, documento y snapshot
anteriores. Nunca aceptar un ID de documento arbitrario del navegador como forma
de adjuntar: conservar el servidor-resuelto o incorporar archivo nuevo.

## 5. Autorización, vistas y errores

`facturacion/permissions.py` contiene filtro de visibilidad y guardas de acción;
no depende de nombres de grupos. El filtro devuelve queryset vacío sin capacidad,
no intenta retornar y lanzar una excepción a la vez.

Las consultas operativas excluyen BORRADOR_TECNICO. Actor con consultar_todas ve
operativas; con consultar_propias ve solo titular str(subject_id). Corregir exige
visibilidad, titularidad y facturacion.corregir; observar exige visibilidad y
facturacion.observar. La lectura global no implica escritura. Los servicios
repiten las guardas, aunque ya se hayan comprobado en la vista.

| Ruta | Acción |
|---|---|
| GET /facturacion/ | Lista visible paginada, orden estable por fecha y PK. |
| GET, POST /facturacion/nueva/ | Mostrar/presentar con facturacion.presentar. |
| GET /facturacion/<numero>/ | Detalle, datos y eventos autorizados. |
| POST /facturacion/<numero>/observar/ | Observar con motivo y versión esperada. |
| GET, POST /facturacion/<numero>/corregir/ | Corrección de propia OBSERVADA. |

GET no crea solicitudes, cabeceras, documentos ni eventos. La emisión de token
firmado de formulario no persiste un trámite. Métodos no admitidos producen 405.
Usar plantillas Django con etiquetas, errores por campo, teclado y datos escalares
conservados tras error. El navegador exige volver a seleccionar un archivo si
se re-renderiza tras un fallo; explicarlo, sin prometer conservar el upload.

Precedencia: CSRF en POST; actor; visibilidad si hay objeto; capacidad/titularidad;
formato de token/versión; conflicto de estado/versión; contenido. En escritura
revalidar sobre filas bloqueadas. Un chequeo preliminar no sustituye ese control.

- Sin actor: redirección al login de demo habilitado según I1; adaptador apagado,
  denegación 403 sin ofrecer login de demo. Mantener logout accesible según I1.
- Objeto ajeno/inexistente/técnico: 404 idéntico en lectura y acciones.
- Objeto visible sin capacidad o titularidad de acción: 403.
- Ruta general sin capacidad de lectura/presentación: 403.
- Token inválido, versión ausente/no entera positiva o datos inválidos: 400.
- Versión desactualizada, estado incompatible o clave ya consumida: 409.
- Otros fallos de integridad/almacenamiento: error controlado de servidor, sin
  exposición de rutas o datos sensibles, nunca convertir indiscriminadamente en 409.

Las excepciones Python no son respuestas HTTP: las vistas traducen explícitamente
los errores de dominio. Un servicio con datos ajenos no revela primero errores
de formulario. Una petición sin CSRF puede recibir 403 antes de cualquier otro
control, conforme al middleware.

## 6. Servicios, transiciones y concurrencia

Servicios públicos: `presentar_solicitud_facturacion`,
`observar_solicitud_facturacion`, `corregir_solicitud_facturacion`; consultas
separadas sin efectos. Los servicios reciben Actor del adaptador del servidor;
no es una API para confiar identidades construidas por clientes externos.

Presentación y corrección son dueñas de la transacción exterior: rechazan ser
llamadas dentro de otro atomic o con autocommit deshabilitado. No activar
ATOMIC_REQUESTS para sus vistas. Pruebas de estos servicios usan transaction=True.
Observar usa atomic; no incorpora archivos.

### Token de presentación

GET crea UUID v4 y firma el payload subject_id:UUID con
Signer(salt='facturacion.presentar.v1'). POST valida firma, estructura, UUID y
sujeto. No introducir vencimiento sin necesidad del recorrido. Reutilizar token
en errores de formulario; token inválido requiere recargar un formulario válido.
El UUID se guarda como clave_idempotencia. No se deduplican formularios con tokens
distintos. Clave ya consumida produce 409 sin modificar el trámite existente.

Puede comprobarse existencia antes de validar contenido para detectar reenvío;
la garantía concurrente es la UniqueConstraint. Capturar IntegrityError fuera del
atomic y convertir a PresentacionDuplicadaError solo SQLSTATE 23505 y nombre
`uq_facturacion_clave_idempotencia`; no usar un exists como sustituto del diagnóstico.
full_clean no debe transformar esa carrera en un error genérico de formulario:
excluir solo esta comprobación de unicidad de la validación Python y confiar en
PostgreSQL para ella. Mantener las demás validaciones explícitas.

### Secuencia de presentación

1. Resolver autorización y token; validar escalares, D01 y archivo en memoria.
   Reutilizar `documentos.policy.validar_archivo`: PDF/JPEG/PNG, máximo configurable
   de 10 MiB exactos, nombre, extensión, MIME, firma y tamaño. No consumir dos
   veces el mismo stream: reutilizar ArchivoValidado mediante interfaz interna.
2. Abrir transacción exterior; reservar PK con la secuencia existente de #22;
   crear cabecera y solicitud provisional BORRADOR_TECNICO con clave única.
   No usar MAX+1 ni bloqueo de tabla. Las secuencias pueden dejar huecos al revertir.
3. Incorporar respaldo con la solicitud ya existente y acceso por objeto
   comprobado. El resolver técnico/documental admite la provisional dentro de
   esta transacción; las vistas y consultas operativas continúan excluyéndola.
   No ampliar la visibilidad de borradores históricos en pantallas de negocio.
4. Asignar datos completos, fecha del servidor, correo histórico y vínculo;
   validar relaciones y contenido; pasar a PRESENTADA/version 1 y guardar.
5. Crear PRESENTACION con snapshot y confirmar. Ninguna salida exitosa de este
   servicio conserva la fila en estado técnico; toda excepción revierte el alta.

La fábrica técnica de #22 se conserva para pruebas/contratos; extraer su reserva
de número como helper interno si evita duplicación. No convertirla en otra ruta
de presentación funcional ni inventar eventos de negocio para sus fixtures.

### Observación y corrección

Dentro de atomic, bloquear primero cabecera y después solicitud con un orden
constante y documentado. Leer después el estado vigente y comprobar autorización,
formato de versión, estado, versión y datos. Si se requiere resolver referencia
antes del bloqueo, repetir las condiciones después. Evitar un orden de bloqueo
implícito dependiente del plan SQL de un JOIN.

- Observar PRESENTADA: motivo strip no vacío, guardar OBSERVADA, motivo vigente,
  versión +1 y evento OBSERVACION, todo junto.
- Corregir propia OBSERVADA: snapshot anterior; validar cambios y D01; actualizar
  cabecera si corresponde; incorporar/reemplazar/retirar vínculo solicitado;
  conservar metadatos inmutables; guardar PRESENTADA, versión +1 y observación
  vigente vacía; crear CORRECCION con antes/después y observación atendida.

Nota de corrección opcional; no se habilita editar en PRESENTADA. No se fija un
límite de rondas. Conflicto o fallo al escribir el evento conserva todo lo previo.
El orden cabecera→solicitud→raíz documental→versión debe contrastarse con los
servicios documentales afectados antes de introducir bloqueos adicionales;
mantener el orden propio gasto→cabecera→documento del consumidor de gastos.

## 7. Documentos, compensación e integridad

Conservar `Documento.tramite_base_id`, `tipo`, `serie`, `version`, `reemplaza` y
`referencia_version`. Incorporar respaldos del solicitante con procedencia
SOLICITANTE. El personal sigue usando la matriz de procedencias existente;
no declararlo solicitante ni eludir `_validar_clasificacion`.

Reemplazo usa `reemplaza_id` de la versión actualmente vinculada, conserva serie
y tipo e incrementa versión bajo el bloqueo documental existente. No exigir
version==1. No modificar/borrar versiones previas. Snapshot identifica exactamente
la versión, incluyendo UUID referencia_version.

FK de solicitud a documento más trigger de integridad que verifica misma cabecera
y tipo COMPROBANTE_COBRO cuando el vínculo no es NULL. Usar nombres reales;
conservar trigger de cabecera existente. Python comprueba además la versión
vigente al asociar o reemplazar. No extender automáticamente esa regla de vigencia
a snapshots históricos. Los triggers de documento ya protegen su inmutabilidad.

### Compensación del almacenamiento

Extender el servicio común sin duplicarlo. La llamada independiente conserva su
API; la operación exterior puede suministrar un registro interno de escrituras.
Registrar ruta prevista antes del intento y nombre real retornado por storage.save
inmediatamente después. Identificar también el storage usado. Solo compensar
rutas nuevas de esa operación; nunca el archivo anterior de un reemplazo.

En rollback confirmado, borrar nuevas rutas con captura de fallos individuales,
registro privado de limpieza pendiente y relanzamiento mediante `raise`.
No cambiar la excepción principal por la del borrado. Si la limpieza interna ya
ocurrió, la exterior debe tolerar archivo inexistente.

Ante pérdida de conexión durante commit con resultado incierto, no borrar a
ciegas: conservar rutas y referencias de operación en registro privado y
reconciliar mediante una conexión nueva contra filas documentales persistidas.
Solo borrar cuando se confirme ausencia de referencia. Si no hay conexión,
dejar pendiente y no presentar el trámite como confirmado al usuario.

Para demo, un manifiesto privado por operación, escrito antes del almacenamiento,
y un comando de reconciliación explícito bastan; no se introduce un servicio
distribuido. La reconciliación no toca operaciones activas ni filas existentes;
solo procesa operaciones marcadas terminadas/fallidas o revisadas tras caída con
la aplicación detenida. Rutas privadas no se muestran al cliente ni se versionan.
El apagado abrupto y los errores de storage no permiten prometer una transacción
distribuida: documentar compensación de mejor esfuerzo y recuperación reproducible.

## 8. Migraciones y garantías de base

1. Agregar campos compatibles con técnicos: fechas/importes/booleano/documento
   anulables; textos con vacío explícito para datos previos, sin inventar valores
   de negocio. Agregar snapshot_datos a EventoFacturacion con default=dict sin
   reescribir eventos históricos append-only.
2. Agregar UUID anulable, poblar con uuid4 individual por fila mediante modelos
   históricos y sin alterar PK/cabecera; después no nulo y UniqueConstraint
   nombrada. Probar los triggers existentes durante este RunPython.
3. Agregar enumerado/constraints con `condition=`: estado conocido, versión >0,
   y campos operativos no vacíos/no nulos e importe positivo salvo técnicos.
   Las condiciones SQL distinguen NULL y cadena vacía.
4. Agregar comprobación D01 a nivel base para estados operativos: si Sí y medio
   efectivo, exigir fecha, número y FK. No añadir un all-or-none para opcionales.
5. Incorporar trigger de pertenencia/tipo documental. Los catálogos, strip,
   módulo 11, correo y política de bytes se validan en servicios; no afirmar que
   un CHECK de no vacío comprueba todos esos formatos.
6. El centro vive en otra tabla: el servicio valida su código/obligatoriedad y
   guarda ambas entidades juntas; full_clean de la solicitud no lo hace solo.
   No agregar un trigger global que imponga catálogos de facturación a gastos.

No convertir BORRADOR_TECNICO previo a PRESENTADA ni borrar sus documentos.
Probar migración desde el esquema #22 y base vacía. La vuelta a un esquema que
perdería datos operativos nuevos debe rechazarse o documentarse como no soportada;
corregir hacia adelante en lugar de borrar historial. No limpiar filas previas
para conseguir que las pruebas pasen.

## 9. Historial y snapshots

Mantener EventoFacturacion append-only, actor_id=actor.subject_id y
fecha_hora del servidor. Añadir JSON snapshot_datos con esquema_version=1:

- tipo_evento, version_anterior (null en alta), version_resultante;
- antes (null en alta), despues;
- observacion_atendida y nota_correccion, opcionales según evento.

Cada estado serializado incluye estado, versión, metadatos de presentación,
centro de costo, campos operativos, observación vigente y respaldo (id, tipo,
serie, version, referencia_version) o null. Decimal como cadena de dos decimales;
fechas ISO; timestamps UTC con microsegundos. No incluir bytes, claves firmadas,
contraseñas ni rutas físicas. La fecha autoritativa de evento es fecha_hora, sin
inventar un segundo timestamp independiente en JSON. Orden estable fecha_hora/PK.

Detalle convierte eventos al EventoHistorialDTO integrado. Usar el parcial común
si existe y cumple contrato; de lo contrario crear parcial local de facturación
que consume los DTO, sin cambiar la navegación global de Franco. Los snapshots
se muestran solo bajo autorización de la solicitud, incluso tras futuras etapas.

## 10. Pruebas y evidencia

Usar PostgreSQL y storage temporal, datos exclusivamente sintéticos. Las pruebas
que llaman servicios dueños de transacción usan django_db(transaction=True).
Comparar conteos y valores antes/después; no suponer tablas vacías.

| Área | Casos obligatorios de esta entrega |
|---|---|
| Compatibilidad | Actor posicional/keyword, correo opcional, flags técnicos sin autoridad, códigos desconocidos, demo apagada, sesión ausente/inactiva. |
| Preparación | Modo I1 preservado, --facturacion repetible, contraseñas y grupos existentes conservados, colisiones, correos sintéticos, sin ampliar L a descargas globales. |
| Permisos | Propias/ajenas, URL directa, lectura global sin modificación, capacidad de acción sin visibilidad, llamadas directas a servicios y manipulación de metadatos. |
| Revocación | Nueva resolución tras retirar grupo; 404 si perdió visibilidad, 403 si mantiene lectura mediante grupo separado. Actor anterior no cambia retroactivamente. |
| Formulario | Sí/No/ausente; CUIT, correo, catálogos, espacios, centavos, exceso de dígitos/decimales e importes no finitos; D01 completa/incompleta; cuenta corriente y respaldos opcionales parciales conservados. |
| Recorrido | Presentar→observar→corregir, versiones 1/2/3, motivo obligatorio, nota opcional, snapshots antes/después, observación atendida conservada y vigente limpia. |
| Repetición | Token ausente/manipulado/de otro sujeto; conservación ante error; doble alta con mismo token; otro IntegrityError no disfrazado; versión ausente/obsoleta y estado incompatible. |
| Concurrencia | Dos conexiones coordinadas: alta mismo token, observación misma versión y corrección misma versión; un éxito y un conflicto, un solo evento por acción exitosa. Cerrar conexiones de cada hilo en finally. |
| Documentos | Política exacta de #19, pertenencia/tipo, versión posterior a 1, nueva referencia vigente y anterior intacta; no asociar IDs ajenos; fallo de evento y rollback de campos, centro y vínculo. |
| Compensación | Fallo antes/después de save de storage, borrado fallido sin sustituir excepción, transacción exterior rechazada, commit incierto sin borrar respaldo confirmado, reconciliación sin tocar operaciones activas. |
| HTTP | 404/403/400/409, 405 en métodos indebidos, GET sin escrituras, CSRF con enforce_csrf_checks=True y conservación de errores del formulario. |
| Migraciones | Base vacía y desde #22 con técnicos/eventos/documentos; UUID distintos; triggers y snapshots previos preservados. |

Ejecutar ruff, manage.py check, makemigrations --check --dry-run y pruebas
pertinentes de identidad/documentos/comunes/facturación más regresión de gastos
afectada por identidad/documentos. No exigir a Franco escribir las pruebas de
facturación. Comprobar manualmente etiquetas, teclado, errores y recorrido de
tres pasos; no sustituirlo solo por checks automáticos.

## 11. Secuencia de entrega y condiciones de cierre

1. Actualizar SPEC-002/004 y contrato común con las decisiones de este plan,
   separando perfil provisional de demo y reglas confirmadas. Revisar cambios
   del contrato con Franco; no afirmar una aprobación que todavía no ocurrió.
2. Entregar extensión compatible de identidad, preparación optativa y políticas
   de acceso, con pruebas. Mantener #21 abierta por evidencia funcional pendiente.
3. Incorporar migraciones, DTO/snapshot, token y servicios transaccionales;
   completar compensación y acceso documental de la presentación provisional.
4. Entregar alta/lista/detalle; después observación/corrección y reemplazos, sin
   declarar #23 terminada con solo el formulario inicial.
5. Ejecutar concurrencia, regresión, migración y recorrido sintético reproducible.
   Registrar commit, entorno, comandos/resultados, límites y pasos de recuperación.
6. PR vinculada a #21/#23 y revisión cruzada pertinente. La integración de otros
   consumidores sigue en #28; aceptación funcional de Cooperadora es evidencia
   separada y conserva los puntos de confirmación del perfil provisional.

#21 tiene evidencia de su consumidor de facturación cuando se demuestran listas,
detalle, acciones, revocación y contrato común. #23 se completa con presentación,
observación, corrección, conservación histórica, documentos condicionales y
rechazos sin cambios parciales confirmados. El plan no declara cerradas esas
issues ni ejecutadas sus pruebas por haber sido escrito.

## 12. Anexo de códigos y etiquetas del perfil de demo

Estos son los valores completos utilizados por el plan. CentroCosto se persiste
en TramiteBase; los demás catálogos, en SolicitudFacturacion. Su procedencia es
el formulario relevado. No se aplican como catálogo global del circuito de gastos.

### 12.1. `CondicionIVA` (`max_length=30`)

1. `('IVA_RESPONSABLE_INSCRIPTO', 'IVA Responsable Inscripto')`
2. `('IVA_SUJETO_EXENTO', 'IVA sujeto Exento')`
3. `('CONSUMIDOR_FINAL', 'Consumidor Final')`
4. `('RESPONSABLE_MONOTRIBUTO', 'Responsable Monotributo')`
5. `('PROVEEDOR_EXTERIOR', 'Proveeor del Exterior')`
6. `('CLIENTE_EXTERIOR', 'Cliente del Exterior')`
7. `('IVA_LIBERADO_19640', 'IVA Liberado - Ley N° 19.640')`
8. `('IVA_RI_AGENTE_PERCEPCION', 'IVA Resp Insc- Agente de Percepción')`
9. `('MONOTRIBUTO_SOCIAL', 'Monotributo Social')`
10. `('IVA_NO_ALCANZADO', 'Iva No Alcanzado')`

### 12.2. `ProductoServicio` (`max_length=60` — 38 opciones)

1. `('ABONO_MENSUAL', 'Abono Mensual')`
2. `('ALQUILER', 'Alquiler')`
3. `('ANALISIS', 'Análisis')`
4. `('ANALISIS_DOSIMETRIA', 'Análisis de Dosimetria')`
5. `('BIENES_DE_CAPITAL', 'Bienes de Capital')`
6. `('CAPACITACION_CONVENIO', 'Capacitación según Convenio')`
7. `('CONSULTORIA_Y_SERVICIOS', 'Consultoria y Servicios')`
8. `('CONVENIO_RADIO', 'Convenio Radio')`
9. `('CORRESPONDENCIA_ENVIO', 'Correspondencia/Envio')`
10. `('COOPERADORA', 'Cooperadora')`
11. `('CUOTA_SOCIETARIA_COOP', 'Cuota Societaria Asoc. Coop')`
12. `('CURSOS_CISCO', 'Cursos Cisco')`
13. `('CURSOS_CAPACITACION_ELEARNING', 'Cursos de capacitación E-Learning')`
14. `('CURSOS_CAPACITACION_VIRTUAL', 'Cursos de Capacitación Modalidad Virtual')`
15. `('CURSOS_CAPACITACION_PRESENCIAL', 'Cursos de Capacitación Presencial')`
16. `('ESPACIO_DE_RADIO', 'Espacio de Radio')`
17. `('EVENTOS', 'Eventos')`
18. `('EXAMEN_OXFORD', 'Examen Oxford Test of English')`
19. `('GISTAQ_ANALISIS_AGUA', 'GISTAQ- Análisis de Agua')`
20. `('GISTAQ_ANALISIS_CARBON', 'GISTAQ- Análisis de Carbon')`
21. `('GISTAQ_SERVICIOS', 'GISTAQ Servicios')`
22. `('HONORARIOS', 'Honorarios')`
23. `('IMPRESIONES', 'Impresiones')`
24. `('INSUMOS_MANTENIMIENTO', 'Insumos de Mantenimiento')`
25. `('INSUMOS_LABORATORIO', 'Insumos de Laboratorio')`
26. `('INSUMOS_INFORMATICOS', 'Insumos Informaticos')`
27. `('PROYECTO_UVT', 'Proyecto UVT')`
28. `('QUIMOBI_ANALISIS_BIODIESEL', 'QUIMOBI- Análisis de Biodiesel')`
29. `('QUIMOBI_SERVICIOS', 'QUIMOBI- Servicios')`
30. `('QUITEX_ANALISIS_CERVEZA', 'QUITEX- Análisis de Cerveza')`
31. `('QUITEX_ANALISIS_PRODUCTOS', 'QUITEX- Análisis de Productos')`
32. `('REINTEGRO', 'Reintegro')`
33. `('REINTEGROS_GASTOS', 'Reintegros gastos')`
34. `('SERVICIOS_AUDITORIAS', 'Servicios de Auditorias')`
35. `('TRABAJOS_MANTENIMIENTO', 'Trabajos de mantenimiento')`
36. `('UVT', 'UVT')`
37. `('VIATICOS', 'Viaticos')`
38. `('OTROS', 'Otros')`

### 12.3. `CentroCosto` (`max_length=50` — 35 opciones)

1. `('ALQUILER', 'Alquiler')`
2. `('AULA_MAGNA', 'Aula Magna')`
3. `('OPCION_35', 'Opción 35')` *(Incluido por fidelidad literal con el formulario relevado; registrado como pendiente de aclaración operativa en `C02` porque corresponde a un ítem sin renombrar en el Google Form original)*.


4. `('AUSPICIO', 'Auspicio')`
5. `('BIBLIOTECA', 'Biblioteca')`
6. `('BIOTEC', 'Biotec')`
7. `('CAPACITACION', 'Capacitación')`
8. `('CAPACITACION_ELEARNING', 'Capacitación Elearning')`
9. `('CET', 'CET')`
10. `('CINAPTIC', 'CINAPTIC')`
11. `('CISCO', 'CISCO')`
12. `('COOPERADORA', 'Cooperadora')`
13. `('EVENTO', 'Evento')`
14. `('GESTION_TECNOLOGICA', 'Gestion Tecnologica')`
15. `('GISTAQ', 'GISTAQ')`
16. `('GITEA', 'GITEA')`
17. `('INTECNOR', 'INTECNOR')`
18. `('LAB_FISICA', 'Lab Fisica')`
19. `('LAB_QUIMICA', 'Lab Química')`
20. `('MANTENIMIENTO', 'Mantenimiento')`
21. `('POSGRADO', 'Posgrado')`
22. `('QUIMOBI', 'QUIMOBI')`
23. `('QUITEX', 'QUITEX')`
24. `('RADIO', 'Radio')`
25. `('RRHH', 'RRHH')`
26. `('RRII', 'RRII')`
27. `('SACAD', 'SACAD')`
28. `('SADMIN', 'SADMIN')`
29. `('SAU', 'SAU')`
30. `('SAU_DEPORTES', 'SAU-Deportes')`
31. `('SCYT', 'SCYT')`
32. `('SEU', 'SEU')`
33. `('STERCEROS', 'STERCEROS')`
34. `('UTD', 'UTD')`
35. `('UVT', 'UVT')`

### 12.4. `ModalidadCobro` (`max_length=30` — 5 opciones)

1. `('MERCADO_PAGO', 'Mercado Pago')`
2. `('BNA_COMUN', 'Banco Nación Cuenta Comun')`
3. `('BNA_UVT', 'Banco Nación Cuenta UVT')`
4. `('NBCH', 'Nuevo Banco del Chaco')`
5. `('CUENTA_CORRIENTE', 'Cuenta corriente (aun no se cobró la factura que se va a emitir)')`
