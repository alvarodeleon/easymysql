'''
Copyright (C) 2020 Alvaro de Leon <info@alvarodeleon.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''

from abc import ABC, abstractmethod
from ._types import ConditionInput, Params, Row
from typing import Iterable, Union, Dict, Any


class connector(ABC):
	"""
	Interfaz abstracta para conectores de base de datos.
	Define los métodos que debe implementar cualquier conector.
	"""
	
	@abstractmethod
	def __init__(self, hostname: str, username: str, password: str, database: str, **kwargs):
		"""
		Inicializa la conexión a la base de datos.
		
		Args:
			hostname (str): Nombre del host
			username (str): Nombre de usuario
			password (str): Contraseña
			database (str): Nombre de la base de datos
		"""
		pass
	
	@abstractmethod
	def version(self) -> str:
		"""
		Retorna la versión del conector.
		
		Returns:
			str: Versión del conector
		"""
		pass
	
	@abstractmethod
	def ping(self) -> bool:
		"""
		Verifica si la conexión está activa.
		
		Returns:
			bool: True si la conexión está activa, False en caso contrario
		"""
		pass
	
	@abstractmethod
	def connect(self):
		"""
		Establece la conexión a la base de datos.
		"""
		pass
	
	@abstractmethod
	def reconnect(self):
		"""
		Reconecta a la base de datos.
		"""
		pass
	
	@abstractmethod
	def execute(self, query: str, params: Params = None):
		"""
		Ejecuta una consulta SQL.
		
		Args:
			query (str): Consulta SQL a ejecutar
		"""
		pass
	
	@abstractmethod
	def executemany(self, query: str, params: list):
		"""
		Ejecuta la misma consulta múltiples veces con diferentes parámetros.
		
		Args:
			query (str): Consulta SQL con placeholders
			params (list): Lista de tuplas con los parámetros
		"""
		pass
	
	@abstractmethod
	def execute_multiple(self, queries: list):
		"""
		Ejecuta múltiples consultas SQL de forma secuencial.
		
		Args:
			queries (list): Lista de consultas SQL a ejecutar
		"""
		pass
	
	@abstractmethod
	def query(self, query: str, params: Params = None) -> list[Row]:
		"""
		Ejecuta una consulta SQL y retorna los resultados.
		
		Args:
			query (str): Consulta SQL a ejecutar
			
		Returns:
			list: Lista de diccionarios con los resultados
		"""
		pass
	
	@abstractmethod
	def count(self) -> int:
		"""
		Retorna el número de filas afectadas por la última consulta.
		
		Returns:
			int: Número de filas afectadas
		"""
		pass
	
	@abstractmethod
	def getLastId(self) -> Any:
		"""
		Retorna el ID de la última fila insertada.
		
		Returns:
			Union[int, None]: ID de la última fila insertada o None
		"""
		pass
	
	@abstractmethod
	def select(self, table: str, condition: ConditionInput = "", fields: str = "*", order: str = "", *, order_by=None, limit=None, offset=None,
	           group_by=None, having=None, for_update: bool=False) -> list[Row]:
		"""
		Ejecuta una consulta SELECT.
		
		Args:
			table (str): Nombre de la tabla
			condition (ConditionInput): Condición WHERE
			fields (str): Campos a seleccionar
			order (str): Cláusula ORDER BY
			
		Returns:
			list: Lista de diccionarios con los resultados
		"""
		pass
	
	@abstractmethod
	def insert(self, table: str, data: dict) -> Any:
		"""
		Inserta un nuevo registro en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a insertar
			
		Returns:
			Union[int, None]: ID del registro insertado o None
		"""
		pass
	
	@abstractmethod
	def update(self, table: str, data: dict, condition: ConditionInput):
		"""
		Actualiza registros en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a actualizar
			condition (ConditionInput): Condición WHERE
		"""
		pass
	
	@abstractmethod
	def delete(self, table: str, condition: ConditionInput):
		"""
		Elimina registros de la tabla.
		
		Args:
			table (str): Nombre de la tabla
			condition (ConditionInput): Condición WHERE
		"""
		pass
	
	@abstractmethod
	def close(self):
		"""
		Cierra la conexión a la base de datos.
		"""
		pass
	
	@abstractmethod
	def resetSession(self):
		"""
		Devuelve la sesión al estado que tenía recién conectada.

		No puede llamarse con una transacción abierta: las implementaciones
		lanzan `RuntimeError` en ese caso.
		"""
		pass
	
	@abstractmethod
	def truncate(self, table: str):
		"""
		Trunca una tabla.
		
		Args:
			table (str): Nombre de la tabla a truncar
		"""
		pass
	
	@abstractmethod
	def commit(self):
		"""
		Confirma la transacción actual.
		"""
		pass
	
	@abstractmethod
	def begin(self) -> bool:
		"""
		Inicia una nueva transacción.
		
		Returns:
			bool: True si la transacción se inició correctamente
		"""
		pass
	
	@abstractmethod
	def rollback(self) -> bool:
		"""
		Revierte la transacción actual.
		
		Returns:
			bool: True si el rollback se ejecutó correctamente
		"""
		pass
	
	@abstractmethod
	def is_in_transaction(self) -> bool:
		"""
		Retorna True si hay una transacción de la biblioteca activa.
		
		Returns:
			bool: True si hay una transacción activa
		"""
		pass
	
	@abstractmethod
	def transaction(self):
		"""
		Retorna un contexto de transacción.
		
		Returns:
			TransactionContext: Contexto de transacción
		"""
		pass