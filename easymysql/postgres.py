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
from ._types import ConditionInput, Params, Row
from typing import Union, Dict, Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


from .connector import connector
from ._convenience import Convenience
from ._sql import POSTGRES
from ._transaction import TransactionContext, TransactionState, serialized, data_operation
from .pg_query import (
	condition_params, insert_params, update_params, delete_params, select_params,
)
# `_table` y `_process_condition` empiezan con guion bajo: van aparte.
from .pg_query import _process_condition, _table

class postgresql(Convenience, connector):
	"""
	Implementación de connector para PostgreSQL usando psycopg2.
	Las transacciones de la biblioteca pertenecen al hilo que las inició;
	las operaciones de otros hilos se rechazan hasta que terminen.
	"""
	
	_dialect = POSTGRES

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
		self._tx = TransactionState()
		self._pending = False
		self.__previous_autocommit = None
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
		self._tx.check_usable()
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
	
	@serialized
	def connect(self):
		"""Abre la conexión; si ya está sana no reemplaza recursos.

		El reemplazo explícito se hace con reconnect(). No se permite abrir
		otra sesión mientras haya una transacción de la biblioteca pendiente.
		"""
		self.__comprobar_reconexion()
		if self.ping() and self.__cursor is not None:
			return
		self.__cerrar_recursos()
		self.__last_rowcount = 0
		self.__last_insert_id = None
		try:
			self.__abrir_recursos()
		except BaseException:
			logger.exception("error conectando a PostgreSQL")
			raise

	def __abrir_recursos(self):
		# Publicar los recursos solo después de que ambos existan.
		db = psycopg2.connect(
			host=self.__hostname,
			user=self.__username,
			password=self.__password,
			database=self.__database,
			**self.__opciones,
		)
		try:
			cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
		except BaseException:
			try:
				db.close()
			except Exception:
				logger.debug("error cerrando la conexión sin cursor", exc_info=True)
			raise
		self.__db = db
		self.__cursor = cursor
		self.__closed = False
		self._pending = False

	def __comprobar_reconexion(self):
		self._tx.check_usable()
		self._ensure_clean()
		if self._tx.depth > 0:
			raise RuntimeError(
				"no se puede reconectar con una transacción abierta: "
				"se perdería el trabajo no commiteado"
			)
	
	@serialized
	def reconnect(self):
		"""Reemplaza explícitamente la sesión, sin repetir sentencias SQL."""
		self.__comprobar_reconexion()
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
	
	@data_operation
	def execute(self, query: str, params: Params=None):
		"""SQL raw sin commit ni reintento; terminar con commit()/rollback()."""
		self._execute(query, params)
	
	@data_operation
	def executemany(self, query: str, params):
		"""Lote transaccional; savepoint propio dentro de otra transacción."""
		if isinstance(params, (str, bytes)) or not isinstance(params, collections.abc.Sequence):
			raise TypeError("params debe ser una secuencia de tuplas/listas")
		if any(not isinstance(row, (tuple, list)) for row in params):
			raise TypeError("cada elemento de params debe ser una tupla/lista")
		self._ensure_cursor()
		self._ensure_clean()
		if not params:
			return
		with self.transaction():
			self.__cursor.executemany(query, params)
			count = max(0, self.__cursor.rowcount or 0)
		self.__last_rowcount = count
		self.__last_insert_id = None
	
	@data_operation
	def execute_multiple(self, queries):
		"""Lote DML atómico; su fallo revierte solo su savepoint si es anidado."""
		if isinstance(queries, (str, bytes)):
			raise TypeError("queries debe ser un iterable de sentencias, no un string")
		queries = list(queries)
		for i, query in enumerate(queries):
			if not isinstance(query, str):
				raise TypeError(f"queries[{i}] no es un string: {type(query).__name__}")
		pending = [query.strip() for query in queries if query.strip()]
		self._ensure_cursor()
		self._ensure_clean()
		if not pending:
			return
		with self.transaction():
			for sql in pending:
				self.__cursor.execute(sql)
				count = max(0, self.__cursor.rowcount or 0)
		self.__last_rowcount = count
		self.__last_insert_id = None
	
	@data_operation
	def query(self, query: str, params: Params=None) -> list[Row]:
		"""SQL raw con filas materializadas; conserva la transacción pendiente."""
		self._execute(query, params)
		return self._fetch_rows()

	def _fetch_rows(self):
		if self.__cursor.description is None:
			return []
		columns = [column[0] for column in self.__cursor.description]
		return [dict(row) if isinstance(row, collections.abc.Mapping) else dict(zip(columns, row))
		        for row in self.__cursor.fetchall()]
	
	def count(self) -> int:
		"""
		Retorna el número de filas afectadas por la última consulta.
		
		Returns:
			int: Número de filas afectadas
		"""
		return self.__last_rowcount
	
	def getLastId(self) -> Any:
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
	
	@data_operation
	def select(self, table: str, condition: ConditionInput="", fields="*", order: str="", *,
	           order_by=None, limit: Union[int, None]=None, offset: Union[int, None]=None,
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
		clauses = dict(order_by=order_by, limit=limit, offset=offset, group_by=group_by,
		               having=having, for_update=for_update)
		if for_update and not self.is_in_transaction():
			raise RuntimeError("for_update requiere transaction()")
		sql, params = select_params(table, condition, fields, order, **clauses)

		return self.query(sql, params)
	
	@data_operation
	def insert(self, table: str, data: dict, returning: Union[str, None] = "id") -> Any:
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

		self._ensure_clean()
		sql, params = insert_params(table, data, returning=returning)

		self._execute(sql, params)

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
	
	@data_operation
	def update(self, table: str, data: dict, condition: ConditionInput):
		"""
		Actualiza registros en la tabla.
		
		Args:
			table (str): Nombre de la tabla
			data (dict): Datos a actualizar
			condition (ConditionInput): Condición WHERE
		"""
		
		self._ensure_clean()
		sql, params = update_params(table, data, condition)

		self._execute(sql, params)
		self.__autocommit()
	
	@data_operation
	def delete(self, table: str, condition: ConditionInput):
		"""
		Elimina registros de la tabla.
		
		Args:
			table (str): Nombre de la tabla
			condition (ConditionInput): Condición WHERE
		"""
		self._ensure_clean()
		sql, params = delete_params(table, condition)

		self._execute(sql, params)
		self.__autocommit()
	
	@serialized
	def close(self):
		"""Cierra recursos; revierte trabajo pendiente del propietario."""
		if self.__closed:
			return
		if self._tx.depth > 0 or self._tx.failed:
			warnings.warn(
				"close() con una transacción abierta o incierta: se intenta "
				"revertir el trabajo no commiteado",
				UserWarning,
				stacklevel=2,
			)
			try:
				if self.__db is not None:
					self.__db.rollback()
			except Exception:
				logger.debug("error al revertir en close()", exc_info=True)
		self.__cerrar_recursos()
		self._tx.clear()
		self._pending = False
		self.__last_rowcount = 0
		self.__last_insert_id = None
		self.__closed = True
		self.__previous_autocommit = None

	@data_operation
	def resetSession(self):
		"""DISCARD ALL solo con sesión limpia; no confirma trabajo pendiente."""
		self._ensure_cursor()
		self._ensure_clean()
		if self._tx.depth:
			raise RuntimeError("no se puede resetear la sesión con una transacción abierta")
		previous = self.__db.autocommit
		try:
			self.__db.autocommit = True
			self.__cursor.execute("DISCARD ALL")
		except BaseException as original:
			try:
				self.__db.autocommit = previous
			except BaseException as cleanup:
				self.__fallo_transaccional()
				raise original from cleanup
			raise
		else:
			try:
				self.__db.autocommit = previous
			except BaseException:
				self.__fallo_transaccional()
				raise
		self._clear_metadata()

	@data_operation
	def truncate(self, table):
		"""TRUNCATE explícito; su atomicidad depende del motor."""
		self._ensure_clean()
		self._execute(f"TRUNCATE TABLE {_table(table)} RESTART IDENTITY CASCADE")
		self.__autocommit()

	# -- transacciones ----------------------------------------------------------
	#
	# La profundidad es un contador, no un booleano: antes, salir de un `with`
	# anidado commiteaba y reactivaba el autocommit dentro de la externa.

	def __autocommit(self):
		"""Commitea solo si no hay ninguna transacción abierta."""
		if self._tx.depth == 0 and self.__db is not None:
			self.commit()

	def _native_pending(self):
		if self.__db is None or not self.ping():
			return None
		get_status = getattr(self.__db, "get_transaction_status", None)
		if get_status is None:
			return None
		status = get_status()
		return status != 0 if isinstance(status, int) else None

	def _driver_autocommit(self):
		return getattr(self.__db, "autocommit", False) is True

	def _ensure_clean(self):
		"""Profundidad cero no implica una sesión sin trabajo pendiente."""
		if self._tx.depth == 0 and (self._pending or self._native_pending() is True):
			raise RuntimeError(
				"hay trabajo pendiente fuera de transaction(): llamá a commit() "
				"o rollback() antes de continuar"
			)

	def _ensure_cursor(self):
		self.__comprobar_abierta()
		if not self.ping():
			raise RuntimeError("no hay una conexión activa; llamá a reconnect()")
		if self.__cursor is None:
			raise RuntimeError("no hay una conexión activa; llamá a connect()")

	def _execute(self, sql, params: Params=None):
		self._ensure_cursor()
		# Marcar antes del envío: un error no demuestra que no haya trabajo.
		if self._tx.depth == 0:
			self._pending = True
		self.__cursor.execute(sql, params)
		if self._tx.depth == 0:
			pending = self._native_pending()
			self._pending = (not self._driver_autocommit()) if pending is None else pending
		self.__last_rowcount = max(0, self.__cursor.rowcount or 0)

	def _set_metadata(self, count, last_id):
		self.__last_rowcount = count
		self.__last_insert_id = last_id

	def _clear_metadata(self):
		self.__last_rowcount = 0
		self.__last_insert_id = None

	def __fallo_transaccional(self):
		self._tx.fail()
		self.__last_rowcount = 0
		self.__last_insert_id = None

	@serialized
	def begin(self) -> bool:
		"""Abre una transacción del hilo actual, o un savepoint anidado."""
		self.__comprobar_abierta()
		self._ensure_clean()
		if self.__db is None:
			return False
		if not self.ping():
			raise RuntimeError("no hay una conexión activa; llamá a reconnect()")
		try:
			if self._tx.depth == 0:
				self.__previous_autocommit = self.__db.autocommit
				if self.__previous_autocommit:
					self.__db.autocommit = False
			else:
				self.__cursor.execute(f"SAVEPOINT easymysql_sp_{self._tx.depth}")
		except BaseException:
			self.__fallo_transaccional()
			raise
		self._tx.opened()
		return True

	@serialized
	def commit(self):
		"""Confirma el nivel actual; nunca reintenta un commit fallido."""
		self._tx.check_usable()
		if self.__db is None:
			return
		try:
			if self._tx.depth <= 1:
				self.__db.commit()
				if self.__previous_autocommit is not None:
					self.__db.autocommit = self.__previous_autocommit
					self.__previous_autocommit = None
				self._tx.clear()
				self._pending = False
			else:
				self.__cursor.execute(f"RELEASE SAVEPOINT easymysql_sp_{self._tx.depth - 1}")
				self._tx.ended()
		except BaseException:
			self.__fallo_transaccional()
			raise

	@serialized
	def rollback(self) -> bool:
		"""Revierte el nivel actual; tras un fallo de control, revierte todo.

		Un rollback posterior a un commit sin respuesta no demuestra que
		ese commit no se haya aplicado en el servidor.
		"""
		if self.__db is None:
			return False
		try:
			if self._tx.depth <= 1 or self._tx.failed:
				self.__db.rollback()
				if self.__previous_autocommit is not None:
					self.__db.autocommit = self.__previous_autocommit
					self.__previous_autocommit = None
				self._tx.clear()
				self._pending = False
			else:
				name = f"easymysql_sp_{self._tx.depth - 1}"
				self.__cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
				self.__cursor.execute(f"RELEASE SAVEPOINT {name}")
				self._tx.ended()
		except BaseException:
			self.__fallo_transaccional()
			raise
		self.__last_rowcount = 0
		self.__last_insert_id = None
		return True

	def is_in_transaction(self) -> bool:
		"""Indica niveles de la biblioteca; no cuenta transacciones implícitas/raw."""
		return self._tx.depth > 0

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


PostgreSQL = postgresql
