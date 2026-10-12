# Reproduccion local de la demostracion tecnica I1

Guia de la Issue #8 (T06). Usar solo datos sinteticos. La demostracion muestra una
necesidad de gasto previa a un pago; no registra pagos, recibe archivos ni valida
reglas institucionales. Cada integrante debe ejecutar y registrar su propio
recorrido.

## Preparacion de PostgreSQL en Windows

Requisitos: Python 3.11 o 3.14, PostgreSQL 17 y un puerto local libre (el
ejemplo usa `55432`). La CI usa Python 3.11; Django 5.2.17 y Psycopg 3.3.5
tambien admiten Python 3.14. El servidor PostgreSQL se instala y ejecuta fuera
del entorno virtual de Python. El proyecto ya incluye el cliente `psycopg[binary]`
en `requirements/base.txt`.

**Opcion Podman:** requiere una maquina Linux funcional. Si
`podman machine start` falla con
`HCS_E_SERVICE_NOT_AVAILABLE`, comprobar `wsl --status`: Windows puede requerir
habilitar la caracteristica "Plataforma de maquina virtual" y la virtualizacion
en BIOS/UEFI. Esto puede requerir permisos de administrador y reinicio; no se
puede continuar con este contenedor hasta que la maquina inicie.
No borrar volumenes ni bases existentes para intentar resolver ese error.

Desde la raiz del repositorio, con `main` actualizada:

```powershell
$Podman = (Get-Command podman -ErrorAction SilentlyContinue).Source
if (-not $Podman) { $Podman = "$env:LOCALAPPDATA\Programs\Podman\podman.exe" }
& $Podman machine list
& $Podman machine start podman-machine-default
& $Podman run -d --name cooperadora-i1-demo-db `
  -e POSTGRES_DB=cooperadora `
  -e POSTGRES_USER=cooperadora `
  -e POSTGRES_PASSWORD=cooperadora_local `
  -p 127.0.0.1:55432:5432 postgres:17-alpine
& $Podman exec cooperadora-i1-demo-db pg_isready -U cooperadora -d cooperadora
```

Si el contenedor ya existe, comprobar su estado con `& $Podman ps -a` y
arrancarlo con `& $Podman start cooperadora-i1-demo-db`; no crear otro con el
mismo nombre. La clave del ejemplo es solo para esta base sintetica local, nunca
para un entorno real.

**Opcion nativa:** instalar [PostgreSQL 17 para Windows](https://www.postgresql.org/download/windows/)
como servicio separado, sin Podman ni WSL. Preparar una base y un usuario de
prueba que coincidan con `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD`
de `.env`; usar el puerto configurado en `POSTGRES_PORT`. No sobrescribir una
instancia o base existente. En ambas opciones, copiar `.env.example` si hace
falta, configurar el puerto correcto y `DEMO_IDENTITY_ENABLED=true`.

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) { py -3.11 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python --version
pip install -r requirements/dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Editar `.env` antes de continuar: definir `POSTGRES_PORT` segun la instancia
elegida y `DEMO_IDENTITY_ENABLED=true`. Luego ejecutar:

```powershell
python manage.py migrate
python manage.py preparar_identidad_demo
python manage.py changepassword demo_a
python manage.py changepassword demo_b
python manage.py changepassword demo_o
python manage.py changepassword demo_l
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
python manage.py runserver 127.0.0.1:8000
```

Definir las cuatro contrasenas distintas por
prompt, sin incorporarlas al repositorio, capturas o acta. Si el puerto `8000`
esta ocupado, usar otro puerto y conservar las mismas rutas.
El `.venv` existente con Python 3.14 puede reutilizarse. Si se crea uno nuevo
con 3.14, sustituir `py -3.11` por `py -3.14` en el comando anterior. Registrar
la version usada en el acta para compararla con CI.

## Recorrido en pantalla

1. Entrar en `http://127.0.0.1:8000/demo/acceso/` como `demo_a`. Desde
   `/gastos/presentar/`, crear una necesidad con concepto, importe positivo y
   unidad ficticios. Anotar su identificador. En el detalle debe figurar
   `Presentada` y "No se solicita documentación en esta etapa de la
   demostración".
2. Salir mediante el formulario de `/demo/` y entrar como `demo_o`. Abrir
   `/gastos/<id>/`, postergar con motivo y comprobar el evento en el historial.
   Recargar: el estado y el mensaje alternativo deben persistir. Aceptar luego
   esa misma solicitud y comprobar el segundo evento y el orden del historial.
3. Volver como `demo_a`. El detalle y la recarga deben mostrar ambos eventos y
   "Respaldo del gasto (presupuesto o factura): por aportar". Crear una segunda
   necesidad y anotar su identificador.
4. Como `demo_o`, rechazar la segunda necesidad con motivo. Como `demo_a`,
   comprobar historial y el mensaje alternativo tambien tras recargar.
5. Como `demo_b`, comprobar que la lista no contiene las solicitudes de A y que
   `/gastos/<id>/` responde 404. Como `demo_l`, comprobar que puede consultar
   ambas, pero no aparece una accion para decidir; un POST directo debe
   denegarse sin modificar estado ni historial.
6. La autodecision de un actor que combina capacidades se comprueba con CT-05:
   `demo_o` no tiene permiso para presentar, por lo que ese caso no se puede
   construir solo con las cuatro cuentas de pantalla. Verificar tambien en la
   suite CT-01 a CT-08, en particular la concurrencia real en PostgreSQL y CSRF.

No debe aparecer un error 500 sin controlar. Registrar commit, sistema, version
de Python y PostgreSQL, comandos/resultados, identificadores sinteticos,
capturas sin secretos, defectos y responsable de corregirlos. Franco y Matias
deben completar recorridos independientes antes de acordar el acta tecnica.
La validacion de H1-H4 con Cooperadora corresponde a la Issue #9.
