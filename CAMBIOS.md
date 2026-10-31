# Cambios de la versión 2.1 (sobre la rama main del equipo)

Las interfaces se mantienen. Solo se cambió el HTML donde había datos de ejemplo escritos a mano
(Usuarios y Mis tickets) para llenarlo con datos reales, y se agregó la pantalla **Empresas** y su
enlace en el menú para el superusuario.

## Base de datos
- Sin triggers, sin procedimientos y **sin vistas**: las consultas de las vistas están en `vistas.py`.
- Rol **Superusuario** (sin empresa) y las 6 empresas con el correo de su contacto como administrador
  (Grupo M&M, Agrofutura, EPSEL, Clínica Provida, Atlántica, Ángel Divino Bus).
- Hora de Perú en cada conexión (`SET time_zone = '-05:00'`): en PythonAnywhere ya no se adelanta 5 h.
- Credenciales solo en `.env` (antes estaban escritas en `db.py`).

## Módulo 1 — Autenticación y usuarios
- Login con **JWT** (cookie HttpOnly en la web, `Authorization: Bearer` en Postman), validado en cada petición.
- Cerrar sesión guarda el `jti` en `tokens_revocados`: el token deja de servir.
- Cada pantalla se protege por rol en el servidor (antes solo se ocultaba en el menú).
- Pantalla **Usuarios** conectada: crear (con contraseña temporal), editar, restablecer contraseña y activar/desactivar.
  El correo debe usar el dominio de la empresa y siempre queda al menos un administrador activo.
- **Superusuario**: crea empresas (con su administrador), las activa/desactiva, las elimina y entra a administrar cualquiera.

### Identidad visual por empresa
- Al iniciar sesión, la interfaz toma los **colores de la empresa** (tabla `empresas`): cabecera, menú lateral,
  opción activa, botones principales, enlaces, pestañas y fondo. El diseño es el mismo; solo cambian los colores.
  Antes `base.html` usaba una variable que nunca se enviaba y todas las empresas se veían igual.
- La paleta (tonos oscuros y claros) se calcula en Python a partir del color principal y el suave (`run.py`, `paleta_empresa`).
- El superusuario ve los colores originales y, al entrar a administrar una empresa, los de esa empresa.
- Si el administrador cambia los colores en **Configuración**, el cambio se ve al instante.

### Menú del perfil (arriba a la derecha)
- **Mi Perfil** (`/perfil`, todos los roles): datos del usuario, su actividad y **cambio de su propia contraseña**
  (pide la actual, mínimo 8 caracteres con letras y números).
- **Configuración** (`/configuracion`, administrador o superusuario dentro de una empresa): título del sistema,
  colores y logo de la empresa con vista previa, y áreas (agregar, activar/desactivar). Antes ambos enlaces apuntaban a `#`.

## Módulos 2 y 3 — Tickets, asignación, estados e historial
- Corregido: `detalle_ticket.js` y `tickets.js` declaraban las mismas constantes y se rompía el detalle.
- Nueva ruta de comentarios: el botón **Enviar** de Conversación y **Responder** ya funcionan.
- Agregar fotos desde el detalle (antes el recuadro no hacía nada; además decía PDF/DOCX y solo se aceptan imágenes).
- El solicitante puede **cerrar o reabrir** su ticket cuando está Resuelto.
- Prioridad y categoría solo las cambia el administrador o el técnico asignado, y el cambio queda en el historial.
- El técnico recibe aviso cuando otra persona cambia el estado de su ticket.
- Corregidas plantillas JS con `\${...}` que mostraban código en lugar de datos.
- Pestaña **Tareas** funcional (tabla nueva `ticket_tareas`): el administrador o el técnico asignado agregan,
  marcan y eliminan tareas; el solicitante las ve. Completar una tarea queda en el historial.
  El botón **Agregar tarea** del panel Acciones lleva a esa pestaña.
- Pestaña **Archivos** muestra las fotos del ticket y el clip del comentario adjunta una foto.

## Módulo 4 — SLA
- El semáforo se calcula en **Python** (`utils.calcular_sla`) con los plazos reales: Alta 4 h, Media 24 h, Baja 72 h
  (`sla.js` y el detalle usaban 8 h para Alta).
- Filtros de SLA con técnicos y categorías reales (antes eran nombres escritos a mano y estados que no existen).
- **Guardar configuración** guarda los plazos (solo el superusuario: son iguales para todas las empresas).
- Recuadro "SLA y tiempos" del detalle ahora se llena (se quedaba en "Calculando...").

## Módulo 5 — Notificaciones
- Texto de las notificaciones escapado (antes se podía inyectar HTML/JS desde el asunto de un ticket).

## Indicadores "vs. mes anterior"
- Antes eran porcentajes escritos a mano. Ahora `GET /api/tendencias` compara lo registrado este mes contra el
  mes anterior (tickets, usuarios y notificaciones) y `tendencias.js` llena cada tarjeta. Al pasar el mouse
  se ven las dos cantidades. En abiertos, vencidos y pendientes bajar se muestra en verde.

## Módulo 6 — Dashboard, reportes y API
- **Reportes** ya carga (el JS se caía buscando botones que no existen).
- **Exportar a Excel** genera un `.xlsx` real (openpyxl) y **Exportar a PDF** un PDF real (ReportLab), con los filtros elegidos.
- Columna "Fecha de resolución" usa `fecha_resolucion` (antes la fecha de última modificación).
- Rutas de Postman protegidas con JWT; `api_insertar_user` hashea la contraseña con bcrypt y valida el dominio;
  `api_insertar_ticket` toma el solicitante del token; `api_insertar_evidencia` sube la foto real.

## Módulo 1 (investigación) — Inicio de sesión con reconocimiento facial
- face-api.js 1.7.13 (TensorFlow.js) + cámara del navegador; librería y modelos en `static/vendor/face-api` y `static/models`.
- Registro del rostro en **Mi Perfil** (pide la contraseña actual, 3 capturas, se guarda el promedio del descriptor).
- Login facial como alternativa: antes de encender la cámara se verifica que la cuenta tenga rostro registrado.
- Distancia euclidiana en el servidor (`facial.py`), umbral 0,45 (promedio de 3 cuadros); 5 fallos en 15 min bloquean el login facial.
- Tablas `usuario_rostros` y `login_facial_intentos`; `migrar_facial.py` las crea sin borrar datos.
- Explicación para la sustentación: `docs/Investigacion_Login_Facial.pdf`.
