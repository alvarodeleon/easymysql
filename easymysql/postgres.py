#!/usr/bin/python
# -*- coding: utf-8 -*-

import psycopg2
import psycopg2.extras
from typing import Union, Dict, Any
from connector import connector

from query import *

class postgresql(connector):
	"""
	Implementación de connector para PostgreSQL usando psycopg2.
	"""
	
	def __init__(self, hostname: str, username: str, password: str, database: str):
		"""
		Inicializa la conexión a PostgreSQL.
		
		Args:
			hostname (str): Nombre del host
			username (str): Nombre de usuario
			password (str): Contraseña
			database (str): Nombre de la base de datos
		"""
		self.__hostname = hostname
		self.__username = username
		self.__password = password
		self.__database = database
		self.__in_transaction = False
		self.__cursor = None
		self.__db = None
		
		self.connect()
	
	def __file__(self):
		return __file__
	
	def version(self) -> str:
		"""
		Retorna la versión del conector PostgreSQL.
		
		Returns:
			str: Versión del conector
		"""
		return "0.1.0"
	
	def ping(self) -> bool:
		"""
		Verifica si la conexión está activa.
		
		Returns:
			bool: True si la conexión está activa, False en caso contrario
		"""
		try:
			if self.__db is not None and not self.__db.closed:
				# Ejecutar una consulta simple para verificar la conexión
				with self.__db.cursor() as cursor:
					cursor.execute("SELECT 1")
				return True
			else:
				return False
		except Exception:
			return False
	
	def connect(self):
		"""
		Establece la conexión a PostgreSQL.
		"""
		try:
			self.__db = psycopg2.connect(
				host=self.__hostname,
				user=self.__username,
				password=self.__password,
				database=self.__database
			)
			self.__cursor = self.__db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
		except Exception as e:
			print(f"Error connecting to PostgreSQL: {e}")
			raise
	
	def reconnect(self):
		"""
		Reconecta a PostgreSQL.
		"""
		self.close()
		self.connect()
	
	def execute(self, query: str):
		"""
		Ejecuta una consulta SQL.
		
		Args:
			query (str): Consulta SQL a ejecutar
		"""
		if not self.ping():
			self.reconnect()
		
		try:
			if self.__cursor is not None:
				self.__cursor.execute(query)
		except Exception as e:
			print(f"Exception occurred: {e}")
			raise
	
	def executemany(self, query: str, params: list):
		"""
		Ejecuta la misma consulta múltiples veces con diferentes parámetros.
		
		Args:
			query (str): Consulta SQL con placeholders (%s)
			params (list): Lista de tuplas con los parámetros para cada ejecución
		"""
		if not self.ping():
			self.reconnect()
		
		try:
			if self.__cursor is not None:
				self.__cursor.executemany(query, params)
				
				# Solo hacer commit automático si no estamos en una transacción
				if not self.__in_transaction and self.__db is not None:
					self.__db.commit()
		except Exception as e:
			print(f"Exception occurred: {e}")
			raise
	
	def execute_multiple(self, queries: list):
		"""
		Ejecuta múltiples consultas SQL de forma secuencial.
		
		Args:
			queries (list): Lista de consultas SQL a ejecutar
		"""
		if not self.ping():
			self.reconnect()
		
		try:
			if self.__cursor is not None:
				for query in queries:
					if query.strip():  # Verificar que no esté vacío
						self.__cursor.execute(query.strip())
				
				# Solo hacer commit automático si no estamos en una transacción
				if not self.__in_transaction and self.__db is not None:
					self.__db.commit()
		except Exception as e:
			print(f"Exception occurred: {e}")
			raise
	
	def query(self, query: str) -> list:
		"""
		Ejecuta una consulta SQL y retorna los resultados.
		
		Args:
			query (str): Consulta SQL a ejecutar
			
		Returns:
			list: Lista de diccionarios con los resultados
		"""
		if not self.ping():
			self.reconnect()
		
		try:
			if self.__cursor is not None:
				self.__cursor.execute(query)
				# psycopg2.extras.RealDictCursor ya retorna diccionarios
				return [dict(row) for row in self.__cursor.fetchall()]
			else:
				return []
		except Exception as e:
			print(f"Exception occurred: {e}")
			return []
	
	def count(self) -> int:
		"""
		Retorna el número de filas afectadas por la última consulta.
		
		Returns:
			int: Número de filas afectadas
		"""
		if self.__cursor is not None and self.__cursor.rowcount is not None:
			return self.__cursor.rowcount
		else:
			return 0
	
	def getLastId(self) -> Union[int, None]:
		"""
		Retorna el ID de la última fila insertada.
		En PostgreSQL usamos RETURNING o currval() para obtener el último ID.
		
		Returns:
			Union[int, None]: ID del registro insertado o None
		"""
		try:
			if self.__cursor is not None:
				# En PostgreSQL, necesitamos usar RETURNING en la consulta INSERT
				# o consultar la secuencia directamente
				self.__cursor.execute("SELECT lastval()")
				result = self.__cursor.fetchone()
				if result:
					return result[0]
		except Exception:
			pass
		return None
	
	def select(self, table: str, condition: Union[str, Dict[str, Any]] = "", fields: str = "*", order: str = "") -> list:
		"""
		Ejecuta una consulta SELECT.
		
		Args:
			table (str): Nombre de la tabla
			condition (Union[str, Dict[str, Any]]): Condición WHERE
			fields (str): Campos a seleccionar
			order (str): Cláusula ORDER BY
			
		Returns:
			list: Lista de diccionarios con los resultados
		"""
		query = select(table,condition,fields,order)
				
		return self.query(query)
	
	def insert(self, table: str, data: dict) -> Union[int, None]:
		"""
		Inserta un nuevo registro en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a insertar
			
		Returns:
			Union[int, None]: ID del registro insertado o None
		"""

		query = insert(table,data)

		
		try:
			self.execute(query)
			
			# Solo hacer commit automático si no estamos en una transacción
			if not self.__in_transaction and self.__db is not None:
				self.__db.commit()
			
			# Intentar obtener el ID retornado
			if self.__cursor is not None:
				result = self.__cursor.fetchone()
				if result:
					return result[0]
		except Exception as e:
			
			query_without_returning = query.replace("RETURNING id","")
			self.execute(query_without_returning)
			
			if not self.__in_transaction and self.__db is not None:
				self.__db.commit()			
				
			return self.getLastId()
		
		return None
	
	def update(self, table: str, data: dict, condition: Union[str, Dict[str, Any]]):
		"""
		Actualiza registros en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a actualizar
			condition (Union[str, Dict[str, Any]]): Condición WHERE
		"""
		
		query = update(table,data,condition)
		
		self.execute(query)
		
		# Solo hacer commit automático si no estamos en una transacción
		if not self.__in_transaction and self.__db is not None:
			self.__db.commit()
	
	def delete(self, table: str, condition: Union[str, Dict[str, Any]]):
		"""
		Elimina registros de la tabla.
		
		Args:
			table (str): Nombre de la tabla
			condition (Union[str, Dict[str, Any]]): Condición WHERE
		"""
		# Procesar condición
		processed_condition = self._process_condition(condition)
		
		query = f'DELETE FROM "{table}" WHERE {processed_condition}'
		
		self.execute(query)
		
		# Solo hacer commit automático si no estamos en una transacción
		if not self.__in_transaction and self.__db is not None:
			self.__db.commit()
	
	def close(self):
		"""
		Cierra la conexión a PostgreSQL.
		"""
		if self.__cursor is not None:
			self.__cursor.close()
		if self.__db is not None:
			self.__db.close()
	
	def resetCache(self):
		"""
		Resetea la caché de consultas en PostgreSQL.
		"""
		if self.__cursor is not None:
			# En PostgreSQL no hay RESET QUERY CACHE como en MySQL
			# Pero podemos usar DISCARD ALL para limpiar el estado de la sesión
			self.__cursor.execute("DISCARD ALL")
	
	def truncate(self, table: str):
		"""
		Trunca una tabla.
		
		Args:
			table (str): Nombre de la tabla a truncar
		"""
		if len(table) > 0 and self.__cursor is not None:
			# En PostgreSQL, TRUNCATE requiere especificar CASCADE/RESTRICT
			self.__cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
	
	def commit(self):
		"""
		Confirma la transacción actual.
		"""
		if self.__db is not None:
			self.__db.commit()
			self.__in_transaction = False
	
	def begin(self) -> bool:
		"""
		Inicia una nueva transacción.
		
		Returns:
			bool: True si la transacción se inició correctamente
		"""
		try:
			if self.__db is not None:
				# PostgreSQL inicia transacciones automáticamente
				# Solo marcamos que estamos en transacción
				self.__in_transaction = True
				return True
		except Exception:
			pass
		return False
	
	def rollback(self) -> bool:
		"""
		Revierte la transacción actual.
		
		Returns:
			bool: True si el rollback se ejecutó correctamente
		"""
		try:
			if self.__db is not None:
				self.__db.rollback()
				self.__in_transaction = False
				return True
		except Exception:
			pass
		return False
	
	def is_in_transaction(self) -> bool:
		"""
		Retorna True si hay una transacción activa.
		
		Returns:
			bool: True si hay una transacción activa
		"""
		return self.__in_transaction
	
	def transaction(self):
		"""
		Retorna un contexto de transacción.
		
		Returns:
			TransactionContext: Contexto de transacción
		"""
		return TransactionContext(self)
	
	def _process_condition(self, condition):
		"""
		Procesa la condición convirtiendo diccionarios a string SQL WHERE.
		Adaptado para PostgreSQL (usa comillas dobles para nombres de columnas).
		
		Args:
			condition: Puede ser string, diccionario, None o cualquier otro tipo
		
		Returns:
			str: Condición SQL formateada
		"""
		# Si es None o string vacío, retornar string vacío
		if condition is None or condition == "":
			return ""
		
		# Si es string, retornarlo directamente
		if isinstance(condition, str):
			return condition
		
		# Si es diccionario, procesarlo
		if isinstance(condition, dict):
			if not condition:  # Diccionario vacío
				return ""
			
			conditions = []
			for key, value in condition.items():
				if value is None:
					conditions.append(f'"{key}" IS NULL')
				else:
					# Escapar comillas simples para prevenir SQL injection
					escaped_value = str(value).replace("'", "''")
					conditions.append(f'"{key}" = \'{escaped_value}\'')
			return " AND ".join(conditions)
		
		# Si es otro tipo iterable (como OrderedDict, etc.)
		if hasattr(condition, 'items'):
			conditions = []
			for key, value in condition.items():
				if value is None:
					conditions.append(f'"{key}" IS NULL')
				else:
					escaped_value = str(value).replace("'", "''")
					conditions.append(f'"{key}" = \'{escaped_value}\'')
			return " AND ".join(conditions)
		
		# Para cualquier otro tipo, convertirlo a string
		return str(condition)


class TransactionContext:
	"""
	Contexto de transacción para usar con la declaración 'with'.
	"""
	def __init__(self, db_connection):
		self.db = db_connection
		self.committed = False
	
	def __enter__(self):
		"""
		Inicia la transacción al entrar al contexto.
		"""
		self.db.begin()
		return self.db
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		"""
		Maneja la salida del contexto de transacción.
		Si hay una excepción, hace rollback. Si no, hace commit.
		"""
		if exc_type is not None:
			# Hubo una excepción, hacer rollback
			self.db.rollback()
		else:
			# No hubo excepción, hacer commit
			self.db.commit()
