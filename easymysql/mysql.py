#!/usr/bin/python
# -*- coding: utf-8 -*-

import pymysql
import pymysql.cursors
import collections
from typing import Iterable, Union, Dict, Any
from connector import connector

class mysql(connector):

		#__cursor = None
		#__db = None
		#__result = None

		__hostname = ""
		__username = ""
		__password = ""
		__database = ""
		__in_transaction = False

		def __init__(self,hostname,username,password,database):

				self.__hostname = hostname
				self.__username = username
				self.__password = password
				self.__database = database
				self.__in_transaction = False

				self.connect()

		def __file__(self):
				return __file__

		def version(self):
				return "0.1.9.2"

		def ping(self):
				if self.__db is not None and self.__db.ping(reconnect=True):
						return True
				else:
						return False

		def connect(self):
				self.__db = pymysql.connect(host=self.__hostname, user=self.__username, password=self.__password, database=self.__database)

				self.__cursor = self.__db.cursor()

		def reconnect(self):
				self.connect()

		def execute(self,query):

				if self.ping() == False:
						self.reconnect()

				try:
					if self.__cursor is not None:
						self.__cursor.execute(query)

				except Exception as e:
						print("Exeception occured:{}".format(e))

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
				"""
				if self.ping() == False:
						self.reconnect()

				try:
					if self.__cursor is not None:
						self.__cursor.executemany(query, params)
						
						# Solo hacer commit automático si no estamos en una transacción
						if not self.__in_transaction and self.__db is not None:
							self.__db.commit()
							
				except Exception as e:
						print("Exception occurred:{}".format(e))

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
				"""
				if self.ping() == False:
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
						print("Exception occurred:{}".format(e))

		def query(self,query):

				if self.ping() == False:
						self.reconnect()

				try:
					if self.__cursor is not None:
						self.__cursor.execute(query)

						columns = map(lambda x:x[0], self.__cursor.description)
						result = [dict(zip(	 columns,row))   for row in self.__cursor.fetchall()]

						return result

				except Exception as e:
						print("Exeception occured:{}".format(e))

		def count(self):
			if self.__cursor is not None and self.__cursor.rowcount is not None:
				return self.__cursor.rowcount
			else:
				return 0

		def getLastId(self):
				if self.__cursor is not None and self.__cursor.lastrowid is not None and self.__cursor.lastrowid > 0:
					return self.__cursor.lastrowid
				else:
					return None

		def select(self,table,condition: Union[str, Dict[str, Any]]="",fields="*",order=""):

			# Procesar condición usando el helper
			processed_condition = self._process_condition(condition)

			if len(processed_condition) > 0:
				query = "SELECT " + fields + " FROM " + table + " WHERE " + processed_condition
			else:
				query = "SELECT " + fields + " FROM " + table

			if len(order)>0:
				query = query + " " + order

			self.execute(query)

			if self.__cursor is not None and self.__cursor.rowcount == 0:
				return []
			
			try:
				tmp = map(lambda x:x[0], self.__cursor.description)
			except:
				return []

			columns = []

			for column in tmp:
				columns.append(column)

			if self.__cursor is not None:
				return [dict(zip(	columns,row))   for row in self.__cursor.fetchall()]
			else:
				return []

		def insert(self,table,data):

				fields = ''
				values = '' 
				for key in data:
						fields = fields + "`" + key + "`,"
						values = str(values) + "\'" + str(data[key]) + "\',"

				if fields.endswith(","):
						fields = fields[0:-1]

				if values.endswith(","):
						values = values[0:-1]

				query = "INSERT INTO " + table + " (" + fields + ") VALUES (" + values + ");"

				#print(query)

				self.execute(query)

				# Solo hacer commit automático si no estamos en una transacción
				if not self.__in_transaction and self.__db is not None:
					self.__db.commit()

				return self.getLastId()

		def update(self,table,data,condition: Union[str, Dict[str, Any]]):

				values=''
				where=''

				if isinstance(data, dict):
						for key in data:
								values = str(values) + "`" + str(key) + "`='" + str(data[key]) + "', "

						if values.endswith(", "):
								values = values[0:-2]

				# Procesar condición usando el helper
				where = self._process_condition(condition)

				query = "UPDATE " + table + " SET " + values + " WHERE " + where + ";"

				self.execute(query)
				
				# Solo hacer commit automático si no estamos en una transacción
				if not self.__in_transaction and self.__db is not None:
					self.__db.commit()

		def delete(self,table,condition: Union[str, Dict[str, Any]]):

				# Procesar condición usando el helper
				processed_condition = self._process_condition(condition)

				query = "DELETE FROM " + table + " WHERE " + processed_condition + ";"

				self.execute(query)
				
				# Solo hacer commit automático si no estamos en una transacción
				if not self.__in_transaction and self.__db is not None:
					self.__db.commit()

		def close(self):
				if self.__db is not None:
					self.__db.close()

		def resetCache(self):
				if self.__cursor is not None:
					self.__cursor.execute("RESET QUERY CACHE;")

		def truncate(self,table):
			if len(table)>0 and self.__cursor is not None:
				self.__cursor.execute("TRUNCATE {};".format(table))

		def commit(self):
			if self.__db is not None:
				self.__db.commit()
				self.__in_transaction = False

		# Métodos para soporte de transacciones
		def begin(self):
			"""
			Inicia una nueva transacción.
			"""
			if self.__db is not None:
				self.__db.begin()
				self.__in_transaction = True
				return True
			return False

		def rollback(self):
			"""
			Revierte la transacción actual.
			"""
			if self.__db is not None:
				self.__db.rollback()
				self.__in_transaction = False
				return True
			return False

		def is_in_transaction(self):
			"""
			Retorna True si hay una transacción activa.
			"""
			return self.__in_transaction

		def transaction(self):
			"""
			Retorna un contexto de transacción que puede ser usado con 'with'.
			"""
			return TransactionContext(self)

		def _process_condition(self, condition):
				"""
				Procesa la condición convirtiendo diccionarios a string SQL WHERE.
				
				Args:
					condition: Puede ser string, diccionario, None o cualquier otro tipo
				
				Returns:
					str: Condición SQL formateada
				
				Examples:
					# String directo
					_process_condition("id = 1 AND activo = 1")
					# Resultado: "id = 1 AND activo = 1"
					
					# Diccionario
					_process_condition({"id": 1, "activo": 1})
					# Resultado: "`id`='1' AND `activo`='1'"
					
					# Diccionario con None
					_process_condition({"id": 1, "activo": None})
					# Resultado: "`id`='1' AND `activo` IS NULL"
					
					# Condición vacía
					_process_condition("")
					# Resultado: ""
					
					# None
					_process_condition(None)
					# Resultado: ""
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
										conditions.append(f"`{key}` IS NULL")
								else:
										# Escapar comillas simples para prevenir SQL injection
										escaped_value = str(value).replace("'", "''")
										conditions.append(f"`{key}`='{escaped_value}'")
						return " AND ".join(conditions)
				
				# Si es otro tipo iterable (como OrderedDict, etc.)
				if hasattr(condition, 'items'):
						conditions = []
						for key, value in condition.items():
								if value is None:
										conditions.append(f"`{key}` IS NULL")
								else:
										escaped_value = str(value).replace("'", "''")
										conditions.append(f"`{key}`='{escaped_value}'")
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