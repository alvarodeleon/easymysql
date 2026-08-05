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
import functools
import warnings
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


def condition_params(condition: Union[str, Dict[str, Any], None]):
	"""Convierte una condición en (fragmento_sql, params)."""
	return _sql.condition_params(condition, DIALECT)


def insert_params(table: str, data: dict, returning: str = "id"):
	"""
	Devuelve (sql, params) para un INSERT.

	`returning` es el nombre de la columna a devolver, o None para omitir la
	cláusula RETURNING en tablas que no tienen columna `id`.
	"""
	return _sql.insert_params(table, data, DIALECT, returning=returning)


def update_params(table: str, data: dict, condition: Union[str, Dict[str, Any]]):
	"""Devuelve (sql, params) para un UPDATE."""
	return _sql.update_params(table, data, condition, DIALECT)


def delete_params(table: str, condition: Union[str, Dict[str, Any]]):
	"""Devuelve (sql, params) para un DELETE."""
	return _sql.delete_params(table, condition, DIALECT)


def select_params(table: str, condition: Union[str, Dict[str, Any]]="", fields="*", order=""):
	"""Devuelve (sql, params) para un SELECT."""
	return _sql.select_params(table, condition, fields, order, DIALECT)


def _process_condition(condition):
	"""
	Versión heredada que devuelve sólo el string, con el valor interpolado.

	Preferí `condition_params()`.
	"""
	return _sql.process_condition(condition, DIALECT)

def select(table, condition: Union[str, Dict[str, Any]]="", fields="*", order="") -> str:
	# Procesar condición usando el helper
	processed_condition = _process_condition(condition)

	if len(processed_condition) > 0:
		query = "SELECT " + fields + " FROM " + table + " WHERE " + processed_condition
	else:
		query = "SELECT " + fields + " FROM " + table

	if len(order)>0:
		query = query + " " + order

	return query

def insert(table: str, data: dict) -> str:
	fields = []
	values = []
		
	for key, value in data.items():
		fields.append(f'"{key}"')
		if value is None:
			values.append("NULL")
		else:
			# Escapar comillas simples para prevenir SQL injection
			escaped_value = str(value).replace("'", "''")
			values.append(f"'{escaped_value}'")
		
	fields_str = ", ".join(fields)
	values_str = ", ".join(values)
		
	# Usar RETURNING id para obtener el ID insertado
	query = f'INSERT INTO "{table}" ({fields_str}) VALUES ({values_str}) RETURNING id'

	return query

def update(table: str, data: dict, condition: Union[str, Dict[str, Any]]) -> str:
	"""
	Actualiza registros en la tabla.
		
	Args:
		table (str): Nombre de la tabla
		data (dict): Datos a actualizar
		condition (Union[str, Dict[str, Any]]): Condición WHERE
	"""
	if not isinstance(data, dict):
		raise ValueError("data debe ser un diccionario")
		
	# Construir SET clause
	set_clauses = []
	for key, value in data.items():
		if value is None:
			set_clauses.append(f'"{key}" = NULL')
		else:
			escaped_value = str(value).replace("'", "''")
			set_clauses.append(f'"{key}" = \'{escaped_value}\'')
		
	values_str = ", ".join(set_clauses)
		
	# Procesar condición
	where_clause = _process_condition(condition)
		
	query = f'UPDATE "{table}" SET {values_str} WHERE {where_clause}'

	return query

def delete(table,condition):
    return f"DELETE FROM {table} WHERE {condition}"

def ilike(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} ILIKE '%{escaped_value}%'"

def like(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} LIKE '%{escaped_value}%'"

def not_like(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} NOT LIKE '%{escaped_value}%'"

def concat_or(*args):
	sentences = ""
	for arg in args:
		sentences += f"{arg} OR "

	return f"({sentences[:-4]})"

def concat_and(*args):
	sentences = ""
	for arg in args:
		sentences += f"{arg} AND "
	return f"({sentences[:-5]})"

# Operadores de comparación
def equals(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} = '{escaped_value}'"

def not_equals(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} != '{escaped_value}'"

def greater_than(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} > '{escaped_value}'"

def greater_than_or_equal(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} >= '{escaped_value}'"

def less_than(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} < '{escaped_value}'"

def less_than_or_equal(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} <= '{escaped_value}'"

# Operadores de rango
def between(field, value1, value2):
    escaped_value1 = str(value1).replace("'", "''")
    escaped_value2 = str(value2).replace("'", "''")
    return f"{field} BETWEEN '{escaped_value1}' AND '{escaped_value2}'"

def not_between(field, value1, value2):
    escaped_value1 = str(value1).replace("'", "''")
    escaped_value2 = str(value2).replace("'", "''")
    return f"{field} NOT BETWEEN '{escaped_value1}' AND '{escaped_value2}'"

# Operadores de existencia
def exists(subquery):
    """
    EXISTS sobre una subconsulta.

    ⚠️ Recibe **SQL crudo** y lo interpola tal cual. El nombre del parámetro
    era `field`, lo que inducía a `exists('activo')` → `EXISTS (activo)`,
    error de sintaxis. Nunca lo construyas con entrada de usuario.
    """
    return f"EXISTS ({subquery})"


def in_list(field, values):
    escaped_values = [str(v).replace("'", "''") for v in values]
    values_str = "', '".join(escaped_values)
    return f"{field} IN ('{values_str}')"

def not_in_list(field, values):
    escaped_values = [str(v).replace("'", "''") for v in values]
    values_str = "', '".join(escaped_values)
    return f"{field} NOT IN ('{values_str}')"



#Operadores de Nulidad
def is_null(field):
    return f"{field} IS NULL"

def is_not_null(field):
    return f"{field} IS NOT NULL"


# Funciones de Texto Adicionales
def starts_with(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} LIKE '{escaped_value}%'"

def ends_with(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} LIKE '%{escaped_value}'"

def contains(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} LIKE '%{escaped_value}%'"

def not_contains(field, value):
    escaped_value = str(value).replace("'", "''")
    return f"{field} NOT LIKE '%{escaped_value}%'"

# Funciones de Fecha
def date_equals(field, date):
    escaped_date = str(date).replace("'", "''")
    return f"DATE({field}) = '{escaped_date}'"

def date_greater_than(field, date):
    escaped_date = str(date).replace("'", "''")
    return f"DATE({field}) > '{escaped_date}'"

def date_less_than(field, date):
    escaped_date = str(date).replace("'", "''")
    return f"DATE({field}) < '{escaped_date}'"

def date_between(field, start_date, end_date):
    escaped_start = str(start_date).replace("'", "''")
    escaped_end = str(end_date).replace("'", "''")
    return f"DATE({field}) BETWEEN '{escaped_start}' AND '{escaped_end}'"

# Funciones de Ordenamiento
def order_by(field, direction="ASC"):
    return f"ORDER BY {field} {direction}"

def order_by_desc(field):
    return f"ORDER BY {field} DESC"

def limit_query(limit, offset=None):
    if offset is not None:
        return f"LIMIT {limit} OFFSET {offset}"
    return f"LIMIT {limit}"

def group_by(field):
    return f"GROUP BY {field}"

def having(condition):
    """
    ⚠️ Recibe **SQL crudo** y lo interpola tal cual. Nunca lo construyas con
    entrada de usuario sin validar.
    """
    return f"HAVING {condition}"

# Funciones de Negación
def not_condition(condition):
    """
    ⚠️ Recibe **SQL crudo** y lo interpola tal cual. La versión parametrizada
    es `where.not_(condicion)` o el operador `~`.
    """
    return f"NOT ({condition})"


# ---------------------------------------------------------------------------
# Constructores parametrizados (recomendados)
#
# Los operadores de arriba interpolan el valor dentro del string SQL. `where`
# devuelve objetos Condition, que llevan el SQL y los parámetros separados:
#
#     from easymysql.pg_query import where
#     db.select("productos", where.equals("activo", True) & where.greater_than("stock", 0))
#
# Además corrigen bugs de resultado que los operadores viejos no pueden
# arreglar sin cambiar su firma: lista vacía en in_list/not_in_list, comodines
# de LIKE sin escapar, y precedencia al mezclar AND con OR.
# ---------------------------------------------------------------------------

where = _conditions.ConditionBuilder(DIALECT)
Condition = _conditions.Condition


def safe_order_by(field, direction="ASC"):
	"""ORDER BY con la dirección validada contra ASC/DESC."""
	return _conditions.order_by(field, direction, DIALECT)


def safe_limit(limit, offset=None):
	"""LIMIT con los valores convertidos a entero."""
	return _conditions.limit_query(limit, offset, DIALECT)


# ---------------------------------------------------------------------------
# Deprecación de los operadores por interpolación
# ---------------------------------------------------------------------------

_REEMPLAZOS = {'like': 'where.like', 'not_like': 'where.not_like', 'ilike': 'where.ilike', 'equals': 'where.equals', 'not_equals': 'where.not_equals', 'greater_than': 'where.greater_than', 'greater_than_or_equal': 'where.greater_than_or_equal', 'less_than': 'where.less_than', 'less_than_or_equal': 'where.less_than_or_equal', 'between': 'where.between', 'not_between': 'where.not_between', 'in_list': 'where.in_list', 'not_in_list': 'where.not_in_list', 'starts_with': 'where.starts_with', 'ends_with': 'where.ends_with', 'contains': 'where.contains', 'not_contains': 'where.not_contains', 'date_equals': 'where.date_equals', 'date_greater_than': 'where.date_greater_than', 'date_less_than': 'where.date_less_than', 'date_between': 'where.date_between', 'concat_and': 'where.all_', 'concat_or': 'where.any_', 'order_by': 'safe_order_by', 'order_by_desc': "safe_order_by(campo, 'DESC')", 'limit_query': 'safe_limit'}


def _deprecar(fn, nombre, reemplazo):
	@functools.wraps(fn)
	def envoltorio(*args, **kwargs):
		warnings.warn(
			"pg_query.%s() interpola el valor dentro del SQL en vez de "
			"parametrizarlo. Usá %s(), que devuelve un Condition." % (nombre, reemplazo),
			DeprecationWarning,
			stacklevel=2,
		)
		return fn(*args, **kwargs)
	return envoltorio


for _nombre, _reemplazo in _REEMPLAZOS.items():
	if _nombre in globals():
		globals()[_nombre] = _deprecar(globals()[_nombre], _nombre, _reemplazo)

del _nombre, _reemplazo
