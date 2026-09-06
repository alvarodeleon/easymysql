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
from ._types import ConditionInput, Params, Row
from typing import Iterable, Union, Dict, Any

from . import _sql
from . import _conditions

# ---------------------------------------------------------------------------
# El motor vive en _sql.py, compartido con my_query: la única diferencia entre
# los dos módulos es el dialecto.
#
# Las funciones `*_params` devuelven (sql, params) para que los valores viajen
# por el driver. PostgreSQL con standard_conforming_strings=on no es vulnerable
# al bypass por backslash que sí afecta a MySQL, pero el escapado manual sigue
# sin cubrir los identificadores ni la conversión de tipos (bool, bytes,
# datetime, Decimal, json), que psycopg2 hace correctamente.
# ---------------------------------------------------------------------------

DIALECT = _sql.POSTGRES
PLACEHOLDER = _sql.PLACEHOLDER


def _ident(name) -> str:
	"""Delimita un identificador (columna) con comillas dobles."""
	return DIALECT.ident(name)


def _table(name) -> str:
	"""Delimita un nombre de tabla, admitiendo la forma `esquema.tabla`."""
	return DIALECT.table(name)


def condition_params(condition: ConditionInput):
	"""Convierte una condición en (fragmento_sql, params)."""
	return _sql.condition_params(condition, DIALECT)


def insert_params(table: str, data: dict, returning: Union[str, None] = "id"):
	"""
	Devuelve (sql, params) para un INSERT.

	`returning` es el nombre de la columna a devolver, o None para omitir la
	cláusula RETURNING en tablas que no tienen columna `id`.
	"""
	return _sql.insert_params(table, data, DIALECT, returning=returning)


def update_params(table: str, data: dict, condition: ConditionInput):
	"""Devuelve (sql, params) para un UPDATE."""
	return _sql.update_params(table, data, condition, DIALECT)


def delete_params(table: str, condition: ConditionInput):
	"""Devuelve (sql, params) para un DELETE."""
	return _sql.delete_params(table, condition, DIALECT)


def select_params(table: str, condition: ConditionInput="", fields="*", order="", **clauses):
	"""Devuelve (sql, params) para un SELECT."""
	return _sql.select_params(table, condition, fields, order, DIALECT, **clauses)


def _process_condition(condition):
	"""
	Versión heredada que devuelve sólo el string, con el valor interpolado.

	Preferí `condition_params()`.
	"""
	return _sql.process_condition(condition, DIALECT)

# ---------------------------------------------------------------------------
# Constructores de condiciones
#
# Devuelven un `Condition`, que lleva el SQL y sus parámetros por separado
# hasta el driver. Se componen con `&` (AND), `|` (OR) y `~` (NOT), o con
# `all_()` / `any_()` / `not_()` para listas.
#
#     from easymysql.pg_query import equals, greater_than
#     db.select("productos", equals("activo", True) & greater_than("stock", 0))
#
# El builder está ligado al dialecto del módulo: es lo único que distingue a
# `my_query` de `pg_query`.

# `ilike` e `icontains` sólo existen acá: en MySQL las collations _ci ya
# comparan sin distinguir mayúsculas.
# ---------------------------------------------------------------------------

_builder = _conditions.ConditionBuilder(DIALECT)

Condition = _conditions.Condition

equals                = _builder.equals
not_equals            = _builder.not_equals
greater_than          = _builder.greater_than
greater_than_or_equal = _builder.greater_than_or_equal
less_than             = _builder.less_than
less_than_or_equal    = _builder.less_than_or_equal
between               = _builder.between
not_between           = _builder.not_between
in_list               = _builder.in_list
not_in_list           = _builder.not_in_list
is_null               = _builder.is_null
is_not_null           = _builder.is_not_null
contains              = _builder.contains
not_contains          = _builder.not_contains
starts_with           = _builder.starts_with
ends_with             = _builder.ends_with
like                  = _builder.like
not_like              = _builder.not_like
all_                  = _builder.all_
any_                  = _builder.any_
not_                  = _builder.not_
raw                   = _builder.raw
ilike                 = _builder.ilike
icontains             = _builder.icontains
date_equals           = _builder.date_equals
date_greater_than     = _builder.date_greater_than
date_less_than        = _builder.date_less_than
date_between          = _builder.date_between


# ---------------------------------------------------------------------------
# Cláusulas
#
# No son condiciones: devuelven un fragmento de SQL sin parámetros, y por eso
# validan en vez de escapar.
# ---------------------------------------------------------------------------

def order_by(field, direction="ASC") -> str:
	"""ORDER BY con la dirección validada contra ASC/DESC."""
	return _conditions.order_by(field, direction, DIALECT)


def group_by(field) -> str:
	"""GROUP BY con el identificador delimitado."""
	return _conditions.group_by(field, DIALECT)


def limit(count, offset=None) -> str:
	"""LIMIT con los valores convertidos a entero."""
	return _conditions.limit_query(count, offset, DIALECT)


def having(sql: str) -> str:
	"""
	HAVING a partir de SQL crudo.

	Es la contraparte de `raw()` para cláusulas: `select()` no transporta
	parámetros fuera del WHERE, así que acá no hay dónde ponerlos. Nunca lo
	construyas con entrada de usuario sin validar.
	"""
	return f"HAVING {sql}"


def exists(subquery: str, params=()) -> "_conditions.Condition":
	"""EXISTS sobre una subconsulta, con los valores en `params`."""
	return _conditions.exists(subquery, params)


__all__ = [
	"Condition",
	# condiciones
	"equals",
	"not_equals",
	"greater_than",
	"greater_than_or_equal",
	"less_than",
	"less_than_or_equal",
	"between",
	"not_between",
	"in_list",
	"not_in_list",
	"is_null",
	"is_not_null",
	"contains",
	"not_contains",
	"starts_with",
	"ends_with",
	"like",
	"not_like",
	"all_",
	"any_",
	"not_",
	"raw",
	"ilike",
	"icontains",
	"date_equals",
	"date_greater_than",
	"date_less_than",
	"date_between",
	# cláusulas
	"order_by", "group_by", "limit", "having", "exists",
	# constructores (sql, params)
	"condition_params", "insert_params", "update_params",
	"delete_params", "select_params",
]


def upsert_params(table, data, **options):
	return _sql.upsert_params(table, data, DIALECT, **options)


def insert_many_params(table, rows, **options):
	return _sql.insert_many_params(table, rows, DIALECT, **options)

__all__ += ["upsert_params", "insert_many_params"]
