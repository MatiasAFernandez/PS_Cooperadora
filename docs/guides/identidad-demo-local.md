# Preparación local de identidad de demo I1

Esta guía usa sólo cuentas ficticias. El adaptador local permanece deshabilitado
salvo que `DEMO_IDENTITY_ENABLED=true` se configure de forma explícita en `.env`.
No usar este adaptador como inicio de sesión institucional ni cargar datos reales.

## Preparar las cuentas

1. Seguir la [puesta en marcha local](../../README.md) y ejecutar las migraciones.
2. En el `.env` local, establecer `DEMO_IDENTITY_ENABLED=true`.
3. Crear grupos y usuarios sin contraseña utilizable:

   ```powershell
   python manage.py preparar_identidad_demo
   ```

4. Establecer contraseñas distintas mediante los prompts interactivos de Django:

   ```powershell
   python manage.py changepassword demo_a
   python manage.py changepassword demo_b
   python manage.py changepassword demo_o
   python manage.py changepassword demo_l
   ```

   Guardar las contraseñas sólo en el entorno local de prueba. No pasarlas como
   argumentos, incorporarlas a archivos versionados ni compartirlas en el PR.

5. Iniciar Django y entrar en `/demo/acceso/`. Tras el ingreso, `/demo/` confirma
   el sujeto local. La salida se hace mediante el formulario POST de esa página.

El comando puede repetirse: conserva las contraseñas existentes y restablece la
asignación al único grupo de demo previsto para cada cuenta. Si encuentra una
cuenta homónima inactiva, staff, superusuaria o con grupos ajenos a la demo,
se detiene sin modificar ninguna cuenta. Revisar ese conflicto manualmente.

| Cuenta | Grupo | Capacidades |
|---|---|---|
| `demo_a`, `demo_b` | `demo_solicitante` | `gastos.presentar`, `gastos.consultar_propias` |
| `demo_o` | `demo_operadora` | `gastos.consultar_todas`, `gastos.decidir` |
| `demo_l` | `demo_lectura` | `gastos.consultar_todas` |

Las cuentas se preparan para demostrar permisos, no para definir cargos reales.
Al desactivar `DEMO_IDENTITY_ENABLED`, las sesiones previas dejan de producir un
actor y el formulario de acceso deja de estar disponible.

## Integración con gastos

El módulo de gastos importa `resolve_actor` y `has_capability` de
`identidad.services`. `resolve_actor` devuelve `None` sin sesión verificada o con
la demo deshabilitada; una cuenta activa sin grupos produce un actor sin
capacidades. `subject_id` es la clave local del usuario para las relaciones de
solicitante e historial. Las capacidades se recalculan desde grupos en cada
petición, sin inferirlas de `is_staff` o `is_superuser`.

Después de incorporar T02 a la rama de T03, retirar el importador dinámico
provisional de `gastos/auth.py` y usar estas funciones directamente. La
suite de T03 también debe sustituir las pruebas que suponen que T02 todavía
no existe por pruebas con las sesiones y grupos reales. La
presentación, visibilidad por objeto y decisiones siguen siendo reglas del
módulo de gastos. Verificar con sesiones reales: A ve sus gastos, B no ve los
de A, O y L consultan todos; L no puede decidir. El cierre de T03 requiere
estas comprobaciones sin dobles de identidad.
