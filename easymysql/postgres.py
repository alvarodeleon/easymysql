#!/usr/bin/python
# -*- coding: utf-8 -*-

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

import collections.abc
import logging
import threading
import warnings
from typing import Union, Dict, Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _es_conexion_caida(exc) -> bool:
	"""
	¿La excepción indica que el servidor cerró la conexión?

	psycopg2 levanta OperationalError/InterfaceError cuando el backend murió
	(corte de red, `pg_terminate_backend`, `idle_session_timeout`).
	"""
	return isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))

from .connector import connector
from .pg_query import (
	condition_params, insert_params, update_params, delete_params, select_params,
)
# `_table` y `_process_condition` empiezan con guion bajo: van aparte.
from .pg_query import _process_condition, _table

class postgresql(connector):
	"""
	Implementación de connector para PostgreSQL usando psycopg2.
	"""
	
	def __init__(self, hostname: str, username: str, password: str,
	             database: str, **kwargs):
		"""
		Inicializa la conexión a PostgreSQL.

		Args:
			hostname (str): Nombre del host
			username (str): Nombre de usuario
			password (str): Contraseña
			database (str): Nombre de la base de datos
			**kwargs: se pasan tal cual a `psycopg2.connect()` — `port`,
				`sslmode`, `connect_timeout`, `application_name`… Antes no
				había forma de indicar ninguno.
		"""
		self.__db = None
		self.__cursor = None
		self.__closed = False
		self.__tx_depth = 0
		self.__last_rowcount = 0
		self.__last_insert_id = None
		self._lock = threading.RLock()

		self.__hostname = hostname
		self.__username = username
		self.__password = password
		self.__database = database
		self.__opciones = dict(kwargs)

		self.connect()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()
		return False

	def __comprobar_abierta(self):
		if self.__closed:
			raise RuntimeError("la conexión está cerrada")
	
	def __file__(self):
		return __file__
	
	def version(self) -> str:
		"""
		Retorna la versión del conector PostgreSQL.
		
		Returns:
			str: Versión del conector
		"""
		from . import __version__
		return __version__
	
	def ping(self) -> bool:
		"""
		Verifica si la conexión está activa.
		
		Returns:
			bool: True si la conexión está activa, False en caso contrario
		"""
		# Antes ejecutaba un `SELECT 1` real en cada operación: duplicaba los
		# round-trips a la base y, dentro de una transacción abortada, fallaba
		# y disparaba una reconexión que descartaba la transacción entera.
		if self.__db is None or self.__closed:
			return False
		try:
			return self.__db.closed == 0
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
				database=self.__database,
				**self.__opciones,
			)
			self.__cursor = self.__db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
			self.__closed = False
		except Exception:
			logger.exception("error conectando a PostgreSQL")
			raise
	
	def reconnect(self):
		"""
		Reconecta cerrando primero la conexión anterior.

		Nunca reconecta con una transacción abierta: cerrar la conexión hace
		un ROLLBACK implícito y el trabajo no commiteado se perdería en
		silencio, que era el mecanismo de C-06.
		"""
		with self._lock:
			if self.__tx_depth > 0:
				raise RuntimeError(
					"no se puede reconectar con una transacción abierta: "
					"se perdería el trabajo no commiteado"
				)
			self.__cerrar_recursos()
			self.connect()

	def __cerrar_recursos(self):
		for recurso in (self.__cursor, self.__db):
			try:
				if recurso is not None:
					recurso.close()
			except Exception:
				logger.debug("error cerrando el recurso", exc_info=True)
		self.__cursor = None
		self.__db = None
	
	def execute(self, query: str, params=None):
		"""
		Ejecuta una consulta SQL.
		
		Args:
			query (str): Consulta SQL a ejecutar

		Raises:
			RuntimeError: si no hay conexión activa.
			psycopg2.Error: cualquier error de la base de datos.
		"""
		with self._lock:
			self.__comprobar_abierta()

			if not self.ping():
				self.reconnect()

			if self.__cursor is None:
				raise RuntimeError("no hay una conexión activa; llamá a connect()")

			# Se invalidan antes de ejecutar: si la sentencia falla, count() y
			# getLastId() no deben devolver los valores de la operación
			# anterior.
			self.__last_rowcount = 0
			self.__last_insert_id = None

			try:
				self.__cursor.execute(query, params)
			except Exception as e:
				# Se reintenta UNA vez y **sólo fuera de transacción**:
				# reconectar dentro de una haría ROLLBACK implícito y
				# perdería el trabajo en silencio (C-06).
				if self.__tx_depth > 0 or not _es_conexion_caida(e):
					raise
				logger.info("conexión caída (%s); reconectando y reintentando", e)
				self.reconnect()
				self.__cursor.execute(query, params)

			self.__last_rowcount = max(0, self.__cursor.rowcount or 0)
	
	def executemany(self, query: str, params: list):
		"""
		Ejecuta la misma consulta múltiples veces con diferentes parámetros.
		
		Args:
			query (str): Consulta SQL con placeholders (%s)
			params (list): Lista de tuplas con los parámetros para cada ejecución

		Raises:
			TypeError: si params no es una secuencia de tuplas/listas.
			psycopg2.Error: cualquier error de la base de datos.
		"""
		if isinstance(params, (str, bytes)) or not isinstance(params, collections.abc.Sequence):
			raise TypeError(
				f"params debe ser una secuencia de tuplas, no {type(params).__name__}"
			)

		with self._lock:
			self.__comprobar_abierta()

			if not self.ping():
				self.reconnect()

			if self.__cursor is None:
				raise RuntimeError("no hay una conexión activa; llamá a connect()")

			self.__last_rowcount = 0
			self.__cursor.executemany(query, params)
			self.__last_rowcount = max(0, self.__cursor.rowcount or 0)

			# El commit solo se alcanza si executemany() no lanzó.
			self.__autocommit()
	
	def execute_multiple(self, queries: list):
		"""
		Ejecuta múltiples consultas SQL de forma secuencial.
		
		El lote se valida entero antes de ejecutar nada.

		Args:
			queries (list): Lista de consultas SQL a ejecutar

		Raises:
			TypeError: si algún elemento de la lista no es un string.
			psycopg2.Error: cualquier error de la base de datos.
		"""
		for i, query in enumerate(queries):
			if not isinstance(query, str):
				raise TypeError(f"queries[{i}] no es un string: {type(query).__name__}")

		pendientes = [q.strip() for q in queries if q.strip()]

		with self._lock:
			self.__comprobar_abierta()

			if not self.ping():
				self.reconnect()

			if self.__cursor is None:
				raise RuntimeError("no hay una conexión activa; llamá a connect()")

			# El lote va en una transacción propia: antes, si fallaba
			# la tercera de cinco, las dos primeras quedaban
			# ejecutadas y sin revertir. Si ya hay una transacción
			# abierta se respeta y el rollback queda a cargo del
			# nivel externo.
			propia = not self.is_in_transaction()
			if propia:
				self.begin()

			try:
				for query in pendientes:
					self.__cursor.execute(query)
			except Exception:
				if propia:
					self.rollback()
				raise

			# El commit solo se alcanza si todas las sentencias pasaron.
			if propia:
				self.commit()
	
	def query(self, query: str, params=None) -> list:
		"""
		Ejecuta una consulta SQL y retorna los resultados.
		
		Args:
			query (str): Consulta SQL a ejecutar
			
		Returns:
			list: Lista de diccionarios con los resultados

		Raises:
			psycopg2.Error: cualquier error de la base de datos. Antes se
			capturaba y se devolvía [], con lo que "cero resultados" y "la
			consulta falló" eran indistinguibles.
		"""
		# El execute y el fetch van bajo el mismo lock: si otro hilo ejecuta
		# entremedio, el cursor compartido devuelve sus filas.
		with self._lock:
			self.execute(query, params)

			# description es None cuando la consulta no devuelve filas
			if self.__cursor.description is None:
				return []

			# psycopg2.extras.RealDictCursor ya retorna diccionarios
			return [dict(row) for row in self.__cursor.fetchall()]
	
	def count(self) -> int:
		"""
		Retorna el número de filas afectadas por la última consulta.
		
		Returns:
			int: Número de filas afectadas
		"""
		return self.__last_rowcount
	
	def getLastId(self) -> Union[int, None]:
		"""
		ID devuelto por el `RETURNING` del último INSERT exitoso, o None.

		Antes ejecutaba `SELECT lastval()` sobre el cursor compartido, lo que
		tenía tres problemas: descartaba el resultset pendiente del cursor,
		`lastval()` es de ámbito de **sesión** y devolvía el valor de otra
		secuencia si un trigger la disparaba, y el `except Exception: pass`
		tapaba cualquier error.

		Ahora se guarda el valor en insert() y este método solo lo lee: mismo
		contrato que el backend MySQL.
		"""
		return self.__last_insert_id
	
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
		sql, params = select_params(table, condition, fields, order)

		return self.query(sql, params)
	
	def insert(self, table: str, data: dict, returning: str = "id") -> Union[int, None]:
		"""
		Inserta un nuevo registro en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a insertar
			
		Returns:
			Union[int, None]: ID del registro insertado, o None si la tabla no
			tiene columna `id`.

		Raises:
			Cualquier error de la base de datos se propaga. Un INSERT fallido
			nunca se reintenta: no es una operación idempotente.
		"""

		sql, params = insert_params(table, data, returning=returning)

		with self._lock:
			self.execute(sql, params)

		# El cursor es RealDictCursor: las filas se indexan por nombre de
		# columna, no por posición. `row[0]` daba KeyError y el except del
		# código anterior reejecutaba el INSERT, duplicando la fila.
			row = None
			if self.__cursor is not None and self.__cursor.description is not None:
				row = self.__cursor.fetchone()

			self.__autocommit()

			if row is None:
				return None

			nuevo = row.get(returning) if hasattr(row, 'get') else row[0]
			self.__last_insert_id = nuevo
			return nuevo
	
	def update(self, table: str, data: dict, condition: Union[str, Dict[str, Any]]):
		"""
		Actualiza registros en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a actualizar
			condition (Union[str, Dict[str, Any]]): Condición WHERE
		"""
		
		sql, params = update_params(table, data, condition)

		with self._lock:
			self.execute(sql, params)
			self.__autocommit()
	
	def delete(self, table: str, condition: Union[str, Dict[str, Any]]):
		"""
		Elimina registros de la tabla.
		
		Args:
			table (str): Nombre de la tabla
			condition (Union[str, Dict[str, Any]]): Condición WHERE
		"""
		sql, params = delete_params(table, condition)

		with self._lock:
			self.execute(sql, params)
			self.__autocommit()
	
	def close(self):
		"""
		Cierra la conexión.

		Si hay una transacción abierta, revierte explícitamente y avisa: antes
		el cierre provocaba un ROLLBACK implícito sin ninguna señal.
		"""
		with self._lock:
			if self.__closed:
				return

			if self.__tx_depth > 0:
				warnings.warn(
					"close() con una transacción abierta: se revierte el "
					"trabajo no commiteado",
					UserWarning,
					stacklevel=2,
				)
				try:
					if self.__db is not None:
						self.__db.rollback()
				except Exception:
					logger.debug("error al revertir en close()", exc_info=True)
				self.__tx_depth = 0

			self.__cerrar_recursos()
			self.__closed = True

	def resetSession(self):
		"""
		Devuelve la sesión al estado que tenía recién conectada: `DISCARD ALL`
		libera planes, sentencias preparadas, tablas temporales y el resto del
		estado de sesión.

		Se llamaba `resetCache()`, pero acá nunca hubo un cache que resetear:
		el nombre describía la sentencia de MySQL, no lo que hace esto.

		No puede correr dentro de una transacción -- PostgreSQL responde
		`DISCARD ALL cannot run inside a transaction block` --, así que la
		guarda avisa antes de que el driver tire un error más oscuro.

		El contador no alcanza para saber si hay una transacción abierta: la
		conexión vive en `autocommit=False` y psycopg2 mete un BEGIN implícito
		antes de la primera sentencia, así que con `__tx_depth == 0` igual se
		está dentro de un bloque -- basta un `select()` previo. Por eso se
		cierra lo pendiente y se ejecuta con autocommit puesto, restaurándolo
		después.
		"""
		with self._lock:
			self.__comprobar_abierta()
			if self.__tx_depth > 0:
				raise RuntimeError(
					"no se puede resetear la sesión con una transacción abierta: "
					"PostgreSQL rechaza DISCARD ALL dentro de un bloque de "
					"transacción"
				)
			if self.__db is None:
				return

			# Cierra el BEGIN implícito. En este punto `__tx_depth` es 0, así
			# que lo único pendiente es el snapshot de lectura: no hay trabajo
			# sin commitear que se pueda perder.
			self.__db.commit()

			previo = getattr(self.__db, "autocommit", False)
			self.__db.autocommit = True
			try:
				self.execute("DISCARD ALL")
			finally:
				self.__db.autocommit = previo

	def truncate(self, table: str):
		"""Trunca una tabla."""
		self.execute(f'TRUNCATE TABLE {_table(table)} RESTART IDENTITY CASCADE')

	# -- transacciones ----------------------------------------------------------
	#
	# La profundidad es un contador, no un booleano: antes, salir de un `with`
	# anidado commiteaba y reactivaba el autocommit dentro de la externa.

	def __autocommit(self):
		"""Commitea solo si no hay ninguna transacción abierta."""
		if self.__tx_depth == 0 and self.__db is not None:
			self.__db.commit()

	def begin(self) -> bool:
		"""
		Abre una transacción, o un SAVEPOINT si ya hay una abierta.

		Antes sólo cambiaba un flag y asumía que psycopg2 abre la transacción
		sola. Es cierto salvo que la conexión esté en autocommit, en cuyo caso
		no había ninguna transacción y el rollback posterior no revertía nada.
		"""
		with self._lock:
			self.__comprobar_abierta()
			if self.__db is None:
				return False

			if self.__tx_depth == 0:
				if getattr(self.__db, "autocommit", False):
					self.__db.autocommit = False
			else:
				self.execute(f"SAVEPOINT easymysql_sp_{self.__tx_depth}")

			self.__tx_depth += 1
			return True

	def commit(self):
		"""
		Cierra el nivel actual. Solo commitea de verdad al salir del más
		externo.
		"""
		with self._lock:
			if self.__db is None:
				return

			if self.__tx_depth <= 1:
				self.__db.commit()
				self.__tx_depth = 0
			else:
				self.__tx_depth -= 1
				self.execute(f"RELEASE SAVEPOINT easymysql_sp_{self.__tx_depth}")

	def rollback(self) -> bool:
		"""
		Revierte el nivel actual: la transacción entera si es el más externo,
		o hasta el SAVEPOINT si es anidado.
		"""
		with self._lock:
			if self.__db is None:
				return False

			if self.__tx_depth <= 1:
				self.__db.rollback()
				self.__tx_depth = 0
			else:
				self.__tx_depth -= 1
				self.execute(f"ROLLBACK TO SAVEPOINT easymysql_sp_{self.__tx_depth}")
			return True

	def is_in_transaction(self) -> bool:
		"""
		¿Hay una transacción **de la librería** abierta?

		Refleja el contador propio, no el estado del driver, y es a propósito.
		`get_transaction_status()` de psycopg2 parece la respuesta correcta
		—vería un `BEGIN` hecho por fuera— pero no sirve: psycopg2 abre una
		transacción implícita antes de la primera sentencia, así que devuelve
		`INTRANS` después de cualquier `select()`, indistinguible de un `BEGIN`
		crudo. Verificado contra PostgreSQL 16.14 el 2026-09-05.

		Usarlo acá rompería `execute_multiple()`, que pregunta esto para decidir
		si abre transacción propia: un lote ejecutado después de cualquier
		consulta previa se quedaría sin `BEGIN` y sin `commit`.

		**Límite conocido:** una transacción abierta por fuera de la librería no
		se detecta. Está documentado en `change.md` §7.
		"""
		return self.__tx_depth > 0

	def transaction(self):
		"""Contexto de transacción para usar con `with`."""
		return TransactionContext(self)

	def _process_condition(self, condition):
		"""
		Heredado: delega en pg_query._process_condition.

		Ya no lo usa ningún método de la clase: insert/update/delete/select
		pasan por los builders parametrizados.
		"""
		return _process_condition(condition)


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
