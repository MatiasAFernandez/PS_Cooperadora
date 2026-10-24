# Verificación, demostración y recuperación de I2

Guía de #29 sobre la base integrada `c1f491f` (#69). Sólo datos sintéticos en
una instancia aislada. Las reglas y permisos de cada módulo se mantienen en sus
specs y contratos; esta guía organiza su reproducción y la muestra de recuperación.

## Instalar y verificar

Seguir [README](../../README.md) para dependencias, entorno virtual y PostgreSQL.
Si se usa PostgreSQL nativo, la [preparación local](recorrido-tecnico-i1.md)
describe esa opción; sus recorridos I1 son históricos. Usar el código del SHA
registrado en la PR de #29. La CI emplea Python 3.11/PostgreSQL 17; este corte
también se verifica localmente con Python 3.14.7/PostgreSQL 18.6.

En una base nueva, con `POSTGRES_*` apuntando a la instancia aislada:

```powershell
python manage.py migrate --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
ruff check .
pytest
```

Para actualizar una copia de una base previa, detener escrituras, respaldar base
y almacenamiento como conjunto, revisar `migrate --plan` y ejecutar `migrate`.
Las reversas que perderían hechos operativos se rechazan; no se usan para borrar
resoluciones, revisiones, pagos o versiones. Conservar la versión de código y las
variables de configuración correspondientes a cada respaldo, sin publicar secretos.

## Preparar y demostrar los dos circuitos

La [matriz y recorridos de #28](../evidence/i2-28-integracion-circuitos.md)
describe los perfiles, capacidades y secuencia. El
[manual de facturación](recorrido-facturacion-i2.md), la
[guía de pago de gastos](c04-pago-externo-proveedor.md) y la
[guía común](historial-y-navegacion-comunes.md) completan los pasos de uso.

Para ensayar desde trámites nuevos, preparar las cuentas y capacidades explícitas
como indica #28. Para disponer además de una muestra ya resuelta que permita
inspeccionar historial y recuperación, usar el comando de la sección siguiente.
Sus cuentas nuevas tienen contraseña inutilizable: asignarla localmente mediante
`changepassword` antes de entrar por navegador. El comando no publica contraseñas.

Guion para la futura demostración (registrar resultado observado, no sólo esperado):

1. A y B entran por el inicio común y presentan un gasto y una solicitud de
   facturación con datos ficticios. Comprobar que no ven trámites ajenos.
2. O decide el gasto, A aporta un respaldo desde su detalle, O revisa esa
   versión y registra el pago externo mediante el proveedor C01. Reenviar el
   mismo pago; debe conservar un único registro. Reemplazar el documento: la
   nueva versión queda pendiente y el pago conserva la versión exacta anterior.
3. En facturación, O registra factura externa, B informa un cobro parcial y O
   lo confirma. Intentar cerrar: debe explicar el faltante. Completar y confirmar
   el cobro restante, aceptar los respaldos vigentes y cerrar explícitamente con
   motivo. No debe cerrar automáticamente por registrar o aceptar un documento.
4. L consulta ambos historiales sin adquirir facultades de decisión, cobro,
   resolución ni acceso documental. Probar una descarga ajena y una operación
   sin capacidad. La descarga autorizada permanece tras el cierre.
5. Registrar observaciones, preguntas y desacuerdos en la ficha de #29. Distinguir
   una falla reproducida de una regla de negocio aún no validada.

Este guion todavía no es un acta de una demostración realizada ni aceptación
institucional. La [ficha de entrega](../evidence/i2-29-verificacion-entrega.md)
identifica la evidencia técnica y los campos pendientes.

## Ensayar copia y restauración de la muestra

Requiere `createdb`, `pg_dump` y `pg_restore` de una versión compatible en PATH,
además de Python y dependencias. Los binarios nativos de PostgreSQL incluyen
estas herramientas. No ejecutar sobre bases o directorios de trabajo existentes.
Las bases siguientes deben ser nuevas y distintas; `pg_restore` no usa `--clean`.

Desde la raíz del repositorio, con la aplicación sin procesos que escriban:

Definir `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_USER` en el entorno de esta
consola. Django lee `.env`, pero esa lectura no exporta variables a PowerShell ni
a las herramientas nativas. Usar los datos de conexión de la instancia aislada.

```powershell
$env:DEMO_IDENTITY_ENABLED = 'true'
$env:GASTOS_PAYMENT_DOCUMENT_PROVIDER = 'documentos.c01.ProveedorDocumentalGastos'
$muestraRoot = Join-Path (Get-Location) '.local/entrega-i2'
if (Test-Path -LiteralPath $muestraRoot) { throw 'Elegir una carpeta nueva para este ensayo' }
New-Item -ItemType Directory -Path $muestraRoot | Out-Null
createdb -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER entrega_i2_origen
if ($LASTEXITCODE -ne 0) { throw 'No se creó la base de origen nueva' }
createdb -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER entrega_i2_restaurada
if ($LASTEXITCODE -ne 0) { throw 'No se creó la base de destino nueva' }
$env:POSTGRES_DB = 'entrega_i2_origen'
$env:DOCUMENT_STORAGE_ROOT = Join-Path $muestraRoot 'archivos-origen'
python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Migración fallida' }
python manage.py muestra_entrega crear --manifiesto "$muestraRoot/manifiesto.json"
if ($LASTEXITCODE -ne 0) { throw 'Preparación fallida; conservar evidencia y usar otro destino vacío' }
pg_dump -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -Fc --no-owner --file="$muestraRoot/muestra.dump" entrega_i2_origen
if ($LASTEXITCODE -ne 0) { throw 'Respaldo de base fallido' }
Copy-Item -LiteralPath "$muestraRoot/archivos-origen" -Destination "$muestraRoot/archivos-restaurados" -Recurse
pg_restore -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER --exit-on-error --no-owner --dbname=entrega_i2_restaurada "$muestraRoot/muestra.dump"
if ($LASTEXITCODE -ne 0) { throw 'Restauración fallida' }
$env:POSTGRES_DB = 'entrega_i2_restaurada'
$env:DOCUMENT_STORAGE_ROOT = Join-Path $muestraRoot 'archivos-restaurados'
python manage.py migrate --check
if ($LASTEXITCODE -ne 0) { throw 'El esquema restaurado no corresponde al código' }
python manage.py muestra_entrega verificar --manifiesto "$muestraRoot/manifiesto.json"
if ($LASTEXITCODE -ne 0) { throw 'La muestra restaurada no coincide' }
```

`pg_dump`/`pg_restore` usan autenticación del cliente PostgreSQL (prompt o su
configuración privada); `POSTGRES_PASSWORD` es la variable de Django y no se
convierte automáticamente en contraseña del cliente. No escribirla en el comando.

La muestra contiene dos trámites, cuatro versiones documentales y sus bytes:
gasto aceptado con pago referido a v1 y reemplazo v2 sin revisión; facturación
cerrada con factura, cobro confirmado y respaldos aceptados. El manifiesto privado
compara huellas de todas las filas de los cuatro módulos, bytes y grupos de
usuarios; no contiene contraseñas. La verificación usa sesiones sintéticas para
comprobar descargas autorizadas y denegación ajena por HTTP. No demuestra login
por contraseña ni recuperación de credenciales. Su ejecución puede crear sesiones
y actualizar último acceso, sin modificar hechos de los circuitos.

`crear` exige demo habilitada, base sin usuarios/trámites, almacenamiento vacío y
manifiesto nuevo. No es idempotente ni repara una ejecución parcial; conservar el
fallo y repetir en destinos nuevos. `verificar` no restaura ni repara datos. Un
archivo faltante, alterado o un registro diferente impide dar el ensayo por válido.

El respaldo lógico **no incluye archivos**; copiar ambos mientras no haya
escrituras evita mezclas de momentos distintos. La muestra no mide RPO/RTO ni
certifica continuidad de producción. Para manifiestos de una operación documental
interrumpida, usar el [procedimiento de reconciliación](recorrido-facturacion-i2.md#fallos-y-recuperación)
con aplicación detenida; no confundirlo con restaurar el conjunto base/archivos.
Conservar los artefactos del ensayo en `.local/`, fuera de Git. No borrar ni
sobrescribir los datos originales para demostrar la recuperación.
