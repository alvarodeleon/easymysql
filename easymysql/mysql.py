#!/usr/bin/python
# -*- coding: utf-8 -*-

import pymysql
import collections

class mysql:

		__cursor = None
		__db = None
		__result = None

		__hostname = ""
		__username = ""
		__password = ""
		__database = ""

		def __init__(self,hostname,username,password,database):

				self.__hostname = hostname
				self.__username = username
				self.__password = password
				self.__database = database

				self.connect()

		def version(self):
				return "0.1.9.1"

		def ping(self):
				if self.__db.ping(reconnect=True):
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
						self.__cursor.execute(query)

				except Exception as e:
						print("Exeception occured:{}".format(e))

		def query(self,query):

				if self.ping() == False:
						self.reconnect()

				try:
						self.__cursor.execute(query)

						columns = map(lambda x:x[0], self.__cursor.description)
						result = [dict(zip(	 columns,row))   for row in self.__cursor.fetchall()]

						return result

				except Exception as e:
						print("Exeception occured:{}".format(e))

		def count(self):
				return self.__cursor.rowcount

		def getLastId(self):
				return self.__cursor.lastrowid

		def select(self,table,condition="",fields="*",order=""):

			if not isinstance(condition,str) and isinstance(condition,collections.Iterable):
				tmp=""
				for key in condition:
					tmp = tmp + str(key) + "=\'" + str(condition[key]) + "\' AND "

				if tmp.endswith("AND "):
					tmp = tmp[0:-4]

				condition = tmp

			if len(condition) > 0:
				query = "SELECT " + fields + " FROM " + table + " WHERE " + condition
			else:
				query = "SELECT " + fields + " FROM " + table

			if len(order)>0:
				query = query + " " + order

			self.execute(query)

			tmp = map(lambda x:x[0], self.__cursor.description)

			columns = []

			for column in tmp:
				columns.append(column)

			result = [dict(zip(	columns,row))   for row in self.__cursor.fetchall()]

			return result

		def insert(self,table,data):

				fields = ''
				values = '' 
				for key in data:
						fields = fields + key + ","
						values = str(values) + "\'" + str(data[key]) + "\',"

				if fields.endswith(","):
						fields = fields[0:-1]

				if values.endswith(","):
						values = values[0:-1]

				query = "INSERT INTO " + table + " (" + fields + ") VALUES (" + values + ");"

				self.execute(query)
				self.__db.commit()

				return self.__cursor.lastrowid

		def update(self,table,data,condition):

				values=''
				where=''

				if not isinstance(data,str) and isinstance(data,collections.Iterable):
						for key in data:
								values = str(values) + str(key) + "='" + str(data[key]) + "', "

						if values.endswith(", "):
								values = values[0:-2]

				if not isinstance(condition,str) and isinstance(condition,collections.Iterable):
						for key in condition:
								where = str(where) + str(key) + "='" + str(condition[key]) + "' AND "

						if where.endswith(" "):
								where = where[0:-5]
				else:
						where = condition

				query = "UPDATE " + table + " SET " + values + " WHERE " + where + ";"

				self.execute(query)
				self.__db.commit()




		def delete(self,table,condition):

				if not isinstance(condition,str) and isinstance(condition,collections.Iterable):
						tmp=""
						for key in condition:
								tmp = tmp + str(key) + "=\'" + str(condition[key]) + "\' AND " 

						if tmp.endswith("AND "):
								tmp = tmp[0:-4]

						condition = tmp

				query = "DELETE FROM " + table + " WHERE " + condition + ";"

				self.execute(query)
				self.__db.commit()

		def close(self):
				self.__db.close()

		def resetCache(self):
			self.__db.execute("RESET QUERY CACHE;")

		def truncate(self,table):
			if len(table)>0:
				self.__db.execute("TRUNCATE {};".format(table))