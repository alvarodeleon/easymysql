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
from ._types import ConditionInput
from .expressions import Expression

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

def condition_params(condition: ConditionInput, dialect: Dialect):
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
	values = [_value(v, dialect) for v in data.values()]
	marks = ", ".join(sql for sql, _ in values)
	sql = f"INSERT INTO {dialect.table(table)} ({cols}) VALUES ({marks})"

	if returning and dialect.supports_returning:
		sql += f" RETURNING {dialect.ident(returning)}"

	return sql, tuple(p for _, params in values for p in params)


def update_params(table: str, data: dict, condition, dialect: Dialect):
	"""Devuelve (sql, params) para un UPDATE."""
	if not isinstance(data, dict):
		raise TypeError(f"data debe ser un diccionario, no {type(data).__name__}")
	if not data:
		raise ValueError("data no puede estar vacío")

	values = [(k, _value(v, dialect, update=True)) for k, v in data.items()]
	sets = ", ".join(f"{dialect.ident(k)} = {value[0]}" for k, value in values)
	params = [p for _, value in values for p in value[1]]

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


def select_params(table: str, condition, fields, order: str, dialect: Dialect, **clauses):
	"""
	Devuelve (sql, params) para un SELECT.

	`fields` y `order` se interpolan en crudo: son SQL, no datos. Nunca deben
	construirse con entrada de usuario sin validar.
	"""
	where, params = condition_params(condition, dialect)

	if not isinstance(fields, str):
		fields = ", ".join(dialect.ident(field) for field in _columns(fields, "fields"))
	sql = f"SELECT {fields} FROM {dialect.table(table)}"
	if where:
		sql += f" WHERE {where}"
	tail, tail_params = _select_clauses(dialect, order, **clauses)
	return sql + tail, params + tail_params


# ---------------------------------------------------------------------------
# Construcción por interpolación (heredada)
#
# Se conserva para los constructores de string que son API pública. El
# escapado con replace("'", "''") es evadible en MySQL con un backslash:
# preferí siempre las funciones `*_params` de arriba.
# ---------------------------------------------------------------------------

from ._legacy_sql import escape_value, process_condition  # compatibilidad privada


def _value(value, dialect, *, update=False):
	if not isinstance(value, Expression):
		return PLACEHOLDER, (adapt(value),)
	if value.kind == "current_timestamp":
		return "CURRENT_TIMESTAMP", ()
	if value.kind == "increment" and update:
		from .expressions import increment
		increment(value.column, value.value)  # valida también objetos construidos a mano
		return f"{dialect.ident(value.column)} + %s", (adapt(value.value),)
	raise ValueError("expresión no admitida en esta posición")


def _columns(columns, name):
	if isinstance(columns, str):
		columns = [columns]
	else:
		columns = list(columns)
	if not columns or any(not isinstance(c, str) for c in columns):
		raise ValueError(f"{name} requiere nombres de columnas")
	if len(set(columns)) != len(columns):
		raise ValueError(f"{name} contiene columnas repetidas")
	return columns


def _nonnegative(value, name):
	if isinstance(value, bool) or not isinstance(value, int) or value < 0:
		raise ValueError(f"{name} debe ser un entero no negativo")
	return value


def _select_clauses(dialect, order="", *, order_by=None, limit=None, offset=None,
                    group_by=None, having=None, for_update=False):
	structured = (order_by is not None or limit is not None or offset is not None
	              or group_by is not None or having is not None or for_update)
	if order and structured:
		raise ValueError("no mezcles order raw con cláusulas estructuradas")
	if not isinstance(for_update, bool):
		raise TypeError("for_update debe ser bool")
	if order:
		return " " + order, ()
	parts, params = [], ()
	if group_by is not None:
		parts.append("GROUP BY " + ", ".join(dialect.ident(c) for c in _columns(group_by, "group_by")))
	if having is not None:
		if not isinstance(having, Condition):
			raise TypeError("having requiere Condition; usá raw(sql, params) para SQL explícito")
		parts.append("HAVING " + having.sql)
		params += having.params
	if order_by is not None:
		entries = [order_by] if isinstance(order_by, str) else list(order_by)
		if not entries:
			raise ValueError("order_by no puede estar vacío")
		orders = []
		for entry in entries:
			field, direction = (entry, "ASC") if isinstance(entry, str) else entry
			if not isinstance(direction, str) or direction.upper() not in ("ASC", "DESC"):
				raise ValueError("direction debe ser ASC o DESC")
			orders.append(f"{dialect.ident(field)} {direction.upper()}")
		parts.append("ORDER BY " + ", ".join(orders))
	if limit is not None:
		parts.append(f"LIMIT {_nonnegative(limit, 'limit')}")
	if offset is not None:
		if limit is None:
			raise ValueError("offset requiere limit")
		parts.append(f"OFFSET {_nonnegative(offset, 'offset')}")
	if for_update:
		parts.append("FOR UPDATE")
	return (" " + " ".join(parts) if parts else ""), params


def insert_many_params(table, rows, dialect, *, conflict_columns=None,
                       update_columns=None, upsert=False, returning=None):
	"""Construye una sola sentencia para un lote ya materializado."""
	rows = list(rows)
	if not rows:
		raise ValueError("rows no puede estar vacío")
	if any(not isinstance(row, dict) or not row for row in rows):
		raise ValueError("cada fila debe ser un diccionario no vacío")
	columns = list(rows[0])
	if any(set(row) != set(columns) for row in rows):
		raise ValueError("todas las filas deben tener las mismas columnas")
	values = [[_value(row[c], dialect) for c in columns] for row in rows]
	marks = ", ".join("(" + ", ".join(sql for sql, _ in row) + ")" for row in values)
	params = tuple(p for row in values for _, arguments in row for p in arguments)
	sql = f"INSERT INTO {dialect.table(table)} ({', '.join(dialect.ident(c) for c in columns)}) VALUES {marks}"
	if upsert:
		if dialect.name == "postgres":
			if conflict_columns is None:
				raise ValueError("PostgreSQL requiere conflict_columns")
			conflicts = _columns(conflict_columns, "conflict_columns")
			if not set(conflicts) <= set(columns):
				raise ValueError("conflict_columns debe estar presente en data")
		else:
			if conflict_columns is not None:
				raise ValueError("MySQL resuelve conflictos con cualquier clave única; omití conflict_columns")
			conflicts = []
		updates = ([c for c in columns if c not in conflicts] if update_columns is None
		           else _columns(update_columns, "update_columns"))
		if not updates or not set(updates) <= set(columns):
			raise ValueError("update_columns requiere columnas presentes y actualizables")
		if set(updates) & set(conflicts):
			raise ValueError("no se actualizan las columnas de conflicto")
		if dialect.name == "postgres":
			sql += " ON CONFLICT (" + ", ".join(dialect.ident(c) for c in conflicts) + ") DO UPDATE SET "
			sql += ", ".join(f"{dialect.ident(c)} = EXCLUDED.{dialect.ident(c)}" for c in updates)
		elif len(rows) == 1:
			# Valores parametrizados: compatible sin VALUES() deprecado ni alias nuevo.
			assignments = [(c, _value(rows[0][c], dialect)) for c in updates]
			sql += " ON DUPLICATE KEY UPDATE " + ", ".join(f"{dialect.ident(c)} = {v[0]}" for c, v in assignments)
			params += tuple(p for _, value in assignments for p in value[1])
		else:
			alias = "_easymysql_new"
			while alias == table.split(".")[-1]:
				alias += "_"
			sql += f" AS {dialect.ident(alias)} ON DUPLICATE KEY UPDATE "
			sql += ", ".join(f"{dialect.ident(c)} = {dialect.ident(alias)}.{dialect.ident(c)}" for c in updates)
	if returning is not None:
		if not dialect.supports_returning:
			raise ValueError("returning solo está disponible en PostgreSQL")
		sql += " RETURNING " + dialect.ident(returning)
	return sql, params


def upsert_params(table, data, dialect, *, conflict_columns=None, update_columns=None, returning=None):
	return insert_many_params(table, [data], dialect, upsert=True,
	                         conflict_columns=conflict_columns,
	                         update_columns=update_columns, returning=returning)
