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
from typing import Iterable, Union, Dict, Any

import pymysql
import pymysql.cursors

logger = logging.getLogger(__name__)

# 2006 "MySQL server has gone away", 2013 "Lost connection during query".
# Son los códigos con los que el servidor avisa que cerró la conexión, casi
# siempre por `wait_timeout`.
_CODIGOS_CONEXION_CAIDA = (2006, 2013)


def _es_conexion_caida(exc) -> bool:
	"""¿La excepción indica que el servidor cerró la conexión?"""
	if not isinstance(exc, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
		return False
	return bool(exc.args) and exc.args[0] in _CODIGOS_CONEXION_CAIDA

from .connector import connector
from .my_query import *
# `import *` no trae los nombres que empiezan con guion bajo.
from .my_query import _process_condition

class mysql(connector):
		"""
		Conector MySQL.

		**Concurrencia:** todas las operaciones se serializan con un lock de
		instancia. Compartir una instancia entre hilos es seguro pero no
		paralelo: las consultas se encolan. Para paralelismo real usá una
		instancia por hilo o un pool de conexiones.

		Antes no había ningún lock y los hilos se robaban el resultset entre
		sí: cuatro hilos consultando cuatro tablas distintas recibían todos
		las filas del último execute, sin ningún error.
		"""

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
				self.__tx_depth = 0
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

		def connect(self):
				self.__db = pymysql.connect(
					host=self.__hostname,
					user=self.__username,
					password=self.__password,
					database=self.__database,
					**self.__opciones,
				)
				self.__cursor = self.__db.cursor()
				self.__closed = False

		def reconnect(self):
				"""
				Reconecta cerrando primero la conexión anterior.

				Antes era un alias de connect(): la conexión vieja quedaba
				huérfana y se acumulaban sockets y sesiones en el servidor
				hasta agotar max_connections.
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

		def __comprobar_abierta(self):
				if self.__closed:
						raise RuntimeError("la conexión está cerrada")

		def execute(self,query,params=None):
				"""
				Ejecuta una sentencia SQL.

				Los errores se propagan. Antes se capturaban y se imprimían por
				stdout: el llamante no podía saber que la sentencia había
				fallado y seguía leyendo `lastrowid`, `rowcount` y `description`
				del cursor, que conservaban los valores de la sentencia
				anterior.

				Raises:
					RuntimeError: si la conexión está cerrada.
					pymysql.MySQLError: cualquier error de la base de datos.
				"""
				with self._lock:
						self.__comprobar_abierta()

						if self.ping() == False:
								self.reconnect()

						if self.__cursor is None:
								raise RuntimeError("no hay una conexión activa; llamá a connect()")

						# Se invalidan antes de ejecutar: si la sentencia falla,
						# count() y getLastId() no deben devolver los valores de
						# la operación anterior.
						self.__last_rowcount = 0
						self.__last_insert_id = None

						try:
								self.__cursor.execute(query,params)
						except Exception as e:
								# El servidor puede haber cerrado la conexión por
								# `wait_timeout` sin que el socket local se entere.
								# Se reintenta UNA vez y **sólo fuera de
								# transacción**: reconectar dentro de una haría
								# ROLLBACK implícito y perdería el trabajo en
								# silencio, que es el mecanismo de C-06.
								if self.__tx_depth > 0 or not _es_conexion_caida(e):
										raise
								logger.info("conexión caída (%s); reconectando y reintentando", e)
								self.reconnect()
								self.__cursor.execute(query,params)

						self.__last_rowcount = self.__cursor.rowcount if self.__cursor.rowcount is not None and self.__cursor.rowcount >= 0 else 0
						lastrowid = getattr(self.__cursor, "lastrowid", None)
						if self.__cursor.description is None and lastrowid:
								self.__last_insert_id = lastrowid

		def executemany(self, query, params):
				"""
				Ejecuta la misma consulta múltiples veces con diferentes parámetros.
				
				Args:
					query (str): Consulta SQL con placeholders (%s, %d, etc.)
					params (list): Lista de tuplas con los parámetros para cada ejecución
				
				Example:
					query = "INSERT INTO usuarios (nombre, email) VALUES (%s, %s)"
					params = [("Juan", "juan@example.com"), ("María", "maria@example.com")]
					db.executemany(query, params)

				Raises:
					TypeError: si params no es una secuencia de tuplas/listas.
					pymysql.MySQLError: cualquier error de la base de datos.
				"""
				if isinstance(params, (str, bytes)) or not isinstance(params, collections.abc.Sequence):
						raise TypeError(
							"params debe ser una secuencia de tuplas, no {}".format(type(params).__name__)
						)

				with self._lock:
						self.__comprobar_abierta()

						if self.ping() == False:
								self.reconnect()

						if self.__cursor is None:
								raise RuntimeError("no hay una conexión activa; llamá a connect()")

						self.__last_rowcount = 0
						self.__last_insert_id = None

						self.__cursor.executemany(query, params)
						self.__last_rowcount = max(0, self.__cursor.rowcount or 0)

						# El commit solo se alcanza si executemany() no lanzó.
						self.__autocommit()

		def execute_multiple(self, queries):
				"""
				Ejecuta múltiples consultas SQL de forma secuencial.
				
				Args:
					queries (list): Lista de consultas SQL a ejecutar
				
				Example:
					queries = [
						"INSERT INTO usuarios (nombre, email) VALUES ('Juan', 'juan@example.com')",
						"INSERT INTO usuarios (nombre, email) VALUES ('María', 'maria@example.com')",
						"UPDATE contadores SET valor = valor + 2 WHERE id = 1"
					]
					db.execute_multiple(queries)

				El lote se valida entero antes de ejecutar nada: antes se
				detenía en el primer elemento no-string y commiteaba lo que
				hubiera alcanzado a ejecutar.

				Raises:
					TypeError: si algún elemento de la lista no es un string.
					pymysql.MySQLError: cualquier error de la base de datos.
				"""
				for i, query in enumerate(queries):
						if not isinstance(query, str):
								raise TypeError(
									"queries[{}] no es un string: {}".format(i, type(query).__name__)
								)

				pendientes = [q.strip() for q in queries if q.strip()]

				with self._lock:
						self.__comprobar_abierta()

						if self.ping() == False:
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

		def query(self,query,params=None):
				"""
				Ejecuta una consulta y devuelve la lista de filas como dicts.

				Raises:
					pymysql.MySQLError: cualquier error de la base de datos.
				"""
				# El execute y el fetch van bajo el mismo lock: si otro hilo
				# ejecuta entremedio, el cursor compartido devuelve sus filas.
				with self._lock:
						self.execute(query,params)

						# description es None cuando la consulta no devuelve filas (INSERT, UPDATE, ...)
						if self.__cursor.description is None:
							return []

						# La lista se materializa: un iterador de map() se agota en la
						# primera fila y las siguientes saldrían como diccionarios vacíos.
						columns = [x[0] for x in self.__cursor.description]

						return [dict(zip(columns,row))   for row in self.__cursor.fetchall()]

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

		def select(self,table,condition: Union[str, Dict[str, Any]]="",fields="*",order=""):

			# La construcción del SQL vive en my_query, igual que postgres.py
			# delega en pg_query. Antes estaba duplicada acá y las dos copias
			# ya habían divergido.
			sql, params = select_params(table,condition,fields,order)

			# Antes se decidía por rowcount y se envolvía el acceso a
			# description en un `except:` desnudo, con lo que "cero filas" y
			# "la consulta falló" devolvían lo mismo: [].
			return self.query(sql,params)

		def insert(self,table,data):

				# Antes se interpolaba str(data[key]) en crudo, sin ningún
				# escapado. Ahora los valores viajan como parámetros: el driver
				# se encarga del quoting y de convertir bool, bytes, datetime y
				# Decimal al tipo correcto de la columna.
				sql, params = insert_params(table,data)

				# execute + commit + lectura del ID van bajo el mismo lock: si
				# otro hilo inserta entremedio, getLastId() devolvería su ID.
				with self._lock:
						self.execute(sql,params)
						self.__autocommit()
						return self.getLastId()

		def update(self,table,data,condition: Union[str, Dict[str, Any]]):

				sql, params = update_params(table,data,condition)

				with self._lock:
						self.execute(sql,params)
						self.__autocommit()

		def delete(self,table,condition: Union[str, Dict[str, Any]]):

				sql, params = delete_params(table,condition)

				with self._lock:
						self.execute(sql,params)
						self.__autocommit()

		def close(self):
				"""
				Cierra la conexión.

				Si hay una transacción abierta, revierte explícitamente y avisa:
				antes el cierre provocaba un ROLLBACK implícito del servidor sin
				ninguna señal, y el trabajo no commiteado desaparecía.
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

		def resetCache(self):
				"""
				DEPRECADO. El query cache **no existe desde MySQL 8.0**: fue
				eliminado en esa versión, así que esta sentencia siempre falla.
				En versiones anteriores requiere el privilegio `RELOAD`.
				"""
				warnings.warn(
					"resetCache() ejecuta RESET QUERY CACHE, que no existe desde "
					"MySQL 8.0. El método se eliminará en una versión futura.",
					DeprecationWarning,
					stacklevel=2,
				)
				self.execute("RESET QUERY CACHE")

		def truncate(self,table):
			self.execute("TRUNCATE {}".format(_table(table)))

		# -- transacciones ------------------------------------------------------
		#
		# La profundidad es un contador, no un booleano: antes, salir de un
		# `with` anidado commiteaba y reactivaba el autocommit dentro de la
		# transacción externa.

		def __autocommit(self):
			"""Commitea solo si no hay ninguna transacción abierta."""
			if self.__tx_depth == 0 and self.__db is not None:
				self.__db.commit()

		def begin(self):
			"""
			Abre una transacción, o un SAVEPOINT si ya hay una abierta.
			"""
			with self._lock:
				self.__comprobar_abierta()
				if self.__db is None:
					return False

				if self.__tx_depth == 0:
					self.__db.begin()
				else:
					self.execute("SAVEPOINT easymysql_sp_{}".format(self.__tx_depth))

				self.__tx_depth += 1
				return True

		def commit(self):
			"""
			Cierra el nivel de transacción actual. Solo commitea de verdad al
			salir del nivel más externo.
			"""
			with self._lock:
				if self.__db is None:
					return

				if self.__tx_depth <= 1:
					self.__db.commit()
					self.__tx_depth = 0
				else:
					self.__tx_depth -= 1
					self.execute("RELEASE SAVEPOINT easymysql_sp_{}".format(self.__tx_depth))

		def rollback(self):
			"""
			Revierte el nivel actual: la transacción entera si es el más
			externo, o hasta el SAVEPOINT si es anidado.
			"""
			with self._lock:
				if self.__db is None:
					return False

				if self.__tx_depth <= 1:
					self.__db.rollback()
					self.__tx_depth = 0
				else:
					self.__tx_depth -= 1
					self.execute("ROLLBACK TO SAVEPOINT easymysql_sp_{}".format(self.__tx_depth))
				return True

		def is_in_transaction(self):
			return self.__tx_depth > 0

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