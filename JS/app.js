/* =========================================================
   Mesa de Ayuda TI — JavaScript de interfaz
   ---------------------------------------------------------
   Solo interacción visual y navegación entre pantallas.
   No hay autenticación, base de datos ni envío de datos.
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {

  /* Inicio: "Ingresar" solo lleva al dashboard */
  const formLogin = document.getElementById("form-login");
  if (formLogin) {
    formLogin.addEventListener("submit", (e) => {
      e.preventDefault();
      window.location.href = "dashboard.html";
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
