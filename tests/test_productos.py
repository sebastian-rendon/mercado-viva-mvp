import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from unittest.mock import patch, MagicMock
from app import app

@pytest.fixture
def cliente():
    app.config['TESTING'] = True
    with app.test_client() as cliente:
        yield cliente

def test_productos_con_stock(cliente):
    mock_filas = [
        (1, 'Arroz 500g', 'SKU001', 'Granos', 5, 20, 2, 'Sucursal Centro'),
        (2, 'Aceite 1L',  'SKU002', 'Aceites', 3, 0,  0, 'Sucursal Centro'),
    ]

    with patch('app.obtener_conexion') as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_filas
        mock_conn.return_value.cursor.return_value = mock_cursor

        respuesta = cliente.get('/productos?tienda_id=1')
        datos     = respuesta.get_json()

        assert respuesta.status_code == 200
        assert len(datos) == 2

        arroz = datos[0]
        assert arroz['nombre'] == 'Arroz 500g'
        assert arroz['stock_disponible'] == 20
        assert arroz['sin_disponibilidad'] == False

        aceite = datos[1]
        assert aceite['nombre'] == 'Aceite 1L'
        assert aceite['stock_disponible'] == 0
        assert aceite['sin_disponibilidad'] == True