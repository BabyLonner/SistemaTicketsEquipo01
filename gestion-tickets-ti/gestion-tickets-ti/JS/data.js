/* =========================================================
   data.js — Datos simulados del módulo 3
   Simula las tablas de la base de datos mientras no hay backend:
     - tecnicos
     - tickets
     - ticket_historial  (FK ticket_id → tickets.id, timestamp, comentario obligatorio)
   Los datos se guardan en localStorage para que no se pierdan al recargar.
   ========================================================= */

const DB_KEY = "mesaTI_modulo3";

/* Estados posibles del ticket */
const ESTADOS = ["Abierto", "En proceso", "Resuelto", "Cerrado"];

/* Transiciones permitidas (validación del UPDATE de estado) */
const TRANSICIONES = {
  "Abierto":    ["En proceso"],
  "En proceso": ["Resuelto", "Abierto"],
  "Resuelto":   ["Cerrado", "En proceso"],
  "Cerrado":    []
};

/* Longitud mínima del comentario obligatorio */
const MIN_COMENTARIO = 10;

/* Devuelve una fecha ISO de hace N minutos (solo para datos de ejemplo) */
function haceMinutos(min) {
  return new Date(Date.now() - min * 60000).toISOString();
}

function crearDatosIniciales() {
  const tecnicos = [
    { id: 1, nombre: "Carlos Mendoza", especialidad: "Redes y conectividad" },
    { id: 2, nombre: "Lucía Ramírez",  especialidad: "Soporte de hardware" },
    { id: 3, nombre: "Jorge Quispe",   especialidad: "Software y licencias" },
    { id: 4, nombre: "Andrea Salazar", especialidad: "Cuentas y accesos" }
  ];

  const tickets = [
    {
      id: 1, codigo: "TK-0101",
      titulo: "No hay conexión a internet en el laboratorio 3",
      descripcion: "Ninguna de las 30 PCs del laboratorio 3 tiene acceso a internet desde esta mañana. El resto del pabellón funciona normal.",
      solicitante: "María Torres", area: "Laboratorios", prioridad: "Alta",
      estado: "En proceso", tecnico_id: 1, creado: haceMinutos(300)
    },
    {
      id: 2, codigo: "TK-0102",
      titulo: "La impresora de secretaría no imprime",
      descripcion: "La impresora muestra el mensaje 'papel atascado' pero no hay papel dentro.",
      solicitante: "Rosa Chávez", area: "Secretaría académica", prioridad: "Media",
      estado: "Abierto", tecnico_id: null, creado: haceMinutos(45)
    },
    {
      id: 3, codigo: "TK-0103",
      titulo: "Instalar Office en PC de contabilidad",
      descripcion: "Se necesita Microsoft Office en la nueva computadora asignada a contabilidad.",
      solicitante: "Luis Vásquez", area: "Contabilidad", prioridad: "Baja",
      estado: "Resuelto", tecnico_id: 3, creado: haceMinutos(2880)
    },
    {
      id: 4, codigo: "TK-0104",
      titulo: "Olvidé la contraseña del correo institucional",
      descripcion: "No puedo ingresar al correo desde el viernes.",
      solicitante: "Pedro Castillo", area: "Recursos humanos", prioridad: "Media",
      estado: "Cerrado", tecnico_id: 4, creado: haceMinutos(10080)
    },
    {
      id: 5, codigo: "TK-0105",
      titulo: "El proyector del aula 204 no enciende",
      descripcion: "Al presionar el botón de encendido la luz parpadea en rojo y se apaga.",
      solicitante: "Ana Flores", area: "Docencia", prioridad: "Alta",
      estado: "Abierto", tecnico_id: 2, creado: haceMinutos(120)
    }
  ];

  /* Tabla ticket_historial */
  const historial = [
    // TK-0101
    { id: 1,  ticket_id: 1, tipo: "creacion",   estado_anterior: null, estado_nuevo: "Abierto",    tecnico_id: null, comentario: "Ticket registrado por el solicitante.", timestamp: haceMinutos(300) },
    { id: 2,  ticket_id: 1, tipo: "asignacion", estado_anterior: null, estado_nuevo: null,         tecnico_id: 1,    comentario: "Ticket asignado a Carlos Mendoza.",       timestamp: haceMinutos(280) },
    { id: 3,  ticket_id: 1, tipo: "estado",     estado_anterior: "Abierto", estado_nuevo: "En proceso", tecnico_id: 1, comentario: "Revisando el switch del laboratorio, parece que el puerto de uplink está dañado.", timestamp: haceMinutos(240) },
    // TK-0102
    { id: 4,  ticket_id: 2, tipo: "creacion",   estado_anterior: null, estado_nuevo: "Abierto",    tecnico_id: null, comentario: "Ticket registrado por el solicitante.", timestamp: haceMinutos(45) },
    // TK-0103
    { id: 5,  ticket_id: 3, tipo: "creacion",   estado_anterior: null, estado_nuevo: "Abierto",    tecnico_id: null, comentario: "Ticket registrado por el solicitante.", timestamp: haceMinutos(2880) },
    { id: 6,  ticket_id: 3, tipo: "asignacion", estado_anterior: null, estado_nuevo: null,         tecnico_id: 3,    comentario: "Ticket asignado a Jorge Quispe.",         timestamp: haceMinutos(2800) },
    { id: 7,  ticket_id: 3, tipo: "estado",     estado_anterior: "Abierto", estado_nuevo: "En proceso", tecnico_id: 3, comentario: "Descargando instalador con la licencia institucional.", timestamp: haceMinutos(1500) },
    { id: 8,  ticket_id: 3, tipo: "estado",     estado_anterior: "En proceso", estado_nuevo: "Resuelto", tecnico_id: 3, comentario: "Office instalado y activado. Se verificó Word y Excel con el usuario.", timestamp: haceMinutos(1440) },
    // TK-0104
    { id: 9,  ticket_id: 4, tipo: "creacion",   estado_anterior: null, estado_nuevo: "Abierto",    tecnico_id: null, comentario: "Ticket registrado por el solicitante.", timestamp: haceMinutos(10080) },
    { id: 10, ticket_id: 4, tipo: "asignacion", estado_anterior: null, estado_nuevo: null,         tecnico_id: 4,    comentario: "Ticket asignado a Andrea Salazar.",       timestamp: haceMinutos(10000) },
    { id: 11, ticket_id: 4, tipo: "estado",     estado_anterior: "Abierto", estado_nuevo: "En proceso", tecnico_id: 4, comentario: "Verificando identidad del usuario con RR.HH.", timestamp: haceMinutos(9900) },
    { id: 12, ticket_id: 4, tipo: "estado",     estado_anterior: "En proceso", estado_nuevo: "Resuelto", tecnico_id: 4, comentario: "Contraseña restablecida. El usuario ya puede ingresar.", timestamp: haceMinutos(9800) },
    { id: 13, ticket_id: 4, tipo: "estado",     estado_anterior: "Resuelto", estado_nuevo: "Cerrado", tecnico_id: 4, comentario: "El usuario confirmó que todo funciona. Se cierra el ticket.", timestamp: haceMinutos(8600) },
    // TK-0105
    { id: 14, ticket_id: 5, tipo: "creacion",   estado_anterior: null, estado_nuevo: "Abierto",    tecnico_id: null, comentario: "Ticket registrado por el solicitante.", timestamp: haceMinutos(120) },
    { id: 15, ticket_id: 5, tipo: "asignacion", estado_anterior: null, estado_nuevo: null,         tecnico_id: 2,    comentario: "Ticket asignado a Lucía Ramírez.",        timestamp: haceMinutos(90) }
  ];

  return { tecnicos, tickets, historial };
}

/* Lee la "base de datos" desde localStorage o crea los datos de ejemplo */
function cargarDB() {
  try {
    const guardado = localStorage.getItem(DB_KEY);
    if (guardado) return JSON.parse(guardado);
  } catch (e) {
    console.warn("No se pudo leer localStorage:", e);
  }
  const db = crearDatosIniciales();
  guardarDB(db);
  return db;
}

function guardarDB(db) {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(db));
  } catch (e) {
    console.warn("No se pudo guardar en localStorage:", e);
  }
}

function reiniciarDB() {
  try { localStorage.removeItem(DB_KEY); } catch (e) { /* sin acción */ }
  return cargarDB();
}
