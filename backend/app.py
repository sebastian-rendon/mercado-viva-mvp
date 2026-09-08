from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import psycopg2
import os

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


if __name__ == '__main__':
    app.run(debug=True)