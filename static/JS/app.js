/* =========================================================
   Mesa de Ayuda TI — JavaScript de interfaz
   ---------------------------------------------------------
   Solo interacción visual y navegación entre pantallas.
   No hay autenticación, base de datos ni envío de datos.
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {

  /* =======================================================
     INICIO: validaciones del formulario de acceso
     ======================================================= */
  const formLogin = document.getElementById("form-login");
  if (formLogin) {
    const correo = document.getElementById("correo");
    const clave = document.getElementById("clave");
    const recordar = document.getElementById("recordar");
    const btnIngresar = document.getElementById("btn-ingresar");
    const btnVer = document.getElementById("ver-clave");
    const avisoMayus = document.getElementById("aviso-mayus");
    const alerta = document.getElementById("login-alerta");
    const alertaTexto = document.getElementById("login-alerta-texto");
    const tarjeta = document.getElementById("login-card");
    const nota = document.getElementById("nota-cuentas");

    const REGEX_CORREO = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

    const validarCorreo = (valor) => {
      if (valor === "") return "Ingresa tu correo corporativo.";
      if (/\s/.test(valor)) return "El correo no puede contener espacios.";
      if (valor.length > 100) return "El correo no puede superar los 100 caracteres.";
      if (!REGEX_CORREO.test(valor)) return "Escribe un correo válido, por ejemplo nombre@empresa.com.";
      return "";
    };

    const validarClave = (valor) => {
      if (valor === "") return "Ingresa tu contraseña.";
      if (valor.length < 8) return "La contraseña debe tener al menos 8 caracteres.";
      if (valor.length > 64) return "La contraseña no puede superar los 64 caracteres.";
      return "";
    };

    const pintarCampo = (input, mensaje) => {
      const campo = input.closest(".campo");
      campo.classList.toggle("campo--error", mensaje !== "");
      campo.classList.toggle("campo--ok", mensaje === "");
      input.setAttribute("aria-invalid", mensaje !== "" ? "true" : "false");
      document.getElementById("error-" + input.id).textContent = mensaje;
      return mensaje === "";
    };

    const revisarCorreo = () => pintarCampo(correo, validarCorreo(correo.value.trim()));
    const revisarClave = () => pintarCampo(clave, validarClave(clave.value));

    const mostrarAlerta = (texto, tipo) => {
      alertaTexto.textContent = texto;
      alerta.className = "alerta-login" + (tipo === "exito" ? " alerta-login--exito" : "");
      alerta.hidden = false;
    };

    // Valida al salir del campo y, desde entonces, mientras se escribe
    [[correo, revisarCorreo], [clave, revisarClave]].forEach(([input, revisar]) => {
      input.addEventListener("blur", () => {
        if (input.value !== "") {
          input.dataset.tocado = "true";
          revisar();
        }
      });
      input.addEventListener("input", () => {
        alerta.hidden = true;
        if (input.dataset.tocado) revisar();
      });
    });

    correo.addEventListener("change", () => { correo.value = correo.value.trim(); });

    // Mostrar / ocultar contraseña
    btnVer.addEventListener("click", () => {
      const oculta = clave.type === "password";
      clave.type = oculta ? "text" : "password";
      btnVer.textContent = oculta ? "Ocultar" : "Mostrar";
      btnVer.setAttribute("aria-label", oculta ? "Ocultar contraseña" : "Mostrar contraseña");
      btnVer.setAttribute("aria-pressed", String(oculta));
      clave.focus();
    });

    // Aviso de Bloq Mayús
    ["keydown", "keyup"].forEach((evento) => {
      clave.addEventListener(evento, (e) => {
        if (e.getModifierState) avisoMayus.hidden = !e.getModifierState("CapsLock");
      });
    });
    clave.addEventListener("blur", () => { avisoMayus.hidden = true; });

    // ¿Olvidaste tu contraseña?
    document.getElementById("olvide-clave").addEventListener("click", () => {
      nota.classList.add("is-resaltada");
      setTimeout(() => nota.classList.remove("is-resaltada"), 2500);
    });

    // Recordar correo
    try {
      const guardado = localStorage.getItem("mesa_correo");
      if (guardado) { correo.value = guardado; recordar.checked = true; }
    } catch (e) { /* sin acceso a localStorage */ }

    formLogin.addEventListener("submit", (e) => {
      e.preventDefault();
      if (btnIngresar.disabled) return; // evita doble envío

      correo.dataset.tocado = "true";
      clave.dataset.tocado = "true";
      const correoOk = revisarCorreo();
      const claveOk = revisarClave();

      if (!correoOk || !claveOk) {
        mostrarAlerta("Revisa los campos marcados antes de continuar.");
        tarjeta.classList.remove("sacudir");
        void tarjeta.offsetWidth;
        tarjeta.classList.add("sacudir");
        (correoOk ? clave : correo).focus();
        return;
      }

      try {
        if (recordar.checked) localStorage.setItem("mesa_correo", correo.value.trim());
        else localStorage.removeItem("mesa_correo");
      } catch (err) { /* sin acceso a localStorage */ }

      btnIngresar.disabled = true;
      btnIngresar.classList.add("is-cargando");
      mostrarAlerta("Datos correctos. Iniciando sesión…", "exito");

      // Solo interfaz: simula la espera y pasa al dashboard
      setTimeout(() => { window.location.href = "dashboard.html"; }, 900);
    });
  }

  /* Los demás formularios no envían nada */
  document.querySelectorAll("form:not(#form-login)").forEach((form) => {
    form.addEventListener("submit", (e) => e.preventDefault());
  });

  /* Tickets: cada fila abre el detalle */
  document.querySelectorAll(".fila-enlace").forEach((fila) => {
    fila.addEventListener("click", () => {
      window.location.href = fila.dataset.href;
    });
  });

  /* Detalle: elegir miniatura de evidencia */
  const nombreEvidencia = document.getElementById("evidencia-nombre");
  document.querySelectorAll(".miniaturas button").forEach((boton) => {
    boton.addEventListener("click", () => {
      document.querySelectorAll(".miniaturas button").forEach((b) => b.classList.remove("is-activa"));
      boton.classList.add("is-activa");
      if (nombreEvidencia) nombreEvidencia.textContent = "Imagen completa · " + boton.dataset.nombre;
    });
  });

  /* Nuevo ticket: quitar la foto de ejemplo */
  document.querySelectorAll(".foto__quitar").forEach((boton) => {
    boton.addEventListener("click", () => boton.closest(".foto").remove());
  });

  /* Notificaciones: pestañas y "marcar como leída" (solo visual) */
  const lista = document.querySelector(".notificaciones");
  if (lista) {
    const pestanas = document.querySelectorAll(".pestana");
    const contador = document.getElementById("contador-notificaciones");
    let filtro = "todas";

    const actualizar = () => {
      const noLeidas = lista.querySelectorAll(".notificacion.no-leida").length;
      contador.textContent = noLeidas + " sin leer";
      document.querySelector('[data-filtro="no-leidas"]').textContent = "No leídas (" + noLeidas + ")";
      const badge = document.querySelector(".campana__badge");
      if (badge) {
        badge.textContent = noLeidas;
        badge.hidden = noLeidas === 0;
      }
      lista.querySelectorAll(".notificacion").forEach((item) => {
        item.hidden = filtro === "no-leidas" && !item.classList.contains("no-leida");
      });
    };

    const marcarLeida = (item) => {
      item.classList.remove("no-leida");
      const boton = item.querySelector(".notificacion__accion");
      if (boton) boton.outerHTML = '<span class="notificacion__leida">Leída</span>';
    };

    lista.addEventListener("click", (e) => {
      if (e.target.classList.contains("notificacion__accion")) {
        marcarLeida(e.target.closest(".notificacion"));
        actualizar();
      }
    });

    document.getElementById("marcar-todas").addEventListener("click", () => {
      lista.querySelectorAll(".notificacion.no-leida").forEach(marcarLeida);
      actualizar();
    });

    pestanas.forEach((pestana) => {
      pestana.addEventListener("click", () => {
        filtro = pestana.dataset.filtro;
        pestanas.forEach((p) => {
          p.classList.toggle("is-activa", p === pestana);
          p.setAttribute("aria-selected", p === pestana);
        });
        actualizar();
      });
    });
  }
});
