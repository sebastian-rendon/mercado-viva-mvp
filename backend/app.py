from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from urllib.parse import urlparse
import psycopg2
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

def obtener_conexion():
    url = urlparse(os.getenv('DATABASE_URL'))
    return psycopg2.connect(
        host=url.hostname,
        port=url.port,
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        sslmode='require'
    )

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

if __name__ == '__main__':
    app.run(debug=True)