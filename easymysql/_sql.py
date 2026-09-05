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
Motor común de construcción de SQL, parametrizado por dialecto.

Existía una copia de esta lógica en cada uno de los cuatro módulos
(`mysql.py`, `postgres.py`, `my_query.py`, `pg_query.py`) y las copias ya
habían divergido: `mysql.py` generaba `` `id`='1' `` y `my_query.py`
`` `id` = '1' `` para la misma entrada. Cualquier corrección de seguridad
había que aplicarla cuatro veces, y olvidar una dejaba el agujero abierto.
"""

from typing import Any, Dict, Union

from ._conditions import Condition, adapt

# Tanto PyMySQL como psycopg2 usan el estilo de placeholder `format`.
PLACEHOLDER = "%s"


class Dialect:
	"""
	Diferencias entre motores. Hoy sólo cambia el delimitador de
	identificadores y el soporte de RETURNING.
	"""

	def __init__(self, name: str, quote: str, supports_returning: bool):
		self.name = name
		self.quote = quote
		self.supports_returning = supports_returning

	def ident(self, name) -> str:
		"""Delimita un identificador simple (columna)."""
		if not isinstance(name, str):
			raise TypeError(
				f"el identificador debe ser un string, no {type(name).__name__}"
			)
		if not name or "\x00" in name:
			raise ValueError(f"identificador inválido: {name!r}")
		q = self.quote
		return q + name.replace(q, q + q) + q

	def table(self, name) -> str:
		"""
		Delimita un nombre de tabla, admitiendo la forma `esquema.tabla`:
		cada parte se delimita por separado para no generar
		`` `esquema.tabla` ``, que sería un único identificador con un punto.
		"""
		if not isinstance(name, str):
			raise TypeError(
				f"el nombre de tabla debe ser un string, no {type(name).__name__}"
			)
		if not name or "\x00" in name:
			raise ValueError(f"nombre de tabla inválido: {name!r}")
		return ".".join(self.ident(part) for part in name.split("."))


MYSQL = Dialect("mysql", "`", supports_returning=False)
POSTGRES = Dialect("postgres", '"', supports_returning=True)


# ---------------------------------------------------------------------------
# Construcción parametrizada
# ---------------------------------------------------------------------------

def condition_params(condition: Union[str, Dict[str, Any], None], dialect: Dialect):
	"""
	Convierte una condición en (fragmento_sql, params).

	Un string se devuelve tal cual y sin parámetros: es SQL crudo y su
	seguridad queda a cargo del llamante. Un diccionario se parametriza.

	Raises:
		TypeError: para cualquier otro tipo. Antes se hacía `str(condition)`,
		con lo que `delete(tabla, 1)` generaba `WHERE 1` y borraba la tabla
		entera.
	"""
	# Un Condition ya trae sus parámetros separados del SQL.
	if isinstance(condition, Condition):
		return condition.sql, condition.params

	if condition is None or condition == "":
		return "", ()

	if isinstance(condition, str):
		return condition, ()

	if hasattr(condition, 'items'):
		if not condition:
			return "", ()

		parts = []
		params = []
		for key, value in condition.items():
			if value is None:
				parts.append(f"{dialect.ident(key)} IS NULL")
			else:
				parts.append(f"{dialect.ident(key)} = {PLACEHOLDER}")
				params.append(adapt(value))
		return " AND ".join(parts), tuple(params)

	raise TypeError(
		f"condition debe ser str, dict o Condition, no {type(condition).__name__}"
	)


def insert_params(table: str, data: dict, dialect: Dialect, returning=None):
	"""
	Devuelve (sql, params) para un INSERT.

	`returning` sólo se aplica en dialectos que lo soportan.
	"""
	if not isinstance(data, dict):
		raise TypeError(f"data debe ser un diccionario, no {type(data).__name__}")
	if not data:
		raise ValueError("data no puede estar vacío")

	cols = ", ".join(dialect.ident(k) for k in data)
	marks = ", ".join([PLACEHOLDER] * len(data))
	sql = f"INSERT INTO {dialect.table(table)} ({cols}) VALUES ({marks})"

	if returning and dialect.supports_returning:
		sql += f" RETURNING {dialect.ident(returning)}"

	return sql, tuple(adapt(v) for v in data.values())


def update_params(table: str, data: dict, condition, dialect: Dialect):
	"""Devuelve (sql, params) para un UPDATE."""
	if not isinstance(data, dict):
		raise TypeError(f"data debe ser un diccionario, no {type(data).__name__}")
	if not data:
		raise ValueError("data no puede estar vacío")

	sets = ", ".join(f"{dialect.ident(k)} = {PLACEHOLDER}" for k in data)
	params = [adapt(v) for v in data.values()]

	where, where_params = condition_params(condition, dialect)
	if not where.strip():
		raise ValueError(
			"update() requiere una condición WHERE no vacía. "
			"Para actualizar la tabla entera, pasá '1=1' explícitamente."
		)
	params.extend(where_params)

	return f"UPDATE {dialect.table(table)} SET {sets} WHERE {where}", tuple(params)


def delete_params(table: str, condition, dialect: Dialect):
	"""Devuelve (sql, params) para un DELETE."""
	where, params = condition_params(condition, dialect)
	if not where.strip():
		raise ValueError(
			"delete() requiere una condición WHERE no vacía. "
			"Para vaciar la tabla, usá truncate() o pasá '1=1' explícitamente."
		)
	return f"DELETE FROM {dialect.table(table)} WHERE {where}", params


def select_params(table: str, condition, fields: str, order: str, dialect: Dialect):
	"""
	Devuelve (sql, params) para un SELECT.

	`fields` y `order` se interpolan en crudo: son SQL, no datos. Nunca deben
	construirse con entrada de usuario sin validar.
	"""
	where, params = condition_params(condition, dialect)

	sql = f"SELECT {fields} FROM {dialect.table(table)}"
	if where:
		sql += f" WHERE {where}"
	if order:
		sql += f" {order}"

	return sql, params


# ---------------------------------------------------------------------------
# Construcción por interpolación (heredada)
#
# Se conserva para los constructores de string que son API pública. El
# escapado con replace("'", "''") es evadible en MySQL con un backslash:
# preferí siempre las funciones `*_params` de arriba.
# ---------------------------------------------------------------------------

def escape_value(value) -> str:
	"""Escapado por interpolación. NO es seguro: ver la nota de arriba."""
	return str(value).replace("'", "''")


def process_condition(condition, dialect: Dialect) -> str:
	"""
	Versión heredada de `condition_params` que devuelve sólo el string.

	Mantiene el comportamiento histórico, incluido el fallback
	`str(condition)` para tipos no contemplados.
	"""
	if condition is None or condition == "":
		return ""

	if isinstance(condition, str):
		return condition

	if hasattr(condition, 'items'):
		if not condition:
			return ""

		conditions = []
		for key, value in condition.items():
			if value is None:
				conditions.append(f"{dialect.ident(key)} IS NULL")
			else:
				conditions.append(f"{dialect.ident(key)} = '{escape_value(value)}'")
		return " AND ".join(conditions)

	return str(condition)
