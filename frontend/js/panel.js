const API = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
  ? 'http://127.0.0.1:5000'
  : 'https://TU-BACKEND.up.railway.app';
  
let token = null;

// ── LOGIN ──────────────────────────────────────────────
document.getElementById('btnLogin').addEventListener('click', async () => {
  console.log('click detectado');
  const email    = document.getElementById('inputEmail').value;
  const password = document.getElementById('inputPassword').value;
  console.log('email:', email);
  console.log('password:', password);
  console.log('email vacío:', !email);
  console.log('password vacío:', !password);

  if (!email || !password) {
      mostrarError(loginError, 'Completa todos los campos.');
      return;
  }

  console.log('pasó validación, haciendo fetch...');

  try {
    const respuesta = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    console.log('status:', respuesta.status);
    const datos = await respuesta.json();
    console.log('datos:', datos);

    if (!respuesta.ok) {
      mostrarError(loginError, datos.error || 'Credenciales inválidas.');
      return;
    }

    token = datos.token;
    console.log('token guardado, cambiando vista...');
    document.getElementById('nombreEmpleado').textContent = `${datos.nombre}`;
    document.getElementById('seccionLogin').classList.add('oculto');
    document.getElementById('seccionPanel').classList.remove('oculto');

    cargarProductosPanel();
    cargarAlertas();
    cargarMovimientos();

  } catch (e) {
    mostrarError(loginError, 'Error al conectar con el servidor.');
  }
});

document.getElementById('btnCerrarSesion').addEventListener('click', () => {
  token = null;
  document.getElementById('seccionLogin').classList.remove('oculto');
  document.getElementById('seccionPanel').classList.add('oculto');
  document.getElementById('inputPassword').value = '';
});

// ── CARGAR PRODUCTOS EN SELECTOR ───────────────────────
async function cargarProductosPanel() {
  try {
    const respuesta = await fetch(`${API}/productos`);
    const productos = await respuesta.json();

    const selectProducto = document.getElementById('selectProductoPanel');
    selectProducto.innerHTML = '';

    const ids = [];
    productos.forEach(p => {
      if (!ids.includes(p.id)) {
        ids.push(p.id);
        const opcion = document.createElement('option');
        opcion.value = p.id;
        opcion.textContent = p.nombre;
        selectProducto.appendChild(opcion);
      }
    });
  } catch (e) {
    console.error('Error cargando productos:', e);
  }
}

// ── ALERTAS ────────────────────────────────────────────
async function cargarAlertas() {
  const contenedor = document.getElementById('contenedorAlertas');
  try {
    const respuesta = await fetch(`${API}/inventario/alertas`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const datos = await respuesta.json();

    if (!datos.alertas.length) {
      contenedor.innerHTML = '<p style="color:#2e7d32"> Sin alertas de stock bajo.</p>';
      return;
    }

    let html = `
      <table class="tabla-alertas">
        <thead>
          <tr>
            <th>Producto</th>
            <th>Tienda</th>
            <th>Stock actual</th>
            <th>Umbral</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
    `;

    datos.alertas.forEach(a => {
      const badge = a.sin_stock
        ? '<span class="badge-sin-stock">Sin stock</span>'
        : '<span class="badge-bajo-panel">Stock bajo</span>';

      html += `
        <tr>
          <td>${a.producto}</td>
          <td>${a.tienda}</td>
          <td>${a.stock_disponible}</td>
          <td>${a.umbral_minimo}</td>
          <td>${badge}</td>
        </tr>
      `;
    });

    html += '</tbody></table>';
    contenedor.innerHTML = html;

  } catch (e) {
    contenedor.innerHTML = '<p class="error-msg">Error cargando alertas.</p>';
  }
}

// ── REGISTRAR MOVIMIENTO ───────────────────────────────
document.getElementById('btnRegistrar').addEventListener('click', async () => {
  const tienda_id   = document.getElementById('selectTiendaPanel').value;
  const producto_id = document.getElementById('selectProductoPanel').value;
  const tipo        = document.getElementById('selectTipo').value;
  const cantidad    = parseInt(document.getElementById('inputCantidadPanel').value);
  const mensaje     = document.getElementById('mensajeMovimiento');

  if (!cantidad || cantidad <= 0) {
    mostrarMensaje(mensaje, 'La cantidad debe ser mayor a cero.', false);
    return;
  }

  try {
    const respuesta = await fetch(`${API}/inventario/movimiento`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        producto_id: parseInt(producto_id),
        tienda_id:   parseInt(tienda_id),
        tipo,
        cantidad
      })
    });

    const datos = await respuesta.json();

    if (!respuesta.ok) {
      mostrarMensaje(mensaje, datos.error, false);
      return;
    }

    let texto = `${datos.mensaje} — Stock: ${datos.stock_anterior} → ${datos.stock_nuevo}`;
    if (datos.alerta) texto += ` | ${datos.alerta}`;

    mostrarMensaje(mensaje, texto, true);
    cargarAlertas();
    cargarMovimientos();

  } catch (e) {
    mostrarMensaje(mensaje, 'Error al conectar con el servidor.', false);
  }
});

// ── MOVIMIENTOS RECIENTES ──────────────────────────────
async function cargarMovimientos() {
  const contenedor = document.getElementById('contenedorMovimientos');
  try {
    const respuesta = await fetch(`${API}/inventario/movimientos`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const movimientos = await respuesta.json();

    if (!movimientos.length) {
      contenedor.innerHTML = '<p class="cargando">Sin movimientos registrados.</p>';
      return;
    }

    let html = `
      <table class="tabla-movimientos">
        <thead>
          <tr>
            <th>Producto</th>
            <th>Tienda</th>
            <th>Tipo</th>
            <th>Cantidad</th>
            <th>Empleado</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
    `;

    movimientos.forEach(m => {
      const badge = m.tipo === 'entrada'
        ? '<span class="badge-entrada">Entrada</span>'
        : '<span class="badge-salida">Salida</span>';

      html += `
        <tr>
          <td>${m.producto}</td>
          <td>${m.tienda}</td>
          <td>${badge}</td>
          <td>${m.cantidad}</td>
          <td>${m.empleado}</td>
          <td>${m.fecha}</td>
        </tr>
      `;
    });

    html += '</tbody></table>';
    contenedor.innerHTML = html;

  } catch (e) {
    contenedor.innerHTML = '<p class="error-msg">Error cargando movimientos.</p>';
  }
}

// ── UTILIDADES ─────────────────────────────────────────
function mostrarError(elemento, texto) {
  elemento.textContent = texto;
  elemento.classList.remove('oculto');
}

function mostrarMensaje(elemento, texto, esOk) {
  elemento.textContent = texto;
  elemento.className   = esOk ? 'mensaje-ok' : 'mensaje-error';
  elemento.classList.remove('oculto');
  setTimeout(() => elemento.classList.add('oculto'), 5000);
}