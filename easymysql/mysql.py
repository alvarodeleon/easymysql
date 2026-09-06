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
from typing import Iterable, Union, Dict, Any

import pymysql
import pymysql.cursors

logger = logging.getLogger(__name__)


from .connector import connector
from ._convenience import Convenience
from ._sql import MYSQL
from ._transaction import TransactionContext, TransactionState, serialized, data_operation
from .my_query import (
	condition_params, insert_params, update_params, delete_params, select_params,
)
	# `_table` y `_process_condition` empiezan con guion bajo: van aparte.
from .my_query import _process_condition, _table

class mysql(Convenience, connector):
	"""
	Conector MySQL.

	Las operaciones se serializan con un lock de instancia. Las transacciones
	abiertas con begin()/transaction() pertenecen al hilo que las inició:
	las operaciones de otros hilos se rechazan hasta que terminen.
	Para paralelismo o transacciones raw, usá una instancia por trabajador.
	"""

	_dialect = MYSQL

	def __init__(self,hostname,username,password,database,**kwargs):
		"""
		Args:
			hostname, username, password, database: conexión básica.
			**kwargs: se pasan tal cual a `pymysql.connect()` — `port`,
				`ssl`, `connect_timeout`, `read_timeout`, `unix_socket`,
				`charset`… Antes no había forma de indicar ninguno:
				era imposible conectar a un puerto no estándar o con TLS.

		`charset` vale 'utf8mb4' por defecto. Sin él, PyMySQL usa el del
		servidor: si es latin1, el texto UTF-8 se guarda corrupto.
		"""

			# Se inicializan antes de connect(): si la conexión falla, el
			# objeto queda utilizable para dar un error legible en vez de
			# un AttributeError sobre un atributo que nunca existió.
		self.__db = None
		self.__cursor = None
		self.__closed = False
		self._tx = TransactionState()
		self._pending = False
		self.__last_rowcount = 0
		self.__last_insert_id = None
		self._lock = threading.RLock()

		self.__hostname = hostname
		self.__username = username
		self.__password = password
		self.__database = database
		self.__opciones = dict(kwargs)
		self.__opciones.setdefault("charset", "utf8mb4")

		self.connect()

	def __file__(self):
		return __file__

	def version(self):
		from . import __version__
		return __version__

			# -- ciclo de vida ------------------------------------------------------

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()
		return False

	def ping(self):
		"""
		¿La conexión sigue viva?

		**No usar `Connection.ping()` de PyMySQL para esto: devuelve
		`None`, no un booleano.** El código anterior hacía
		`if self.__db.ping(reconnect=True): return True else: return False`,
		que evaluaba `bool(None)` y por lo tanto devolvía **siempre**
		`False`. Como `execute()` reconecta cuando `ping()` es falso,
		la librería abría una conexión nueva —con handshake de
		autenticación completo— **antes de cada sentencia**, y toda
		transacción se perdía en el `ROLLBACK` implícito de la
		reconexión.

		Se comprueba el estado local del socket, sin round-trip: si el
		servidor cerró la conexión por su cuenta, la próxima sentencia
		falla con `OperationalError` en vez de reconectar en silencio.
		"""
		if self.__db is None or self.__closed:
			return False
		try:
			return bool(self.__db.open)
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
			logger.exception("error conectando a MySQL")
			raise

	def __abrir_recursos(self):
		# Publicar los recursos solo después de que ambos existan.
		db = pymysql.connect(
			host=self.__hostname,
			user=self.__username,
			password=self.__password,
			database=self.__database,
			**self.__opciones,
		)
		try:
			cursor = db.cursor()
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

	def __comprobar_abierta(self):
		self._tx.check_usable()
		if self.__closed:
			raise RuntimeError("la conexión está cerrada")

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

	def count(self):
		"""
		Filas afectadas por la última operación exitosa.

		Antes devolvía `cursor.rowcount` crudo, que vale -1 antes de la
		primera sentencia y conserva el valor previo tras un fallo.

		⚠️ En un UPDATE, MySQL cuenta las filas **modificadas**, no las
		coincidentes: actualizar una fila con el valor que ya tenía
		devuelve 0. Si necesitás el conteo de coincidencias, construí la
		conexión con `client_flag=pymysql.constants.CLIENT.FOUND_ROWS`.
		"""
		return self.__last_rowcount

	def getLastId(self):
		"""
		ID generado por el último INSERT exitoso, o None.

		Antes leía `cursor.lastrowid` crudo, que sobrevive a una
		sentencia fallida y devolvía el ID de otra fila.
		"""
		return self.__last_insert_id

	@data_operation
	def select(self, table: str, condition: ConditionInput="", fields="*", order: str="", *,
	           order_by=None, limit: Union[int, None]=None, offset: Union[int, None]=None,
	           group_by=None, having=None, for_update: bool=False) -> list[Row]:

		# La construcción del SQL vive en my_query, igual que postgres.py
		# delega en pg_query. Antes estaba duplicada acá y las dos copias
		# ya habían divergido.
		clauses = dict(order_by=order_by, limit=limit, offset=offset, group_by=group_by,
		               having=having, for_update=for_update)
		if for_update and not self.is_in_transaction():
			raise RuntimeError("for_update requiere transaction()")
		sql, params = select_params(table,condition,fields,order, **clauses)

			# Antes se decidía por rowcount y se envolvía el acceso a
			# description en un `except:` desnudo, con lo que "cero filas" y
			# "la consulta falló" devolvían lo mismo: [].
		return self.query(sql,params)

	@data_operation
	def insert(self, table: str, data: Row) -> Any:

		# Antes se interpolaba str(data[key]) en crudo, sin ningún
		# escapado. Ahora los valores viajan como parámetros: el driver
		# se encarga del quoting y de convertir bool, bytes, datetime y
		# Decimal al tipo correcto de la columna.
		self._ensure_clean()
		sql, params = insert_params(table,data)

			# execute + commit + lectura del ID van bajo el mismo lock: si
			# otro hilo inserta entremedio, getLastId() devolvería su ID.
		self._execute(sql,params)
		self.__autocommit()
		return self.getLastId()

	@data_operation
	def update(self,table,data,condition: ConditionInput):

		self._ensure_clean()
		sql, params = update_params(table,data,condition)

		self._execute(sql,params)
		self.__autocommit()

	@data_operation
	def delete(self,table,condition: ConditionInput):

		self._ensure_clean()
		sql, params = delete_params(table,condition)

		self._execute(sql,params)
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

	@data_operation
	def resetSession(self):
		"""
		Devuelve la sesión al estado que tenía recién conectada: se van
		las tablas temporales, las variables de usuario y el resto del
		estado de sesión.

		Reemplaza al viejo `resetCache()`, que ejecutaba `RESET QUERY
		CACHE`: el query cache no existe desde MySQL 8.0, así que esa
		sentencia falla con un error de sintaxis en cualquier servidor
		soportado hoy.

		Se implementa reconectando. El equivalente exacto sería
		`COM_RESET_CONNECTION`, pero PyMySQL no lo expone -- no está en
		`pymysql.constants.COMMAND` ni hay método en `Connection` -- y
		llegar a él obliga a usar API privada y a reponer el charset a
		mano, porque el servidor vuelve al suyo y el driver no se entera.
		Reconectar da el mismo estado observable y repone charset y
		opciones en el handshake. El costo es un round trip y un
		connection id nuevo.
		"""
		self.__comprobar_abierta()
		if self._tx.depth > 0:
			raise RuntimeError(
				"no se puede resetear la sesión con una transacción "
				"abierta: se perdería el trabajo no commiteado"
			)
		self.reconnect()

	@data_operation
	def truncate(self, table):
		"""TRUNCATE explícito; su atomicidad depende del motor."""
		self._ensure_clean()
		self._execute("TRUNCATE {}".format(_table(table)))
		self.__autocommit()

			# -- transacciones ------------------------------------------------------
			#
			# La profundidad es un contador, no un booleano: antes, salir de un
			# `with` anidado commiteaba y reactivaba el autocommit dentro de la
			# transacción externa.

	def __autocommit(self):
		"""Commitea solo si no hay ninguna transacción abierta."""
		if self._tx.depth == 0 and self.__db is not None:
			self.commit()

	def _native_pending(self):
		if self.__db is None or not self.ping():
			return None
		status = getattr(self.__db, "server_status", None)
		return bool(status & 1) if isinstance(status, int) else None

	def _driver_autocommit(self):
		get_autocommit = getattr(self.__db, "get_autocommit", None)
		return get_autocommit() is True if get_autocommit is not None else False

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
		lastrowid = getattr(self.__cursor, "lastrowid", None)
		if self.__cursor.description is None and lastrowid:
			self.__last_insert_id = lastrowid

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
				self.__db.begin()
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
		"""
		Contexto de transacción para usar con `with`.
		"""
		return TransactionContext(self)

	def _process_condition(self, condition):
		"""
		Heredado: delega en my_query._process_condition.

		Esta copia generaba `id`='1' mientras my_query generaba `id` = '1'
		para la misma entrada. Ya no la usa ningún método de la clase:
		insert/update/delete/select pasan por los builders parametrizados.
		"""
		return _process_condition(condition)


MySQL = mysql
