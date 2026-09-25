
const $ = (sel) => document.querySelector(sel);

const vistaLogin = $("#vista-login");
const vistaPanel = $("#vista-panel");

const TEXTOS_ROL = {
  "Administrador": "Gestiona las cuentas del sistema: registra usuarios, asigna roles y activa o desactiva accesos.",
  "Técnico": "Aquí verás los tickets que te asignen para atenderlos y actualizar su estado.",
  "Solicitante": "Desde aquí podrás registrar incidencias de TI y hacer seguimiento a tus tickets."
};


const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function mostrarError(idCampo, mensaje) {
  const input = document.getElementById(idCampo);
  const error = document.querySelector(`[data-error-for="${idCampo}"]`);
  input.closest(".campo").classList.toggle("campo--invalido", !!mensaje);
  input.setAttribute("aria-invalid", mensaje ? "true" : "false");
  if (error) error.textContent = mensaje || "";
}

function limpiarErrores(form) {
  form.querySelectorAll("input, select").forEach(el => {
    if (el.id) mostrarError(el.id, "");
  });
}

function mostrarAlerta(el, mensaje, tipo = "error") {
  el.textContent = mensaje;
  el.classList.toggle("alerta--ok", tipo === "ok");
  el.hidden = !mensaje;
}


document.querySelectorAll(".btn-ver").forEach(boton => {
  boton.addEventListener("click", () => {
    const input = document.getElementById(boton.dataset.toggle);
    const oculto = input.type === "password";
    input.type = oculto ? "text" : "password";
    boton.textContent = oculto ? "Ocultar" : "Mostrar";
    boton.setAttribute("aria-label", oculto ? "Ocultar contraseña" : "Mostrar contraseña");
  });
});


const formLogin = $("#form-login");
const alertaLogin = $("#login-alerta");
const btnLogin = $("#btn-login");

formLogin.addEventListener("submit", async (e) => {
  e.preventDefault();
  limpiarErrores(formLogin);
  mostrarAlerta(alertaLogin, "");

  const email = $("#login-email").value.trim();
  const password = $("#login-password").value;
  let valido = true;

  if (!email) { mostrarError("login-email", "Escribe tu correo."); valido = false; }
  else if (!EMAIL_RE.test(email)) { mostrarError("login-email", "El correo no tiene un formato válido."); valido = false; }
  if (!password) { mostrarError("login-password", "Escribe tu contraseña."); valido = false; }

  if (!valido) return;

  btnLogin.disabled = true;
  btnLogin.textContent = "Verificando…";
  try {
    const sesion = await Auth.login(email, password);
    formLogin.reset();
    mostrarPanel(sesion);
  } catch (err) {
    mostrarAlerta(alertaLogin, err.message);
    $("#login-password").value = "";
    $("#login-password").focus();
  } finally {
    btnLogin.disabled = false;
    btnLogin.textContent = "Iniciar sesión";
  }
});


$("#btn-logout").addEventListener("click", async () => {
  await Auth.logout();
  mostrarLogin();
});


function mostrarLogin(mensaje) {
  vistaPanel.hidden = true;
  vistaLogin.hidden = false;
  document.title = "Mesa de Ayuda TI · Iniciar sesión";
  if (mensaje) mostrarAlerta(alertaLogin, mensaje);
  $("#login-email").focus();
}

function mostrarPanel(sesion) {
  vistaLogin.hidden = true;
  vistaPanel.hidden = false;
  document.title = "Mesa de Ayuda TI · Panel";

  $("#panel-nombre").textContent = sesion.nombre;
  const rol = $("#panel-rol");
  rol.textContent = sesion.rol;
  rol.className = "rol rol--" + sesion.rol;

  const primerNombre = sesion.nombre.split(" ")[0];
  $("#bienvenida-titulo").textContent = `Hola, ${primerNombre}`;
  $("#bienvenida-texto").textContent = TEXTOS_ROL[sesion.rol] || "";
  $("#panel-expira").textContent = sesion.expira.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });

  const esAdmin = sesion.rol === Auth.ROLES.ADMIN;
  $("#seccion-admin").hidden = !esAdmin;
  if (esAdmin) renderizarUsuarios();
}


const tablaUsuarios = $("#tabla-usuarios");

async function renderizarUsuarios() {
  try {
    const usuarios = await Auth.listarUsuarios();
    const idActual = Auth.obtenerSesion().id;
    tablaUsuarios.innerHTML = "";

    usuarios.forEach(u => {
      const fila = document.createElement("tr");
      if (!u.activo) fila.classList.add("inactivo");

      const celdas = [u.nombre, u.email, u.rol];
      celdas.forEach(texto => {
        const td = document.createElement("td");
        td.textContent = texto;
        fila.appendChild(td);
      });

      const tdEstado = document.createElement("td");
      tdEstado.innerHTML = `<span class="punto ${u.activo ? "" : "punto--inactivo"}">${u.activo ? "Activo" : "Inactivo"}</span>`;
      fila.appendChild(tdEstado);

      const tdAccion = document.createElement("td");
      if (u.id !== idActual) {
        const boton = document.createElement("button");
        boton.className = "btn btn--linea btn--mini";
        boton.textContent = u.activo ? "Desactivar" : "Activar";
        boton.addEventListener("click", () => cambiarEstado(u.id, !u.activo));
        tdAccion.appendChild(boton);
      } else {
        tdAccion.innerHTML = `<small style="color:var(--gris)">Tu cuenta</small>`;
      }
      fila.appendChild(tdAccion);

      tablaUsuarios.appendChild(fila);
    });
  } catch (err) {
    manejarErrorSesion(err);
  }
}

async function cambiarEstado(id, activo) {
  try {
    await Auth.cambiarEstado(id, activo);
    renderizarUsuarios();
  } catch (err) {
    manejarErrorSesion(err);
  }
}

const formRegistro = $("#form-registro");
const alertaRegistro = $("#registro-alerta");

formRegistro.addEventListener("submit", async (e) => {
  e.preventDefault();
  limpiarErrores(formRegistro);
  mostrarAlerta(alertaRegistro, "");

  const datos = {
    nombre: $("#reg-nombre").value.trim(),
    email: $("#reg-email").value.trim(),
    password: $("#reg-password").value,
    rol: $("#reg-rol").value
  };
  let valido = true;

  if (datos.nombre.length < 3) { mostrarError("reg-nombre", "Escribe el nombre completo."); valido = false; }
  if (!EMAIL_RE.test(datos.email)) { mostrarError("reg-email", "Escribe un correo válido."); valido = false; }
  if (datos.password.length < 8 || !/[A-Za-z]/.test(datos.password) || !/\d/.test(datos.password)) {
    mostrarError("reg-password", "La contraseña necesita 8 caracteres, una letra y un número.");
    valido = false;
  }
  if (!datos.rol) { mostrarError("reg-rol", "Elige un rol."); valido = false; }

  if (!valido) return;

  try {
    const nuevo = await Auth.registrarUsuario(datos);
    formRegistro.reset();
    mostrarAlerta(alertaRegistro, `Usuario registrado: ${nuevo.nombre} (${nuevo.rol}).`, "ok");
    renderizarUsuarios();
  } catch (err) {
    if (err.message.includes("correo")) mostrarError("reg-email", err.message);
    else manejarErrorSesion(err, alertaRegistro);
  }
});

function manejarErrorSesion(err, alerta) {
  if (!Auth.obtenerSesion()) {
    mostrarLogin("Tu sesión terminó. Inicia sesión de nuevo.");
  } else if (alerta) {
    mostrarAlerta(alerta, err.message);
  } else {
    alert(err.message);
  }
}


(function iniciar() {
  const sesion = Auth.obtenerSesion();
  if (sesion) mostrarPanel(sesion);
  else mostrarLogin();
})();
