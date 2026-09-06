"""Compatibilidad de interpolación heredada; no usar para consultas ejecutables."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from ._sql import Dialect

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
