
/* =========================================================
   Mesa de Ayuda TI - JavaScript de interfaz
   Validaciones visuales e interacciones del sistema.
   La autenticacion se realiza en el backend Flask.
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {

  /* =======================================================
     1. INICIO DE SESION
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

    const REGEX_CORREO =
      /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

    const validarCorreo = (valor) => {
      if (valor === "") return "Ingresa tu correo corporativo.";
      if (/\s/.test(valor)) return "El correo no puede contener espacios.";
      if (valor.length > 100) {
        return "El correo no puede superar los 100 caracteres.";
      }
      if (!REGEX_CORREO.test(valor)) {
        return "Escribe un correo válido, por ejemplo nombre@empresa.com.";
      }
      return "";
    };

    const validarClave = (valor) => {
      if (valor === "") return "Ingresa tu contraseña.";
      if (valor.length < 8) {
        return "La contraseña debe tener al menos 8 caracteres.";
      }
      if (valor.length > 64) {
        return "La contraseña no puede superar los 64 caracteres.";
      }
      return "";
    };

    const pintarCampo = (input, mensaje) => {
      const campo = input.closest(".campo");
      const error = document.getElementById("error-" + input.id);

      if (campo) {
        campo.classList.toggle("campo--error", mensaje !== "");
        campo.classList.toggle("campo--ok", mensaje === "");
      }

      input.setAttribute("aria-invalid", mensaje ? "true" : "false");

      if (error) {
        error.textContent = mensaje;
      }

      return mensaje === "";
    };

    const revisarCorreo = () =>
      pintarCampo(correo, validarCorreo(correo.value.trim()));

    const revisarClave = () =>
      pintarCampo(clave, validarClave(clave.value));

    const mostrarAlerta = (texto, tipo = "error") => {
      if (!alerta || !alertaTexto) return;

      alertaTexto.textContent = texto;
      alerta.className =
        "alerta-login" +
        (tipo === "exito" ? " alerta-login--exito" : "");

      alerta.hidden = false;
    };

    // Validacion al salir de los campos y mientras se escribe.
    [[correo, revisarCorreo], [clave, revisarClave]].forEach(
      ([input, revisar]) => {
        input.addEventListener("blur", () => {
          if (input.value !== "") {
            input.dataset.tocado = "true";
            revisar();
          }
        });

        input.addEventListener("input", () => {
          if (alerta) alerta.hidden = true;

          if (input.dataset.tocado) {
            revisar();
          }
        });
      }
    );

    correo.addEventListener("change", () => {
      correo.value = correo.value.trim();
    });

    // Mostrar u ocultar contrasena.
    if (btnVer) {
      btnVer.addEventListener("click", () => {
        const oculta = clave.type === "password";

        clave.type = oculta ? "text" : "password";
        btnVer.textContent = oculta ? "Ocultar" : "Mostrar";
        btnVer.setAttribute(
          "aria-label",
          oculta ? "Ocultar contrasena" : "Mostrar contrasena"
        );
        btnVer.setAttribute("aria-pressed", String(oculta));
        clave.focus();
      });
    }

    // Aviso de Bloq Mayus.
    if (avisoMayus) {
      ["keydown", "keyup"].forEach((evento) => {
        clave.addEventListener(evento, (e) => {
          if (e.getModifierState) {
            avisoMayus.hidden = !e.getModifierState("CapsLock");
          }
        });
      });

      clave.addEventListener("blur", () => {
        avisoMayus.hidden = true;
      });
    }

    // Ayuda para recuperar la contrasena.
    const botonOlvide = document.getElementById("olvide-clave");

    if (botonOlvide && nota) {
      botonOlvide.addEventListener("click", () => {
        nota.classList.add("is-resaltada");

        setTimeout(() => {
          nota.classList.remove("is-resaltada");
        }, 2500);
      });
    }

    // Recordar solamente el correo, nunca la contrasena.
    try {
      const guardado = localStorage.getItem("mesa_correo");

      if (guardado) {
        correo.value = guardado;
        recordar.checked = true;
      }
    } catch (error) {
      // El navegador puede bloquear localStorage.
    }

    // Enviar las credenciales al backend Flask.
    formLogin.addEventListener("submit", (e) => {
      e.preventDefault();

      if (btnIngresar.disabled) return;

      correo.dataset.tocado = "true";
      clave.dataset.tocado = "true";

      const correoOk = revisarCorreo();
      const claveOk = revisarClave();

      if (!correoOk || !claveOk) {
        mostrarAlerta("Revisa los campos marcados antes de continuar.");

        if (tarjeta) {
          tarjeta.classList.remove("sacudir");
          void tarjeta.offsetWidth;
          tarjeta.classList.add("sacudir");
        }

        (correoOk ? clave : correo).focus();
        return;
      }

      try {
        if (recordar && recordar.checked) {
          localStorage.setItem("mesa_correo", correo.value.trim());
        } else {
          localStorage.removeItem("mesa_correo");
        }
      } catch (error) {
        // El navegador puede bloquear localStorage.
      }

      // Flask debe recibir el formulario mediante POST.
      if (!formLogin.method || formLogin.method.toLowerCase() !== "post") {
        formLogin.method = "POST";
      }

      if (!formLogin.action) {
        formLogin.action = "/";
      }

      btnIngresar.disabled = true;
      btnIngresar.classList.add("is-cargando");

      const textoBoton = btnIngresar.querySelector(".btn__texto");

      if (textoBoton) {
        textoBoton.textContent = "Verificando...";
      }

      // Envio nativo: no vuelve a disparar este listener.
      HTMLFormElement.prototype.submit.call(formLogin);
    });
  }

  /* =======================================================
     2. LOS DEMAS FORMULARIOS
     ======================================================= */

  document.querySelectorAll("form:not(#form-login)").forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
    });
  });

  /* =======================================================
     3. NAVEGACION DE FILAS
     ======================================================= */

  document.querySelectorAll(".fila-enlace").forEach((fila) => {
    fila.addEventListener("click", () => {
      const destino = fila.dataset.href;

      if (destino) {
        window.location.href = destino;
      }
    });
  });

  /* =======================================================
     4. MINIATURAS DE EVIDENCIAS
     ======================================================= */

  const nombreEvidencia = document.getElementById("evidencia-nombre");

  document.querySelectorAll(".miniaturas button").forEach((boton) => {
    boton.addEventListener("click", () => {
      document.querySelectorAll(".miniaturas button").forEach((b) => {
        b.classList.remove("is-activa");
      });

      boton.classList.add("is-activa");

      if (nombreEvidencia) {
        nombreEvidencia.textContent =
          "Imagen completa · " + (boton.dataset.nombre || "");
      }
    });
  });

  /* =======================================================
     5. QUITAR FOTOGRAFIAS DE EJEMPLO
     ======================================================= */

  document.querySelectorAll(".foto__quitar").forEach((boton) => {
    boton.addEventListener("click", () => {
      const foto = boton.closest(".foto");

      if (foto) foto.remove();
    });
  });

  /* =======================================================
     6. NOTIFICACIONES VISUALES
     ======================================================= */

  const lista = document.querySelector(".notificaciones");

  if (lista) {
    const pestanas = document.querySelectorAll(".pestana");
    const contador = document.getElementById("contador-notificaciones");
    const botonMarcarTodas = document.getElementById("marcar-todas");
    const filtroNoLeidas = document.querySelector(
      '[data-filtro="no-leidas"]'
    );

    let filtro = "todas";

    const actualizar = () => {
      const noLeidas = lista.querySelectorAll(
        ".notificacion.no-leida"
      ).length;

      if (contador) {
        contador.textContent = noLeidas + " sin leer";
      }

      if (filtroNoLeidas) {
        filtroNoLeidas.textContent = "No leídas (" + noLeidas + ")";
      }

      const badge = document.querySelector(".campana__badge");

      if (badge) {
        badge.textContent = noLeidas;
        badge.hidden = noLeidas === 0;
      }

      lista.querySelectorAll(".notificacion").forEach((item) => {
        item.hidden =
          filtro === "no-leidas" &&
          !item.classList.contains("no-leida");
      });
    };

    const marcarLeida = (item) => {
      item.classList.remove("no-leida");

      const boton = item.querySelector(".notificacion__accion");

      if (boton) {
        const etiqueta = document.createElement("span");
        etiqueta.className = "notificacion__leida";
        etiqueta.textContent = "Leída";
        boton.replaceWith(etiqueta);
      }
    };

    lista.addEventListener("click", (e) => {
      const boton = e.target.closest(".notificacion__accion");

      if (boton && lista.contains(boton)) {
        marcarLeida(boton.closest(".notificacion"));
        actualizar();
      }
    });

    if (botonMarcarTodas) {
      botonMarcarTodas.addEventListener("click", () => {
        lista.querySelectorAll(".notificacion.no-leida").forEach(
          marcarLeida
        );

        actualizar();
      });
    }

    pestanas.forEach((pestana) => {
      pestana.addEventListener("click", () => {
        filtro = pestana.dataset.filtro || "todas";

        pestanas.forEach((p) => {
          const activa = p === pestana;

          p.classList.toggle("is-activa", activa);
          p.setAttribute("aria-selected", String(activa));
        });

        actualizar();
      });
    });

    actualizar();
  }
});
