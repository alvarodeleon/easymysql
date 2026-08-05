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

"""
Constructores de condiciones parametrizadas.

Los operadores históricos (`equals`, `like`, `between`, …) devuelven un string
con el valor ya interpolado, lo que en MySQL es evadible con un backslash. No
se pueden arreglar sin romper su firma, porque un parámetro no sobrevive a una
interpolación en un f-string.

Este módulo ofrece la alternativa: cada constructor devuelve un `Condition`,
que lleva el SQL y los parámetros por separado hasta el driver.

	from easymysql.my_query import where

	c = where.equals("activo", True) & where.greater_than("stock", 0)
	db.select("productos", c)

También se puede componer con `where.all_(...)` / `where.any_(...)`, que es lo
mismo que `&` y `|` pero para listas.
"""

import json
import math
from typing import Any


def adapt(value):
	"""
	Normaliza un valor antes de entregarlo al driver.

	El driver ya convierte bien `bool`, `bytes`, `datetime`, `Decimal` y
	`None`: esos se pasan intactos. Solo hacen falta dos ajustes:

	- `NaN` e `Inf` no tienen representación en SQL. Antes se serializaban
	  como los textos 'nan' e 'inf' y el error de conversión se tragaba.
	- `dict` y `list` se serializan como JSON. Antes se guardaba el repr de
	  Python (`{'k': 'v'}`, con comillas simples), que `json.loads` no puede
	  leer después.
	"""
	if isinstance(value, float) and not math.isfinite(value):
		raise ValueError(
			"no se puede almacenar {!r}: NaN e infinito no tienen "
			"representación en SQL".format(value)
		)

	if isinstance(value, (dict, list)):
		return json.dumps(value, ensure_ascii=False)

	return value


class Condition:
	"""
	Fragmento de SQL con sus parámetros.

	Se compone con `&` (AND), `|` (OR) y `~` (NOT). La composición mantiene el
	orden de los parámetros y parentiza cada operando, de modo que mezclar AND
	y OR no cambia el significado por precedencia.
	"""

	__slots__ = ("sql", "params")

	def __init__(self, sql: str, params=()):
		self.sql = sql
		self.params = tuple(params)

	# -- composición --------------------------------------------------------

	def __and__(self, other):
		return self._combine(other, "AND")

	def __or__(self, other):
		return self._combine(other, "OR")

	def __invert__(self):
		return Condition(f"NOT ({self.sql})", self.params)

	def _combine(self, other, op):
		if not isinstance(other, Condition):
			return NotImplemented
		return Condition(
			f"({self.sql} {op} {other.sql})",
			self.params + other.params,
		)

	# -- consumo ------------------------------------------------------------

	def __iter__(self):
		"""Permite `sql, params = condicion`."""
		return iter((self.sql, self.params))

	def __eq__(self, other):
		if isinstance(other, Condition):
			return self.sql == other.sql and self.params == other.params
		return NotImplemented

	def __hash__(self):
		return hash((self.sql, self.params))

	def __repr__(self):
		return f"Condition({self.sql!r}, {self.params!r})"

	def __str__(self):
		raise TypeError(
			"un Condition no se puede interpolar en un string: los parámetros "
			"se perderían y el SQL quedaría con placeholders sueltos.\n"
			"Pasalo directamente:  db.select(tabla, condicion)\n"
			"O desarmalo:          sql, params = condicion\n"
			f"Para inspeccionarlo:  repr() -> {self.sql!r} {self.params!r}"
		)


TRUE = Condition("1=1")
FALSE = Condition("1=0")


def _escape_like(value) -> str:
	"""
	Escapa los comodines de LIKE.

	Sin esto, buscar "50%" devuelve 50, 500 y 5012, y `starts_with(campo, '%')`
	genera `LIKE '%%'`, que matchea todas las filas y anula el filtro.
	"""
	return (str(value)
	        .replace("\\", "\\\\")
	        .replace("%", "\\%")
	        .replace("_", "\\_"))


class ConditionBuilder:
	"""
	Constructores de `Condition` ligados a un dialecto.

	Se expone como `my_query.where` y `pg_query.where`.
	"""

	def __init__(self, dialect):
		self._d = dialect

	# -- helpers ------------------------------------------------------------

	def _f(self, field) -> str:
		return self._d.ident(field)

	def raw(self, sql: str, params=()) -> Condition:
		"""
		Envuelve SQL crudo. Es la vía de escape para lo que no cubren los
		constructores; los valores deben ir en `params`, no en el string.
		"""
		return Condition(sql, params)

	# -- composición --------------------------------------------------------

	def all_(self, *conditions) -> Condition:
		"""AND de todas. Sin argumentos devuelve `1=1` (no filtra nada)."""
		return self._join(conditions, "AND", TRUE)

	def any_(self, *conditions) -> Condition:
		"""OR de todas. Sin argumentos devuelve `1=0` (no matchea nada)."""
		return self._join(conditions, "OR", FALSE)

	def not_(self, condition: Condition) -> Condition:
		return ~condition

	def _join(self, conditions, op, vacio):
		reales = [c for c in conditions if c is not None]
		for c in reales:
			if not isinstance(c, Condition):
				raise TypeError(
					f"se esperaba un Condition, no {type(c).__name__}. "
					"Usá where.raw(sql, params) para SQL crudo."
				)
		if not reales:
			return vacio
		if len(reales) == 1:
			return reales[0]
		sql = f" {op} ".join(f"({c.sql})" for c in reales)
		params = tuple(p for c in reales for p in c.params)
		return Condition(f"({sql})", params)

	# -- comparación --------------------------------------------------------

	def equals(self, field, value) -> Condition:
		if value is None:
			return self.is_null(field)
		return Condition(f"{self._f(field)} = %s", (adapt(value),))

	def not_equals(self, field, value) -> Condition:
		if value is None:
			return self.is_not_null(field)
		return Condition(f"{self._f(field)} != %s", (adapt(value),))

	def greater_than(self, field, value) -> Condition:
		return Condition(f"{self._f(field)} > %s", (adapt(value),))

	def greater_than_or_equal(self, field, value) -> Condition:
		return Condition(f"{self._f(field)} >= %s", (adapt(value),))

	def less_than(self, field, value) -> Condition:
		return Condition(f"{self._f(field)} < %s", (adapt(value),))

	def less_than_or_equal(self, field, value) -> Condition:
		return Condition(f"{self._f(field)} <= %s", (adapt(value),))

	# -- rango --------------------------------------------------------------

	def between(self, field, value1, value2) -> Condition:
		return Condition(f"{self._f(field)} BETWEEN %s AND %s", (adapt(value1), adapt(value2)))

	def not_between(self, field, value1, value2) -> Condition:
		return Condition(f"{self._f(field)} NOT BETWEEN %s AND %s", (adapt(value1), adapt(value2)))

	# -- pertenencia --------------------------------------------------------

	def in_list(self, field, values) -> Condition:
		"""
		Con una lista vacía devuelve `1=0`: el conjunto vacío no matchea nada.
		El operador histórico generaba `IN ('')`, que matchea la cadena vacía.
		"""
		values = list(values)
		if not values:
			return FALSE
		marks = ", ".join(["%s"] * len(values))
		return Condition(f"{self._f(field)} IN ({marks})", tuple(adapt(v) for v in values))

	def not_in_list(self, field, values) -> Condition:
		"""
		Con una lista vacía devuelve `1=1`: sin exclusiones, matchea todo.
		El operador histórico generaba `NOT IN ('')`, que devolvía **todas**
		las filas y podía usarse para saltear un filtro de permisos.
		"""
		values = list(values)
		if not values:
			return TRUE
		marks = ", ".join(["%s"] * len(values))
		return Condition(f"{self._f(field)} NOT IN ({marks})", tuple(adapt(v) for v in values))

	# -- nulidad ------------------------------------------------------------

	def is_null(self, field) -> Condition:
		return Condition(f"{self._f(field)} IS NULL")

	def is_not_null(self, field) -> Condition:
		return Condition(f"{self._f(field)} IS NOT NULL")

	# -- texto --------------------------------------------------------------

	def contains(self, field, value) -> Condition:
		return self._like(field, f"%{_escape_like(value)}%")

	def not_contains(self, field, value) -> Condition:
		return self._like(field, f"%{_escape_like(value)}%", negado=True)

	def starts_with(self, field, value) -> Condition:
		return self._like(field, f"{_escape_like(value)}%")

	def ends_with(self, field, value) -> Condition:
		return self._like(field, f"%{_escape_like(value)}")

	def like(self, field, patron) -> Condition:
		"""
		LIKE con el patrón tal cual: los `%` y `_` del argumento **sí** son
		comodines. Para buscar un literal usá contains/starts_with/ends_with.
		"""
		return Condition(f"{self._f(field)} LIKE %s", (patron,))

	def not_like(self, field, patron) -> Condition:
		return Condition(f"{self._f(field)} NOT LIKE %s", (patron,))

	def ilike(self, field, patron) -> Condition:
		"""LIKE sin distinguir mayúsculas. Sólo PostgreSQL."""
		if self._d.name != "postgres":
			raise NotImplementedError(
				"ILIKE es de PostgreSQL. En MySQL la comparación de texto ya es "
				"insensible a mayúsculas con las collations _ci."
			)
		return Condition(f"{self._f(field)} ILIKE %s", (patron,))

	def icontains(self, field, value) -> Condition:
		"""Contiene, sin distinguir mayúsculas. Sólo PostgreSQL."""
		return self.ilike(field, f"%{_escape_like(value)}%")

	def _like(self, field, patron, negado=False):
		op = "NOT LIKE" if negado else "LIKE"
		return Condition(f"{self._f(field)} {op} %s ESCAPE '\\\\'", (patron,))

	# -- fechas -------------------------------------------------------------
	#
	# Se usan rangos en lugar de DATE(columna): aplicar una función sobre la
	# columna invalida el índice y fuerza un full scan.

	def date_equals(self, field, date) -> Condition:
		return Condition(
			f"{self._f(field)} >= %s AND {self._f(field)} < %s + INTERVAL '1 day'"
			if self._d.name == "postgres" else
			f"{self._f(field)} >= %s AND {self._f(field)} < DATE_ADD(%s, INTERVAL 1 DAY)",
			(date, date),
		)

	def date_greater_than(self, field, date) -> Condition:
		return Condition(f"{self._f(field)} > %s", (date,))

	def date_less_than(self, field, date) -> Condition:
		return Condition(f"{self._f(field)} < %s", (date,))

	def date_between(self, field, start_date, end_date) -> Condition:
		return Condition(
			f"{self._f(field)} BETWEEN %s AND %s", (start_date, end_date)
		)


# ---------------------------------------------------------------------------
# Cláusulas que no son condiciones
# ---------------------------------------------------------------------------

def order_by(field, direction="ASC", dialect=None) -> str:
	"""
	ORDER BY con la dirección validada.

	El operador histórico interpolaba `direction` en crudo:
	`order_by('a', 'ASC; DROP TABLE t')` generaba SQL ejecutable.
	"""
	if str(direction).upper() not in ("ASC", "DESC"):
		raise ValueError(f"direction debe ser ASC o DESC, no {direction!r}")
	campo = dialect.ident(field) if dialect is not None else field
	return f"ORDER BY {campo} {str(direction).upper()}"


def limit_query(limit, offset=None, dialect=None) -> str:
	"""
	LIMIT con los valores convertidos a entero.

	El operador histórico interpolaba en crudo: `limit_query('1; DROP TABLE t')`
	generaba SQL ejecutable.
	"""
	limit = int(limit)
	if limit < 0:
		raise ValueError("limit no puede ser negativo")

	if offset is None:
		return f"LIMIT {limit}"

	offset = int(offset)
	if offset < 0:
		raise ValueError("offset no puede ser negativo")

	if dialect is not None and dialect.name == "postgres":
		return f"LIMIT {limit} OFFSET {offset}"
	return f"LIMIT {offset}, {limit}"
