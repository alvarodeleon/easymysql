
from typing import Iterable, Union, Dict, Any

def _process_condition(condition):
	"""
	Procesa la condición convirtiendo diccionarios a string SQL WHERE.
	Adaptado para PostgreSQL (usa comillas dobles para nombres de columnas).
	
	Args:
		condition: Puede ser string, diccionario, None o cualquier otro tipo
	
	Returns:
		str: Condición SQL formateada
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
				conditions.append(f'"{key}" IS NULL')
			else:
				# Escapar comillas simples para prevenir SQL injection
				escaped_value = str(value).replace("'", "''")
				conditions.append(f'"{key}" = \'{escaped_value}\'')
		return " AND ".join(conditions)
	
	# Si es otro tipo iterable (como OrderedDict, etc.)
	if hasattr(condition, 'items'):
		conditions = []
		for key, value in condition.items():
			if value is None:
				conditions.append(f'"{key}" IS NULL')
			else:
				escaped_value = str(value).replace("'", "''")
				conditions.append(f'"{key}" = \'{escaped_value}\'')
		return " AND ".join(conditions)
	
	# Para cualquier otro tipo, convertirlo a string
	return str(condition)

def select(self,table,condition: Union[str, Dict[str, Any]]="",fields="*",order="") -> str:
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
    return f"{field} ILIKE '%{value}%'"

def like(field, value):
    return f"{field} LIKE '%{value}%'"

def not_like(field, value):
    return f"{field} NOT LIKE '%{value}%'"

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
    return f"{field} = '{value}'"

def not_equals(field, value):
    return f"{field} != '{value}'"

def greater_than(field, value):
    return f"{field} > '{value}'"

def greater_than_or_equal(field, value):
    return f"{field} >= '{value}'"

def less_than(field, value):
    return f"{field} < '{value}'"

def less_than_or_equal(field, value):
    return f"{field} <= '{value}'"

# Operadores de rango
def between(field, value1, value2):
    return f"{field} BETWEEN '{value1}' AND '{value2}'"

def not_between(field, value1, value2):
    return f"{field} NOT BETWEEN '{value1}' AND '{value2}'"

# Operadores de existencia
def exists(field):
    return f"EXISTS ({field})"


def in_list(field, values):
    values_str = "', '".join(str(v) for v in values)
    return f"{field} IN ('{values_str}')"

def not_in_list(field, values):
    values_str = "', '".join(str(v) for v in values)
    return f"{field} NOT IN ('{values_str}')"



#Operadores de Nulidad
def is_null(field):
    return f"{field} IS NULL"

def is_not_null(field):
    return f"{field} IS NOT NULL"


# Funciones de Texto Adicionales
def starts_with(field, value):
    return f"{field} LIKE '{value}%'"

def ends_with(field, value):
    return f"{field} LIKE '%{value}'"

def contains(field, value):
    return f"{field} LIKE '%{value}%'"

def not_contains(field, value):
    return f"{field} NOT LIKE '%{value}%'"

# Funciones de Fecha
def date_equals(field, date):
    return f"DATE({field}) = '{date}'"

def date_greater_than(field, date):
    return f"DATE({field}) > '{date}'"

def date_less_than(field, date):
    return f"DATE({field}) < '{date}'"

def date_between(field, start_date, end_date):
    return f"DATE({field}) BETWEEN '{start_date}' AND '{end_date}'"

# Funciones de Ordenamiento
def order_by(field, direction="ASC"):
    return f"ORDER BY {field} {direction}"

def order_by_desc(field):
    return f"ORDER BY {field} DESC"

def limit_query(limit, offset=0):
    if offset > 0:
        return f"LIMIT {offset}, {limit}"
    return f"LIMIT {limit}"

def group_by(field):
    return f"GROUP BY {field}"

def having(condition):
    return f"HAVING {condition}"

# Funciones de Negación
def not_condition(condition):
    return f"NOT ({condition})"