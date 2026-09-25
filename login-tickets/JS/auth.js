
const CONFIG = {
  API_URL: "http://localhost:5000/api",
  USE_MOCK: true,
  TOKEN_MINUTOS: 60
};

const ROLES = {
  ADMIN: "Administrador",
  TECNICO: "Técnico",
  SOLICITANTE: "Solicitante"
};

const CLAVES = {
  usuarios: "tk_usuarios",
  token: "tk_token",
  listaNegra: "tk_tokens_revocados"
};


function b64urlEncode(texto) {
  return btoa(unescape(encodeURIComponent(texto)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(texto) {
  let b64 = texto.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  return decodeURIComponent(escape(atob(b64)));
}

function decodificarToken(token) {
  try {
    const partes = token.split(".");
    if (partes.length !== 3) return null;
    return JSON.parse(b64urlDecode(partes[1]));
  } catch {
    return null;
  }
}

async function hashTexto(texto) {
  if (window.crypto && crypto.subtle) {
    const datos = new TextEncoder().encode(texto);
    const buffer = await crypto.subtle.digest("SHA-256", datos);
    return [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, "0")).join("");
  }

  let h = 0;
  for (let i = 0; i < texto.length; i++) h = (h * 31 + texto.charCodeAt(i)) | 0;
  return "fb" + (h >>> 0).toString(16);
}

function leerJSON(clave, porDefecto) {
  try {
    const valor = localStorage.getItem(clave);
    return valor ? JSON.parse(valor) : porDefecto;
  } catch {
    return porDefecto;
  }
}

function guardarJSON(clave, valor) {
  localStorage.setItem(clave, JSON.stringify(valor));
}


const Mock = {
  async inicializar() {
    if (leerJSON(CLAVES.usuarios, null)) return;
    const base = [
      { nombre: "Ana Torres",    email: "admin@tickets.com",   password: "Admin123",   rol: ROLES.ADMIN },
      { nombre: "Luis Quispe",   email: "tecnico@tickets.com", password: "Tecnico123", rol: ROLES.TECNICO },
      { nombre: "María Sánchez", email: "usuario@tickets.com", password: "Usuario123", rol: ROLES.SOLICITANTE }
    ];
    const usuarios = [];
    for (let i = 0; i < base.length; i++) {
      usuarios.push({
        id: i + 1,
        nombre: base[i].nombre,
        email: base[i].email,
        password_hash: await hashTexto(base[i].password),
        rol: base[i].rol,
        activo: true
      });
    }
    guardarJSON(CLAVES.usuarios, usuarios);
  },

  async crearToken(usuario) {
    const ahora = Math.floor(Date.now() / 1000);
    const header = { alg: "HS256", typ: "JWT" };
    const payload = {
      sub: usuario.id,
      nombre: usuario.nombre,
      email: usuario.email,
      rol: usuario.rol,
      iat: ahora,
      exp: ahora + CONFIG.TOKEN_MINUTOS * 60,
      jti: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random()
    };
    const cuerpo = b64urlEncode(JSON.stringify(header)) + "." + b64urlEncode(JSON.stringify(payload));
    const firma = b64urlEncode(await hashTexto(cuerpo + "clave-secreta-demo"));
    return cuerpo + "." + firma;
  },

  async login(email, password) {
    await this.inicializar();
    const usuarios = leerJSON(CLAVES.usuarios, []);
    const usuario = usuarios.find(u => u.email === email.trim().toLowerCase());
    const hash = await hashTexto(password);

    if (!usuario || usuario.password_hash !== hash) {
      throw new Error("Correo o contraseña incorrectos.");
    }
    if (!usuario.activo) {
      throw new Error("Tu cuenta está inactiva. Pide al administrador que la active.");
    }
    return { access_token: await this.crearToken(usuario) };
  },

  logout(token) {
    const payload = decodificarToken(token);
    if (!payload) return;
    const revocados = leerJSON(CLAVES.listaNegra, []);
    revocados.push(payload.jti);
    guardarJSON(CLAVES.listaNegra, revocados);
  },

  estaRevocado(token) {
    const payload = decodificarToken(token);
    return !payload || leerJSON(CLAVES.listaNegra, []).includes(payload.jti);
  },

  listarUsuarios() {
    return leerJSON(CLAVES.usuarios, []).map(({ password_hash, ...u }) => u);
  },

  async registrarUsuario({ nombre, email, password, rol }) {
    const usuarios = leerJSON(CLAVES.usuarios, []);
    const correo = email.trim().toLowerCase();
    if (usuarios.some(u => u.email === correo)) {
      throw new Error("Ya existe un usuario con ese correo.");
    }
    const nuevo = {
      id: usuarios.reduce((max, u) => Math.max(max, u.id), 0) + 1,
      nombre: nombre.trim(),
      email: correo,
      password_hash: await hashTexto(password),
      rol,
      activo: true
    };
    usuarios.push(nuevo);
    guardarJSON(CLAVES.usuarios, usuarios);
    const { password_hash, ...publico } = nuevo;
    return publico;
  },

  cambiarEstado(id, activo) {
    const usuarios = leerJSON(CLAVES.usuarios, []);
    const usuario = usuarios.find(u => u.id === id);
    if (!usuario) throw new Error("Usuario no encontrado.");
    usuario.activo = activo;
    guardarJSON(CLAVES.usuarios, usuarios);
  }
};

async function peticionAPI(ruta, opciones = {}) {
  const token = localStorage.getItem(CLAVES.token);
  const respuesta = await fetch(CONFIG.API_URL + ruta, {
    ...opciones,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(opciones.headers || {})
    }
  });
  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.mensaje || datos.msg || "No se pudo completar la solicitud (" + respuesta.status + ").");
  }
  return datos;
}

const Auth = {
  ROLES,

  async login(email, password) {
    const datos = CONFIG.USE_MOCK
      ? await Mock.login(email, password)
      : await peticionAPI("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

    localStorage.setItem(CLAVES.token, datos.access_token);
    return this.obtenerSesion();
  },

  async logout() {
    const token = localStorage.getItem(CLAVES.token);
    try {
      if (token) {
        if (CONFIG.USE_MOCK) Mock.logout(token);
        else await peticionAPI("/auth/logout", { method: "POST" });
      }
    } finally {
      localStorage.removeItem(CLAVES.token);
    }
  },

  obtenerSesion() {
    const token = localStorage.getItem(CLAVES.token);
    if (!token) return null;

    const payload = decodificarToken(token);
    const expirado = !payload || payload.exp * 1000 < Date.now();
    const revocado = CONFIG.USE_MOCK && Mock.estaRevocado(token);

    if (expirado || revocado) {
      localStorage.removeItem(CLAVES.token);
      return null;
    }
    return {
      id: payload.sub,
      nombre: payload.nombre,
      email: payload.email,
      rol: payload.rol,
      expira: new Date(payload.exp * 1000)
    };
  },

  tieneRol(...roles) {
    const sesion = this.obtenerSesion();
    return !!sesion && roles.includes(sesion.rol);
  },

  exigirRol(...roles) {
    if (!this.tieneRol(...roles)) {
      throw new Error("No tienes permiso para realizar esta acción.");
    }
  },

  async listarUsuarios() {
    this.exigirRol(ROLES.ADMIN);
    return CONFIG.USE_MOCK ? Mock.listarUsuarios() : peticionAPI("/users");
  },

  async registrarUsuario(datos) {
    this.exigirRol(ROLES.ADMIN);
    return CONFIG.USE_MOCK
      ? Mock.registrarUsuario(datos)
      : peticionAPI("/users", { method: "POST", body: JSON.stringify(datos) });
  },

  async cambiarEstado(id, activo) {
    this.exigirRol(ROLES.ADMIN);
    if (this.obtenerSesion().id === id && !activo) {
      throw new Error("No puedes desactivar tu propia cuenta.");
    }
    return CONFIG.USE_MOCK
      ? Mock.cambiarEstado(id, activo)
      : peticionAPI("/users/" + id + "/estado", { method: "PATCH", body: JSON.stringify({ activo }) });
  }
};
