# Guía de puesta en marcha — Acceso local permanente

Guía técnica para configuración y verificación reproducible del adaptador de identidad local permanente ([SPEC-022](../specs/022-franco-acceso-local-administracion.md), contrato [identidad-local.md](../contracts/identidad-local.md)). Utilizar exclusivamente datos sintéticos.

## 1. Rutas HTTP disponibles (`/cuentas/`)

- `/cuentas/acceso/`: inicio de sesión local mediante correo electrónico y contraseña (`AccesoLocalForm`).
- `/cuentas/registro/`: formulario de registro público (nombre, correo y contraseña obligatorios; área habitual, CUIT/CUIL y legajo opcionales).
- `/cuentas/verificar/`: confirmación de correo mediante enlace firmado temporal; la visita prepara la confirmación y el POST verifica el buzón.
- `/cuentas/estado/`: consulta propia de estado de cuenta y visualización de mensajes neutros.
- `/cuentas/administracion/altas/`: bandeja administrativa para evaluar solicitudes pendientes (requiere `identidad.administrar_cuentas`).
- `/cuentas/recuperar/`: solicitud y confirmación de restablecimiento de contraseña (`TokenRecuperacionLocal`).
- `/cuentas/clave/`: cambio voluntario de contraseña para usuarios autenticados.
- `/cuentas/salida/`: cierre de sesión local por POST.

## 2. Configuración de entorno

- **Activación explícita**: configurar `LOCAL_IDENTITY_ENABLED=True`. La configuración `DEMO_IDENTITY_ENABLED` permanece independiente; cuentas locales pendientes o rechazadas no realizan fallback a demo.
- **URL pública base**: definir `LOCAL_PUBLIC_BASE_URL` con la URL canónica del host (ej. `http://127.0.0.1:8000`, sin subrutas ni barra final), requerida para la construcción de enlaces en correos.
- **Servicio de correo**: utiliza `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `EMAIL_USE_TLS`. Configurar las credenciales fuera de Git. Las pruebas usan el backend en memoria (`django.core.mail.backends.locmem.EmailBackend`), que no entrega correos reales. El envío real requiere SMTP configurado y verificado.

## 3. Base de datos y migraciones

Aplicar la migración inicial del componente sobre una base de datos local seleccionada conscientemente para desarrollo o pruebas:

```powershell
python manage.py migrate identidad
```

> [!CAUTION]
> Para verificar este incremento, utilizar una base aislada y preservar las bases y archivos existentes. En una instalación nueva, ejecutar `python manage.py migrate` para aplicar también las dependencias del sistema.

## 4. Comando de inicialización `preparar_cuenta_local`

Permite el bootstrap técnico explícito de un operador inicial o cuenta local aprobada sobre un usuario Django preexistente:

```powershell
python manage.py preparar_cuenta_local --username <usuario> --correo-verificado [--administrador]
```

### Requisitos y condiciones de uso
- **Usuario preexistente**: usar un usuario Django activo con correo previamente comprobado. Si es necesario crear el inicial, hacerlo desde `python manage.py shell` con `get_user_model().objects.create_user(...)`, sin asignar staff o superusuario; establecer después la clave mediante `python manage.py changepassword <usuario>`. El comando de preparación conserva la identidad y la contraseña existentes.
- **Estado del usuario**: debe encontrarse activo (`is_active=True`), con contraseña utilizable y correo electrónico válido sin colisiones con otras cuentas locales o usuarios.
- **Flags obligatorios y opcionales**:
  - `--correo-verificado`: confirmación obligatoria de que la casilla fue comprobada previamente por quien ejecuta.
  - `--administrador`: asigna el grupo `local_administracion` confiriendo únicamente la capacidad `identidad.administrar_cuentas` (no otorga staff ni superusuario).
- **Controles estrictos**: el comando no crea usuarios ni contraseñas, no reactiva usuarios inactivos y no aprueba por rutina cuentas que ya existan en estado `PENDIENTE` o `RECHAZADA` (las cuales deben resolverse mediante la bandeja administrativa).

## 5. Límites y pendientes

- La configuración SMTP de producción, la integración institucional ([SPEC-016](../specs/016-matias-preparacion-identidad-institucional.md)), la suspensión interactiva desde interfaz web y el ABM general de usuarios quedan pendientes de próximos incrementos.
- La evidencia final de verificación se registra en la PR y el handoff de la tarea, evitando reportes duplicados en la documentación compartida.

## 6. Alcance de la verificación del 12/11/2026

En la rama de tarea se aprobaron 22 pruebas del núcleo y 37 de regresión de identidad. La capa HTTP aprobó 10 pruebas antes del ajuste final de revocación. Después de ese ajuste aprobaron las dos pruebas específicas de recuperación y revocación tras suspensión/reactivación. Estos conjuntos se solapan y no se suman como casos distintos.

Se revisaron con datos sintéticos registro, sesión limitada, aprobación/rechazo, entrada a ambos circuitos y navegación en escritorio y móvil de 390 px. El cambio de contraseña se verificó mediante cliente HTTP, sin operar credenciales reales en navegador. El correo se simuló.

La corrida local ampliada de identidad y consumidores se interrumpió a los 85 segundos sin resumen final; esa ejecución no acredita una regresión completa. Posteriormente, el [CI 176](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/43296856407) completó con éxito sobre `a400486`, incluida la corrección de consultas del panel de Gastos. La [PR #111](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/111) se integró en `main` como `5673784` el 12/11/2026. La revisión compartida, el correo real y la validación institucional siguen pendientes; el CI no sustituye esas comprobaciones.
