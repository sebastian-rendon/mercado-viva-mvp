const API = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
  ? 'http://127.0.0.1:5000'
  : 'https://mercado-viva-mvp-production.up.railway.app';

let productoSeleccionado = null;
let intervaloContador   = null;

// ── CARGAR PRODUCTOS ───────────────────────────────────
const selectTienda      = document.getElementById('selectTienda');
const seccionProductos  = document.getElementById('seccionProductos');

selectTienda.addEventListener('change', () => {
  const tiendaId = selectTienda.value;
  if (!tiendaId) {
    seccionProductos.innerHTML = '<p class="cargando">Selecciona una tienda para ver los productos.</p>';
    return;
  }
  cargarProductos(tiendaId);
});

async function cargarProductos(tiendaId) {
  seccionProductos.innerHTML = '<p class="cargando">Cargando productos...</p>';
  try {
    const respuesta = await fetch(`${API}/productos?tienda_id=${tiendaId}`);
    const productos = await respuesta.json();

    if (!productos.length) {
      seccionProductos.innerHTML = '<p class="cargando">No hay productos disponibles.</p>';
      return;
    }

    seccionProductos.innerHTML = '<div class="grid-productos"></div>';
    const grid = seccionProductos.querySelector('.grid-productos');

    productos.forEach(p => {
      grid.appendChild(crearTarjeta(p));
    });

  } catch (e) {
    seccionProductos.innerHTML = '<p class="error-msg">Error al conectar con el servidor.</p>';
  }
}

function crearTarjeta(producto) {
  const tarjeta = document.createElement('div');
  tarjeta.classList.add('tarjeta');

  let claseStock = 'stock-ok';
  let badgeHTML  = '';

  if (producto.sin_disponibilidad) {
    claseStock = 'stock-cero';
    badgeHTML  = '<span class="badge-agotado">Sin disponibilidad</span>';
  } else if (producto.stock_bajo) {
    claseStock = 'stock-bajo';
    badgeHTML  = '<span class="badge-bajo">Ultimas unidades</span>';
  }

  tarjeta.innerHTML = `
    <div class="tarjeta-imagen">
      <img src="${obtenerImagen(producto.sku)}" alt="${producto.nombre}"/>
    </div>
    <div class="tarjeta-cuerpo">
      <h3>${producto.nombre}</h3>
      <span class="sku">SKU: ${producto.sku}</span>
      <span class="categoria">${producto.categoria}</span>
      <p class="stock ${claseStock}">Stock disponible: ${producto.stock_disponible}</p>
      <div class="badge-espacio">${badgeHTML}</div>
    </div>
    <button
      class="btn-agregar"
      ${producto.sin_disponibilidad ? 'disabled' : ''}
      data-id="${producto.id}"
      data-nombre="${producto.nombre}"
      data-stock="${producto.stock_disponible}"
      data-tienda="${selectTienda.value}"
    >
      ${producto.sin_disponibilidad ? 'Sin disponibilidad' : 'Agregar al carrito'}
    </button>
  `;

  tarjeta.querySelector('.btn-agregar').addEventListener('click', abrirModal);
  return tarjeta;
}

function obtenerImagen(sku) {
  const imagenes = {
    'ARR-001': 'img/arroz.png',
    'ACE-002': 'img/aceite.png',
    'LEC-003': 'img/leche.png',
  };
  return imagenes[sku] || 'img/default.png';
}

// ── MODAL DE RESERVA ───────────────────────────────────
const modalReserva       = document.getElementById('modalReserva');
const modalProductoNombre = document.getElementById('modalProductoNombre');
const modalStockDisponible = document.getElementById('modalStockDisponible');
const inputCantidad      = document.getElementById('inputCantidad');

document.getElementById('btnCancelarModal').addEventListener('click', () => {
  modalReserva.classList.add('oculto');
});

document.getElementById('btnConfirmarReserva').addEventListener('click', confirmarReserva);

function abrirModal(e) {
  const btn = e.currentTarget;
  productoSeleccionado = {
    id:      btn.dataset.id,
    nombre:  btn.dataset.nombre,
    stock:   parseInt(btn.dataset.stock),
    tienda:  btn.dataset.tienda
  };

  modalProductoNombre.textContent  = productoSeleccionado.nombre;
  modalStockDisponible.textContent = `Stock disponible: ${productoSeleccionado.stock} unidades`;
  inputCantidad.value = 1;
  inputCantidad.max   = productoSeleccionado.stock;

  modalReserva.classList.remove('oculto');
}

async function confirmarReserva() {
  const cantidad = parseInt(inputCantidad.value);

  if (cantidad <= 0 || cantidad > productoSeleccionado.stock) {
    alert(`Cantidad inválida. Máximo disponible: ${productoSeleccionado.stock}`);
    return;
  }

  try {
    const respuesta = await fetch(`${API}/reservas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        producto_id: parseInt(productoSeleccionado.id),
        tienda_id:   parseInt(productoSeleccionado.tienda),
        cantidad:    cantidad
      })
    });

    const datos = await respuesta.json();

    if (!respuesta.ok) {
      alert(`Error: ${datos.error}`);
      return;
    }

    modalReserva.classList.add('oculto');
    mostrarExito(datos);
    cargarProductos(selectTienda.value);

  } catch (e) {
    alert('Error al conectar con el servidor.');
  }
}

// ── MODAL DE ÉXITO + CONTADOR ──────────────────────────
const modalExito    = document.getElementById('modalExito');
const exitoMensaje  = document.getElementById('exitoMensaje');
const contadorTiempo = document.getElementById('contadorTiempo');

document.getElementById('btnCerrarExito').addEventListener('click', () => {
  modalExito.classList.add('oculto');
  clearInterval(intervaloContador);
});

function mostrarExito(datos) {
  exitoMensaje.textContent = `Reservaste ${datos.cantidad} unidad(es) de ${productoSeleccionado.nombre}.`;
  modalExito.classList.remove('oculto');

  const expira = new Date(datos.expira_en);
  actualizarContador(expira);
  intervaloContador = setInterval(() => actualizarContador(expira), 1000);
}

function actualizarContador(expira) {
  const ahora     = new Date();
  const diferencia = Math.max(0, Math.floor((expira - ahora) / 1000));
  const minutos   = Math.floor(diferencia / 60).toString().padStart(2, '0');
  const segundos  = (diferencia % 60).toString().padStart(2, '0');
  contadorTiempo.textContent = `${minutos}:${segundos}`;

  if (diferencia === 0) {
    clearInterval(intervaloContador);
    contadorTiempo.textContent = 'Reserva expirada';
  }
}