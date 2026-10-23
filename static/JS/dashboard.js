
document.addEventListener("DOMContentLoaded", () => {
  const dataElement = document.getElementById("dashboard-data");
  const feedback = document.getElementById("filter-feedback");
  const form = document.getElementById("filters-form");
  const desdeInput = document.getElementById("desde");
  const hastaInput = document.getElementById("hasta");
  const areaInput = document.getElementById("area");

  if (!dataElement) {
    if (feedback) {
      feedback.textContent = "No se pudieron cargar los datos del dashboard.";
    }
    return;
  }

  let datos;

  try {
    datos = JSON.parse(dataElement.textContent);
  } catch (error) {
    console.error("Error al leer los datos del dashboard:", error);
    if (feedback) feedback.textContent = "Error al leer los datos.";
    return;
  }

  const tickets = datos.todos_tickets || [];
  const recientesIniciales = datos.recientes || [];

  const palette = {
    blue: "#3479d9",
    lightBlue: "#75b8f8",
    green: "#31bd91",
    slate: "#637b93",
    teal: "#2499a7",
    gray: "#a5b8cb"
  };

  const charts = {};

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          usePointStyle: true,
          boxWidth: 8,
          padding: 14,
          color: "#28466e",
          font: { family: "Figtree", size: 11 }
        }
      }
    }
  };

  function crearGrafico(id, tipo, labels, valores, colores, opciones = {}) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;

    if (charts[id]) {
      charts[id].destroy();
    }

    charts[id] = new Chart(canvas, {
      type: tipo,
      data: {
        labels,
        datasets: [{
          data: valores,
          backgroundColor: colores,
          borderWidth: 0,
          borderRadius: tipo === "bar" ? 5 : 0,
          maxBarThickness: 48
        }]
      },
      options: {
        ...commonOptions,
        ...opciones
      }
    });
  }

  function fechaLocal(valor) {
    if (!valor) return null;

    // Admite fechas SQL y fechas ISO.
    const texto = String(valor).replace(" ", "T");
    const fecha = new Date(texto);

    if (Number.isNaN(fecha.getTime())) {
      return String(valor).slice(0, 10);
    }

    const anio = fecha.getFullYear();
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");

    return `${anio}-${mes}-${dia}`;
  }

  function aplicarFiltros() {
    const desde = desdeInput.value;
    const hasta = hastaInput.value;
    const areaSeleccionada = areaInput.value;

    if (desde && hasta && desde > hasta) {
      if (feedback) {
        feedback.textContent =
          "La fecha inicial no puede ser posterior a la fecha final.";
      }
      return;
    }

    const filtrados = tickets.filter(ticket => {
      const fechaTicket = fechaLocal(ticket.created_at);

      if (desde && (!fechaTicket || fechaTicket < desde)) {
        return false;
      }

      if (hasta && (!fechaTicket || fechaTicket > hasta)) {
        return false;
      }

      if (
        areaSeleccionada !== "todas" &&
        (ticket.area || "") !== areaSeleccionada
      ) {
        return false;
      }

      return true;
    });

    actualizarKpis(filtrados);
    actualizarGraficos(filtrados);
    actualizarTabla(filtrados);

    if (feedback) {
      const filtrosActivos = [];

      if (desde) filtrosActivos.push(`desde ${desde}`);
      if (hasta) filtrosActivos.push(`hasta ${hasta}`);
      if (areaSeleccionada !== "todas") {
        filtrosActivos.push(`área: ${areaSeleccionada}`);
      }

      feedback.textContent = filtrosActivos.length
        ? `${filtrados.length} tickets encontrados (${filtrosActivos.join(", ")})`
        : `Mostrando todos los tickets de la empresa: ${filtrados.length}`;
    }
  }

  function actualizarKpis(lista) {
    const total = lista.length;
    const abiertos = lista.filter(t => t.estado === "Abierto").length;
    const resueltos = lista.filter(t => t.estado === "Resuelto").length;

    const ahora = new Date();

    const vencidos = lista.filter(t => {
      if (!t.fecha_limite) return false;
      if (["Resuelto", "Cerrado"].includes(t.estado)) return false;

      const fechaLimite = new Date(
        String(t.fecha_limite).replace(" ", "T")
      );

      return !Number.isNaN(fechaLimite.getTime()) &&
        fechaLimite < ahora;
    }).length;

    document.getElementById("total-tickets").textContent = total;
    document.getElementById("open-tickets").textContent = abiertos;
    document.getElementById("resolved-tickets").textContent = resueltos;
    document.getElementById("late-tickets").textContent = vencidos;
  }

  function contarPor(lista, propiedad, etiquetaSinDato = "Sin especificar") {
    const conteo = {};

    lista.forEach(ticket => {
      const etiqueta = ticket[propiedad] || etiquetaSinDato;
      conteo[etiqueta] = (conteo[etiqueta] || 0) + 1;
    });

    return Object.entries(conteo).sort((a, b) => b[1] - a[1]);
  }

  function actualizarGraficos(lista) {
    const estados = contarPor(lista, "estado");
    crearGrafico(
      "statusChart",
      "doughnut",
      estados.map(x => x[0]),
      estados.map(x => x[1]),
      [palette.blue, palette.lightBlue, palette.green, palette.slate],
      { cutout: "60%" }
    );

    const prioridades = contarPor(lista, "prioridad");
    crearGrafico(
      "priorityChart",
      "bar",
      prioridades.map(x => x[0]),
      prioridades.map(x => x[1]),
      [palette.blue, palette.lightBlue, palette.slate],
      {
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#28466e" }
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#e8f0fa" }
          }
        }
      }
    );

    const tecnicos = contarPor(lista, "tecnico", "Sin asignar");
    crearGrafico(
      "technicianChart",
      "bar",
      tecnicos.slice(0, 8).map(x => x[0]),
      tecnicos.slice(0, 8).map(x => x[1]),
      [palette.blue, "#4c91ed", "#5ca2f5", "#72b1fa", palette.gray],
      {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "#e8f0fa" }
          },
          y: {
            grid: { display: false },
            ticks: { color: "#28466e" }
          }
        }
      }
    );

    const categorias = contarPor(lista, "categoria");
    crearGrafico(
      "categoryChart",
      "doughnut",
      categorias.map(x => x[0]),
      categorias.map(x => x[1]),
      [palette.blue, palette.lightBlue, palette.green, palette.teal, palette.gray],
      { cutout: "58%" }
    );
  }

  function actualizarTabla(lista) {
    const tbody = document.getElementById("recent-tickets");
    if (!tbody) return;

    tbody.replaceChildren();

    // Mostrar los cinco tickets más recientes del resultado filtrado.
    lista.slice(0, 5).forEach(ticket => {
      const fila = document.createElement("tr");

      const valores = [
        ticket.id,
        ticket.asunto || "Sin asunto",
        ticket.prioridad || "Sin prioridad",
        ticket.estado || "Sin estado",
        ticket.tecnico || "Sin asignar",
        fechaLocal(ticket.created_at) || "-"
      ];

      valores.forEach((valor, indice) => {
        const celda = document.createElement("td");
        celda.textContent = valor;

        if (indice === 2 || indice === 3) {
          const pill = document.createElement("span");
          pill.className = "pill";
          pill.textContent = valor;
          celda.replaceChildren(pill);
        }

        fila.appendChild(celda);
      });

      tbody.appendChild(fila);
    });

    if (lista.length === 0) {
      const fila = document.createElement("tr");
      const celda = document.createElement("td");

      celda.colSpan = 6;
      celda.textContent = "No hay tickets que coincidan con los filtros.";

      fila.appendChild(celda);
      tbody.appendChild(fila);
    }
  }

  // Al entrar, mostrar todos los tickets de la empresa sin filtros.
  actualizarKpis(tickets);
  actualizarGraficos(tickets);
  actualizarTabla(tickets);

  if (feedback) {
    feedback.textContent =
      `Mostrando todos los tickets de la empresa: ${tickets.length}`;
  }

  // Los filtros solo se aplican al pulsar el botón.
  if (form) {
    form.addEventListener("submit", event => {
      event.preventDefault();
      aplicarFiltros();
    });
  }

  // Búsqueda visual sobre la tabla actual.
  const globalSearch = document.querySelector(".global-search input");

  if (globalSearch) {
    globalSearch.addEventListener("input", () => {
      const query = globalSearch.value.trim().toLowerCase();

      document.querySelectorAll("#recent-tickets tr").forEach(fila => {
        fila.hidden = !fila.textContent.toLowerCase().includes(query);
      });
    });
  }
});
