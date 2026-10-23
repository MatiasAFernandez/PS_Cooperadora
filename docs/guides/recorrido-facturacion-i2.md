# Recorrido local de facturación — solicitudes y comprobantes externos

Usar exclusivamente datos y documentos sintéticos. Este recorrido cubre la
presentación, observación y corrección de solicitudes, el registro de comprobantes
y cobros externos, la verificación independiente del ingreso y la resolución
explícita del trámite. No realiza emisión fiscal ni transferencias. Las obligatoriedades del formulario relevado son un
perfil provisional de demo.

## Preparación

Desde una versión con solicitudes, revisión documental, comprobantes de #25 y
cobros de #26 y resolución de #27, con el entorno Python
activado, dependencias instaladas y PostgreSQL local configurado en .env (ver README):

```powershell
python manage.py migrate
python manage.py preparar_identidad_demo --facturacion --revision-documental --verificacion-cobros --resolucion-facturacion
python manage.py changepassword demo_a
python manage.py changepassword demo_b
python manage.py changepassword demo_o
python manage.py changepassword demo_l
python manage.py runserver 127.0.0.1:8000
```

Habilitar DEMO_IDENTITY_ENABLED=true solo en el entorno local. El comando no
publica ni establece contraseñas reutilizables. Si encuentra otro correo o una
configuración peligrosa de una cuenta, informa colisión; no reemplazarla a ciegas.
Sin --facturacion se mantiene la preparación I1; repetir no quita grupos conocidos.
`--revision-documental` habilita de forma optativa la revisión para demo_o y le
asigna metadatos/descarga. Omitirlo conserva el recorrido de facturación sin
ampliar esa capacidad; no revoca un grupo ya asignado. No otorga permiso de pago.

## Recorrido

1. Entrar en /demo/acceso/ como demo_a. Desde inicio abrir facturación o navegar
   a /facturacion/. Crear solicitud con datos ficticios completos. Para el CUIT
   sintético de pruebas puede usarse 30712345671; no representa un receptor real.
2. Con No/cuenta corriente puede omitirse el respaldo. Con Sí y banco/Mercado
   Pago completar fecha, operación y archivo PDF/JPEG/PNG hasta 10 MiB.
3. El detalle muestra PRESENTADA, metadatos del servidor e historial.
   El reenvío del mismo formulario se rechaza; no crea otra solicitud.
4. Salir y entrar como demo_o. Abrir el detalle y observar con motivo no vacío.
5. Volver como demo_a, abrir Corregir, completar lo observado y reenviar. La
   nota de corrección es opcional. Se conserva la versión anterior.
6. El reemplazo de archivo conserva la serie documental y el archivo anterior.
   La retirada explícita desvincula sin borrar historia; se deniega si incumple D01.
7. demo_b no ve la solicitud de A ni la obtiene por URL directa (404).
   demo_l consulta todas sin modificar ni recibir descarga documental por defecto.
8. Comprobar teclado, etiquetas, mensajes y datos conservados ante errores.
   Si el formulario falla tras seleccionar un archivo, volver a seleccionarlo.

El pago declarado queda pendiente de verificación. La revisión documental se abre
desde el detalle mediante el enlace del respaldo, como explica la sección siguiente.
El registro de comprobantes y cobros externos se describe a continuación.
El cierre y la anulación son acciones explícitas del recorrido de resolución.
Ambos circuitos usan la navegación y el parcial de historial comunes de #59.
Cada módulo conserva sus reglas de estado y permisos por objeto.

## Factura y notas externas

1. Como demo_o, abrir una solicitud y **Registrar factura o nota externa**.
   Completar Factura, CUIT sintético 30712345671, letra A, punto de venta 1,
   número ficticio único, fecha, importe 100,25 y PDF sintético hasta 10 MiB.
2. Guardar y comprobar identificación, procedencia Xubio, actor/fecha, PDF e
   historial en el detalle. El estado de la solicitud se conserva.
3. Registrar una nota de crédito por 10,10 y una de débito por 1,05, cada una con
   número propio, mismo emisor/letra y PDF. Se vinculan a la factura del trámite;
   el neto informativo resulta 91,20. Pueden registrarse más notas.
4. Una segunda factura o la misma identidad en otro trámite devuelve conflicto.
   Una nota sin factura, datos inválidos o archivo distinto de PDF se rechazan.
   Ante error se conservan los campos; volver a seleccionar el PDF.
5. A consulta sus registros y descarga con su permiso documental. B no accede
   al detalle ni al archivo de A, incluso por URL. L consulta el registro pero
   no registra ni recibe descarga por defecto.

Los registros son inmutables y conservan la versión exacta del PDF. La revisión
documental es independiente: registrar no acepta el respaldo ni acredita un cobro.
El neto no convierte monedas ni cierra el trámite, incluso si llega a cero o es
negativo. La [spec](../specs/005-matias-facturas-notas.md) delimita el perfil demo.

## Cobros y anticipos en ARS

1. Como A, presentar una solicitud sintética sin pago declarado. Abrir
   **Informar cobro o anticipo**. Elegir BNA común, operación ficticia única,
   fecha e importe 60,10 y adjuntar un PDF/JPEG/PNG sintético de hasta 10 MiB.
   El resultado es PENDIENTE, incluso si registra O. No exige factura previa.
2. Informar otro parcial por 40,15 con operación y respaldo propios. Si la solicitud
   ya tenía comprobante inicial, puede elegirse como respaldo en lugar de subir
   otro. No reutilizar la misma versión para dos cobros ni el mismo número de
   operación en la misma cuenta, incluso en otra solicitud.
3. Como O, preparado explícitamente con `--verificacion-cobros`, abrir
   **Verificar ingreso**. Confirmar ambos: total confirmado 100,25 ARS. Rechazar
   exige motivo; el rechazado se conserva pero no suma al confirmado. Una
   verificación registrada no se edita ni repite; una corrección requiere un
   diseño posterior, no borrar historia ni inventar otra operación.
4. El registro inicial no verifica automáticamente el dinero ni el PDF. Revisar
   el PDF sigue siendo otra acción. Si la factura se emite después, se consulta
   con los cobros del mismo trámite sin duplicarlos. El estado del trámite no cambia.
5. A informa y consulta sus cobros; B no accede a ellos ni descarga su archivo.
   L consulta sin informar, verificar ni descargar por defecto. Quitar el grupo de
   verificación a O revoca la acción en la siguiente petición. Preparar facturación
   sin la opción no otorga esa capacidad, ni revoca un grupo ya asignado.
6. Ante datos inválidos o duplicado se conservan los campos, con respuesta 400 o
   409; si adjuntaste un archivo, volver a seleccionarlo. Un respaldo existente
   conserva su selección mientras siga disponible.

Se registra lo efectivamente recibido en ARS. Descuentos, retenciones, comisiones,
conversión de monedas y cierre quedan fuera de este corte. Los importes pendientes,
confirmados y rechazados aparecen separados: no representan por sí solos saldo
cancelado ni suficiencia documental. Ver [SPEC-006](../specs/006-matias-cobros.md).

## Pendientes, cierre y anulación

1. Completar la solicitud, registrar factura por 100,25 ARS y cobros confirmados
   por 60,10 y 40,15. En revisión documental, aceptar la factura y los dos respaldos
   de ingreso. No hace falta aceptar archivos ajenos a esos registros. Las notas
   que existan también requieren respaldo aceptado.
2. El detalle muestra el estado de solicitud (Presentada/Observada) y el seguimiento
   financiero. La cobertura muestra **Cobrada en revisión** sin resolver el trámite.
   El diagnóstico enumera causas de bloqueo para cerrar y para anular.
3. Entrar como O preparado con `--resolucion-facturacion`. Completar motivo y
   **Cerrar trámite**. Se exige neto positivo, igualdad exacta y ausencia de cobros
   pendientes, además de las aceptaciones. Si se declaró transferencia en el
   formulario inicial, registrar su medio/operación como cobro y verificarlo;
   esa declaración no se descarta ni se confirma automáticamente.
4. Faltante, exceso, neto negativo, observación pendiente o respaldo sin aceptación
   vigente impiden cerrar. Un dato cambiado desde que se abrió el detalle devuelve
   409 y conserva el motivo; recargar para decidir sobre el diagnóstico actual.
5. **Anular trámite** exige motivo y permite sólo solicitud sin factura ni ingresos
   pendientes/confirmados, o factura con neto exactamente cero por notas, respaldos
   aceptados y ausencia de esos ingresos. La nota no acredita devolución de dinero.
   No ejecuta anulación fiscal externa. Un ingreso rechazado se conserva y no cuenta.
6. CERRADA y ANULADA son definitivos. Consultar historial y descargar con permiso
   sigue disponible; nuevas operaciones, revisiones y reapertura se deniegan.
   Sin el grupo de resolución no se habilita la acción por ser operador/revisor.
   Resolver requiere también metadatos. Una cuenta sin esa capacidad recibe una
   sección documental neutral y no ve los motivos de actualización de respaldos.

## Sustituir el respaldo vinculado a un registro

1. Antes de resolver el trámite, como O abrir **Actualizar vínculo del respaldo**
   en la factura/nota o cobro. Elegir una sucesora vigente existente de la misma
   serie/tipo/trámite, o adjuntar un archivo nuevo y motivo (una sola opción).
2. Una carga nueva crea la sucesora y su vínculo en una operación; requiere permiso
   de incorporación. Factura/nota requiere PDF; cobro admite PDF/JPEG/PNG hasta
   10 MiB. Los errores conservan motivo/selección y requieren seleccionar el archivo
   nuevamente. Un rollback no deja vínculo ni archivo nuevos a medias.
3. El historial registra objeto, vínculo anterior/nuevo, motivo, actor y fecha.
   Los importes, operaciones y verificaciones no cambian. La nueva versión no
   hereda aceptación y bloquea el cierre hasta revisarse como ACEPTADO.
4. La FK original y las versiones anteriores siguen conservadas. Si ese respaldo
   se compartía con la declaración inicial y luego A corrige con otro archivo,
   su carga continúa la serie vigente; no borra el vínculo histórico del cobro.
   El operador debe actualizar explícitamente el vínculo si vuelve a reemplazarse.

Las condiciones completas y los límites de regularización están en
[SPEC-007](../specs/007-matias-seguimiento-cierre.md).

## Revisión documental

1. Presentar como demo_a una solicitud sintética con respaldo. En el detalle,
   abrir **Revisión de respaldos** y el enlace de la versión. A puede consultar
   el historial con metadatos y acceso a su trámite; no recibe permiso de revisión.
2. Entrar como demo_o, preparado con `--revision-documental`, y abrir ese mismo
   enlace. La página exige acceso al trámite y metadatos; para registrar exige
   además `documentos.revisar`. La descarga mantiene su capacidad independiente.
3. Sin revisiones aparece **Pendiente**. Seleccionar **Aceptado**, **Observado**
   o **Rechazado**; observar/rechazar exige un motivo con texto. Guardar conserva
   resultado, actor y fecha. El historial autorizado muestra los hechos anteriores.
4. Un reenvío o una revisión desde una versión desactualizada devuelve conflicto;
   recargar antes de volver a operar. Una revisión sin permiso o sin CSRF no cambia
   nada. Un documento ajeno o inexistente no se revela por URL directa.
5. Observar la solicitud y corregirla como A con otro archivo conserva la versión
   anterior y sus revisiones. El reemplazo empieza **Pendiente**; no hereda la
   conformidad anterior. La versión reemplazada conserva historial de consulta,
   pero ya no admite nuevas revisiones.

Revisar no verifica el ingreso declarado ni cierra pagos, deudas o trámites.
En el proveedor de gastos, Observado/Rechazado se omite del selector y se deniega
al registrar; un pago ya registrado no se modifica. La tolerancia de demo para
documentos aún sin revisión no acredita conformidad ni cumplimiento documental.
El [contrato](../contracts/revision-documental-i2.md) precisa esa separación.

## Fallos y recuperación

Los servicios de presentación/corrección y registro de comprobantes son dueños
de la transacción exterior.
No envolverlos en otro atomic ni activar ATOMIC_REQUESTS para estas vistas.
El storage compensa archivos nuevos tras rollback y conserva versiones anteriores.
La recuperación es de mejor esfuerzo: una caída o commit incierto deja un
manifiesto bajo DOCUMENT_STORAGE_ROOT/.operaciones y un registro de error.

Detener todas las escrituras de la aplicación antes de reconciliar:

```powershell
python manage.py reconciliar_archivos --aplicacion-detenida
```

El comando procesa rutas de sus manifiestos privados y conserva cualquier
archivo referenciado por Documento. Si la base o el borrado fallan, el manifiesto
permanece para reintento. No ejecutarlo con peticiones activas ni eliminar
manualmente respaldos existentes.

## Verificación

```powershell
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

Las pruebas usan PostgreSQL real, storage temporal y cuentas sintéticas. Cubren
HTTP/CSRF, D01, objetos ajenos, revocación, snapshots, conexiones concurrentes,
rollback y commit incierto. La prueba de aceptación de #23 completa el ciclo HTTP
con CSRF válido, consulta autorizada e intentos repetidos o incompatibles sin
efectos. La [evidencia de cierre de #23](../evidence/i2-23-cierre-solicitudes.md)
registra la revisión de Franco en #52 y las verificaciones de la versión actual.
La devolución de Cooperadora se recoge en #29; las pruebas no acreditan SSO ni
aceptación institucional.
