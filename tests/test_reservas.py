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

def test_reserva_exitosa(cliente):
    with patch('app.obtener_conexion') as mock_conn:
        mock_cursor = MagicMock()

        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.side_effect = [
            (20,),
            (42,)
        ]

        mock_conn.return_value.cursor.return_value = mock_cursor

        respuesta = cliente.post('/reservas',
            json={
                'producto_id': 1,
                'tienda_id':   1,
                'cantidad':    3
            }
        )
        datos = respuesta.get_json()

        assert respuesta.status_code == 201
        assert datos['cantidad'] == 3
        assert 'reserva_id' in datos
        assert 'expira_en' in datos
        assert 'sesion_cliente' in datos

        calls = mock_cursor.execute.call_args_list
        update_inventario = any(
            'stock_disponible = stock_disponible - %s' in str(c)
            for c in calls
        )
        assert update_inventario, 'El stock no fue descontado'

def test_reserva_stock_insuficiente(cliente):
    with patch('app.obtener_conexion') as mock_conn:
        mock_cursor = MagicMock()

        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.side_effect = [
            (2,)
        ]

        mock_conn.return_value.cursor.return_value = mock_cursor

        respuesta = cliente.post('/reservas',
            json={
                'producto_id': 1,
                'tienda_id':   1,
                'cantidad':    10
            }
        )
        datos = respuesta.get_json()

        assert respuesta.status_code == 409
        assert 'Stock insuficiente' in datos['error']
        assert datos['stock_disponible'] == 2

        calls = mock_cursor.execute.call_args_list
        update_stock = any(
            'stock_disponible = stock_disponible - %s' in str(c)
            for c in calls
        )
        assert not update_stock, 'El stock fue modificado cuando no debía'