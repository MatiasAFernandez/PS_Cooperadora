# Recorrido local de facturación — #21/#23

Usar exclusivamente datos y documentos sintéticos. Este corte implementa
presentación, observación y corrección; no verifica ingresos ni emite facturas.
Las obligatoriedades del formulario relevado son perfil provisional de demo.

## Preparación

Desde una versión integrada que incluya #52/#59, con el entorno Python activado,
dependencias instaladas y PostgreSQL local configurado en .env (ver README):

```powershell
python manage.py migrate
python manage.py preparar_identidad_demo --facturacion
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

El pago declarado queda pendiente de verificación. No hay acciones de revisión
documental, registro de factura/cobro formal, cierre o anulación en estas pantallas.
Ambos circuitos usan la navegación y el parcial de historial comunes de #59.
Cada módulo conserva sus reglas de estado y permisos por objeto.

## Fallos y recuperación

Los servicios de presentación/corrección son dueños de la transacción exterior.
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
