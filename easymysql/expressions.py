"""Expresiones acotadas para valores de insert/update."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from ._conditions import adapt


@dataclass(frozen=True)
class Expression:
	kind: str
	column: Optional[str] = None
	value: Any = None


def increment(column: str, amount=1) -> Expression:
	if isinstance(amount, bool) or not isinstance(amount, (int, float, Decimal)):
		raise TypeError("amount debe ser numérico")
	adapt(amount)
	if isinstance(amount, Decimal) and not amount.is_finite():
		raise ValueError("amount debe ser finito")
	return Expression("increment", column, amount)


def current_timestamp() -> Expression:
	return Expression("current_timestamp")
