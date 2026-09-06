"""Tipos compartidos y resultados independientes del cursor de la conexión."""
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Union

from ._conditions import Condition

Row = Dict[str, Any]
ConditionInput = Union[str, Mapping[str, Any], Condition, None]
Params = Optional[Union[Sequence[Any], Mapping[str, Any]]]


@dataclass(frozen=True)
class WriteResult:
	"""Resultado de ejecución; puede estar sujeto al rollback de un contexto exterior."""
	affected_rows: int
	last_id: Any = None
