from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
import os
import uuid
from datetime import datetime, timezone, timedelta

load_dotenv()

app = Flask(__name__)
CORS(app)

def obtener_conexion():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

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


if __name__ == '__main__':
    app.run(debug=True)