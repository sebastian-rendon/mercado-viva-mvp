import sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
import uuid
import jwt
import bcrypt
import os
from datetime import datetime, timezone, timedelta
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app)

def obtener_conexion():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

# ── AUTENTICACIÓN ──────────────────────────────────────
def verificar_token(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')

        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Token requerido'}), 401

        try:
            datos = jwt.decode(
                token,
                os.getenv('JWT_SECRET'),
                algorithms=['HS256']
            )
            request.empleado_id = datos['empleado_id']
            request.empleado_nombre = datos['nombre']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401

        return f(*args, **kwargs)
    return decorador

# ── PING ──────────────────────────────────────────────
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'mensaje': 'Backend funcionando correctamente'})

@app.route('/db-ping', methods=['GET'])
def db_ping():
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM productos')
        total = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            'mensaje': 'Conexión a Supabase exitosa',
            'total_productos': total
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── PRODUCTOS ──────────────────────────────────────────
@app.route('/productos', methods=['GET'])
def obtener_productos():
    try:
        tienda_id = request.args.get('tienda_id')
        conn = obtener_conexion()
        cursor = conn.cursor()

        if tienda_id:
            cursor.execute('''
                SELECT p.id, p.nombre, p.sku, p.categoria, p.umbral_minimo,
                       i.stock_disponible, i.stock_reservado, t.nombre AS tienda
                FROM productos p
                JOIN inventario i ON i.producto_id = p.id
                JOIN tiendas t ON t.id = i.tienda_id
                WHERE i.tienda_id = %s
                ORDER BY p.nombre
            ''', (tienda_id,))
        else:
            cursor.execute('''
                SELECT p.id, p.nombre, p.sku, p.categoria, p.umbral_minimo,
                       i.stock_disponible, i.stock_reservado, t.nombre AS tienda
                FROM productos p
                JOIN inventario i ON i.producto_id = p.id
                JOIN tiendas t ON t.id = i.tienda_id
                ORDER BY p.nombre
            ''')

        filas = cursor.fetchall()
        cursor.close()
        conn.close()

        productos = []
        for fila in filas:
            stock_disponible = fila[5]
            umbral_minimo = fila[4]
            productos.append({
                'id': fila[0],
                'nombre': fila[1],
                'sku': fila[2],
                'categoria': fila[3],
                'umbral_minimo': umbral_minimo,
                'stock_disponible': stock_disponible,
                'stock_reservado': fila[6],
                'tienda': fila[7],
                'sin_disponibilidad': stock_disponible == 0,
                'stock_bajo': stock_disponible <= umbral_minimo and stock_disponible > 0
            })

        return jsonify(productos)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/productos/<int:producto_id>/stock', methods=['GET'])
def obtener_stock_producto(producto_id):
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT t.id, t.nombre, i.stock_disponible, i.stock_reservado
            FROM inventario i
            JOIN tiendas t ON t.id = i.tienda_id
            WHERE i.producto_id = %s
        ''', (producto_id,))

        filas = cursor.fetchall()
        cursor.close()
        conn.close()

        if not filas:
            return jsonify({'error': 'Producto no encontrado'}), 404

        stock_por_tienda = []
        for fila in filas:
            stock_por_tienda.append({
                'tienda_id': fila[0],
                'tienda': fila[1],
                'stock_disponible': fila[2],
                'stock_reservado': fila[3]
            })

        return jsonify(stock_por_tienda)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── RESERVAS ───────────────────────────────────────────
@app.route('/reservas', methods=['POST'])
def crear_reserva():
    try:
        datos = request.get_json()
        producto_id = datos.get('producto_id')
        tienda_id   = datos.get('tienda_id')
        cantidad    = datos.get('cantidad')

        # Validar campos obligatorios
        if not all([producto_id, tienda_id, cantidad]):
            return jsonify({'error': 'producto_id, tienda_id y cantidad son obligatorios'}), 400

        if cantidad <= 0:
            return jsonify({'error': 'La cantidad debe ser mayor a cero'}), 400

        conn   = obtener_conexion()
        cursor = conn.cursor()

        # Liberar reservas expiradas antes de validar stock
        ahora = datetime.now(timezone.utc)
        cursor.execute('''
            UPDATE inventario i
            SET stock_disponible = stock_disponible + r.cantidad,
                stock_reservado  = stock_reservado  - r.cantidad
            FROM reservas r
            WHERE r.producto_id = i.producto_id
              AND r.tienda_id   = i.tienda_id
              AND r.estado      = 'activa'
              AND r.expira_en   < %s
        ''', (ahora,))

        cursor.execute('''
            UPDATE reservas
            SET estado = 'expirada'
            WHERE estado = 'activa' AND expira_en < %s
        ''', (ahora,))

        # Verificar stock disponible
        cursor.execute('''
            SELECT stock_disponible FROM inventario
            WHERE producto_id = %s AND tienda_id = %s
        ''', (producto_id, tienda_id))

        fila = cursor.fetchone()
        if not fila:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Producto o tienda no encontrados'}), 404

        stock_disponible = fila[0]

        if stock_disponible < cantidad:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Stock insuficiente',
                'stock_disponible': stock_disponible
            }), 409

        # Descontar stock y crear reserva
        cursor.execute('''
            UPDATE inventario
            SET stock_disponible = stock_disponible - %s,
                stock_reservado  = stock_reservado  + %s
            WHERE producto_id = %s AND tienda_id = %s
        ''', (cantidad, cantidad, producto_id, tienda_id))

        sesion_cliente = str(uuid.uuid4())
        expira_en      = ahora + timedelta(minutes=15)

        cursor.execute('''
            INSERT INTO reservas (producto_id, tienda_id, cantidad, estado, sesion_cliente, creada_en, expira_en)
            VALUES (%s, %s, %s, 'activa', %s, %s, %s)
            RETURNING id
        ''', (producto_id, tienda_id, cantidad, sesion_cliente, ahora, expira_en))

        reserva_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'mensaje': 'Reserva creada exitosamente',
            'reserva_id': reserva_id,
            'sesion_cliente': sesion_cliente,
            'expira_en': expira_en.isoformat(),
            'cantidad': cantidad
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reservas/<int:reserva_id>', methods=['DELETE'])
def cancelar_reserva(reserva_id):
    try:
        conn   = obtener_conexion()
        cursor = conn.cursor()

        # Buscar la reserva activa
        cursor.execute('''
            SELECT producto_id, tienda_id, cantidad
            FROM reservas
            WHERE id = %s AND estado = 'activa'
        ''', (reserva_id,))

        fila = cursor.fetchone()
        if not fila:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Reserva no encontrada o ya no está activa'}), 404

        producto_id, tienda_id, cantidad = fila

        # Devolver unidades al stock
        cursor.execute('''
            UPDATE inventario
            SET stock_disponible = stock_disponible + %s,
                stock_reservado  = stock_reservado  - %s
            WHERE producto_id = %s AND tienda_id = %s
        ''', (cantidad, cantidad, producto_id, tienda_id))

        # Marcar reserva como expirada
        cursor.execute('''
            UPDATE reservas SET estado = 'expirada'
            WHERE id = %s
        ''', (reserva_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'mensaje': 'Reserva cancelada y unidades devueltas al stock'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reservas/liberar-expiradas', methods=['POST'])
def liberar_expiradas():
    try:
        ahora  = datetime.now(timezone.utc)
        conn   = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE inventario i
            SET stock_disponible = stock_disponible + r.cantidad,
                stock_reservado  = stock_reservado  - r.cantidad
            FROM reservas r
            WHERE r.producto_id = i.producto_id
              AND r.tienda_id   = i.tienda_id
              AND r.estado      = 'activa'
              AND r.expira_en   < %s
        ''', (ahora,))

        cursor.execute('''
            UPDATE reservas
            SET estado = 'expirada'
            WHERE estado = 'activa' AND expira_en < %s
            RETURNING id
        ''', (ahora,))

        liberadas = cursor.fetchall()
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'mensaje': f'{len(liberadas)} reserva(s) liberada(s)',
            'ids_liberadas': [r[0] for r in liberadas]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── AUTH ───────────────────────────────────────────────
@app.route('/auth/login', methods=['POST'])
def login():
    try:
        datos    = request.get_json()
        email    = datos.get('email')
        password = datos.get('password')

        if not email or not password:
            return jsonify({'error': 'Email y contraseña son obligatorios'}), 400

        conn   = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, nombre, email, password_hash
            FROM empleados
            WHERE email = %s
        ''', (email,))

        empleado = cursor.fetchone()
        cursor.close()
        conn.close()

        if not empleado:
            return jsonify({'error': 'Credenciales inválidas'}), 401

        password_valido = bcrypt.checkpw(
            password.encode('utf-8'),
            empleado[3].encode('utf-8')
        )

        if not password_valido:
            return jsonify({'error': 'Credenciales inválidas'}), 401

        token = jwt.encode({
            'empleado_id': empleado[0],
            'nombre': empleado[1],
            'exp': datetime.now(timezone.utc) + timedelta(hours=8)
        }, os.getenv('JWT_SECRET'), algorithm='HS256')

        return jsonify({
            'mensaje': 'Login exitoso',
            'token': token,
            'nombre': empleado[1]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/auth/verificar', methods=['GET'])
@verificar_token
def verificar():
    return jsonify({
        'mensaje': 'Token válido',
        'empleado_id': request.empleado_id,
        'nombre': request.empleado_nombre
    })


# ── INVENTARIO ─────────────────────────────────────────
@app.route('/inventario/movimiento', methods=['POST'])
@verificar_token
def registrar_movimiento():
    try:
        datos       = request.get_json()
        producto_id = datos.get('producto_id')
        tienda_id   = datos.get('tienda_id')
        tipo        = datos.get('tipo')
        cantidad    = datos.get('cantidad')

        if not all([producto_id, tienda_id, tipo, cantidad]):
            return jsonify({'error': 'producto_id, tienda_id, tipo y cantidad son obligatorios'}), 400

        if tipo not in ('entrada', 'salida'):
            return jsonify({'error': 'tipo debe ser entrada o salida'}), 400

        if cantidad <= 0:
            return jsonify({'error': 'La cantidad debe ser mayor a cero'}), 400

        conn   = obtener_conexion()
        cursor = conn.cursor()

        # Verificar que exista el inventario
        cursor.execute('''
            SELECT stock_disponible FROM inventario
            WHERE producto_id = %s AND tienda_id = %s
        ''', (producto_id, tienda_id))

        fila = cursor.fetchone()
        if not fila:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Producto o tienda no encontrados'}), 404

        stock_actual = fila[0]

        # Validar que no quede stock negativo en salida
        if tipo == 'salida' and stock_actual < cantidad:
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Stock insuficiente para registrar salida',
                'stock_actual': stock_actual
            }), 409

        # Actualizar stock
        if tipo == 'entrada':
            cursor.execute('''
                UPDATE inventario
                SET stock_disponible = stock_disponible + %s
                WHERE producto_id = %s AND tienda_id = %s
            ''', (cantidad, producto_id, tienda_id))
        else:
            cursor.execute('''
                UPDATE inventario
                SET stock_disponible = stock_disponible - %s
                WHERE producto_id = %s AND tienda_id = %s
            ''', (cantidad, producto_id, tienda_id))

        # Registrar movimiento
        cursor.execute('''
            INSERT INTO movimientos (producto_id, tienda_id, tipo, cantidad, empleado_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (producto_id, tienda_id, tipo, cantidad, request.empleado_id))

        movimiento_id = cursor.fetchone()[0]

        # Verificar stock resultante
        cursor.execute('''
            SELECT stock_disponible, umbral_minimo, p.nombre
            FROM inventario i
            JOIN productos p ON p.id = i.producto_id
            WHERE i.producto_id = %s AND i.tienda_id = %s
        ''', (producto_id, tienda_id))

        fila          = cursor.fetchone()
        stock_nuevo   = fila[0]
        umbral_minimo = fila[1]
        nombre        = fila[2]

        conn.commit()
        cursor.close()
        conn.close()

        respuesta = {
            'mensaje': f'Movimiento de {tipo} registrado exitosamente',
            'movimiento_id': movimiento_id,
            'producto': nombre,
            'stock_anterior': stock_actual,
            'stock_nuevo': stock_nuevo
        }

        if stock_nuevo <= umbral_minimo and stock_nuevo > 0:
            respuesta['alerta'] = f'⚠️ Stock bajo: quedan {stock_nuevo} unidades (umbral: {umbral_minimo})'
        elif stock_nuevo == 0:
            respuesta['alerta'] = '🚫 Producto sin disponibilidad'

        return jsonify(respuesta), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/inventario/alertas', methods=['GET'])
@verificar_token
def obtener_alertas():
    try:
        conn   = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT p.id, p.nombre, p.sku, p.umbral_minimo,
                   i.stock_disponible, t.nombre AS tienda, t.id AS tienda_id
            FROM inventario i
            JOIN productos p ON p.id = i.producto_id
            JOIN tiendas t   ON t.id = i.tienda_id
            WHERE i.stock_disponible <= p.umbral_minimo
            ORDER BY i.stock_disponible ASC
        ''', )

        filas = cursor.fetchall()
        cursor.close()
        conn.close()

        alertas = []
        for fila in filas:
            alertas.append({
                'producto_id':      fila[0],
                'producto':         fila[1],
                'sku':              fila[2],
                'umbral_minimo':    fila[3],
                'stock_disponible': fila[4],
                'tienda':           fila[5],
                'tienda_id':        fila[6],
                'sin_stock':        fila[4] == 0
            })

        return jsonify({
            'total_alertas': len(alertas),
            'alertas': alertas
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/inventario/movimientos', methods=['GET'])
@verificar_token
def obtener_movimientos():
    try:
        conn   = obtener_conexion()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT m.id, p.nombre, t.nombre, m.tipo, m.cantidad,
                   e.nombre, m.fecha
            FROM movimientos m
            JOIN productos p  ON p.id = m.producto_id
            JOIN tiendas t    ON t.id = m.tienda_id
            JOIN empleados e  ON e.id = m.empleado_id
            ORDER BY m.fecha DESC
            LIMIT 20
        ''')

        filas = cursor.fetchall()
        cursor.close()
        conn.close()

        movimientos = []
        for fila in filas:
            movimientos.append({
                'id':        fila[0],
                'producto':  fila[1],
                'tienda':    fila[2],
                'tipo':      fila[3],
                'cantidad':  fila[4],
                'empleado':  fila[5],
                'fecha':     fila[6].strftime('%d/%m/%Y %H:%M')
            })

        return jsonify(movimientos)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)