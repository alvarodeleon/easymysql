"""Operaciones comunes compartidas por ambos conectores."""
from typing import Any, Iterable, Optional, Union, Sequence
from . import _sql
from ._transaction import data_operation
from ._types import WriteResult, ConditionInput, Row


class Convenience:
	@data_operation
	def select_one(self, table: str, condition: ConditionInput = "", fields="*", **clauses) -> Optional[Row]:
		"""Una fila o None; límite aplicado en el servidor."""
		if clauses.get("order") or ("limit" in clauses and clauses["limit"] != 1):
			raise ValueError("select_one usa limit=1; usá order_by para ordenar")
		clauses["limit"] = 1
		rows = self.select(table, condition, fields=fields, **clauses)
		return rows[0] if rows else None

	@data_operation
	def row_exists(self, table: str, condition: ConditionInput = "") -> bool:
		return self.select_one(table, condition, fields="1 AS _easymysql_exists") is not None

	@data_operation
	def upsert(self, table: str, data: Row, *, conflict_columns=None, update_columns=None, returning: Optional[str]=None) -> WriteResult:
		self._ensure_clean()
		sql, params = _sql.upsert_params(table, data, self._dialect,
		                               conflict_columns=conflict_columns,
		                               update_columns=update_columns, returning=returning)
		self._execute(sql, params)
		last_id = self.getLastId()
		if returning is not None:
			rows = self._fetch_rows()
			last_id = rows[0][returning] if rows else None
		result = WriteResult(self.count(), last_id)
		if not self.is_in_transaction():
			self.commit()
		self._set_metadata(result.affected_rows, result.last_id)
		return result

	@data_operation
	def insert_many(self, table: str, rows: Iterable[Row], *, batch_size: int=1000) -> WriteResult:
		return self._write_many(table, rows, batch_size=batch_size)

	@data_operation
	def upsert_many(self, table: str, rows: Iterable[Row], *, conflict_columns=None, update_columns=None, batch_size: int=1000) -> WriteResult:
		return self._write_many(table, rows, upsert=True, batch_size=batch_size,
		                        conflict_columns=conflict_columns, update_columns=update_columns)

	def _write_many(self, table, rows, *, batch_size, **options):
		self._ensure_cursor()
		self._ensure_clean()
		if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
			raise ValueError("batch_size debe ser un entero positivo")
		if isinstance(rows, (str, bytes, dict)):
			raise TypeError("rows debe ser un iterable de diccionarios")
		rows = list(rows)
		if not rows:
			return WriteResult(0)
		if any(not isinstance(row, dict) or not row for row in rows):
			raise ValueError("cada fila debe ser un diccionario no vacío")
		if any(set(row) != set(rows[0]) for row in rows):
			raise ValueError("todas las filas deben tener las mismas columnas")
		# Validar/adaptar todo antes de enviar la primera sentencia.
		statements = [_sql.insert_many_params(table, rows[i:i+batch_size], self._dialect, **options)
		              for i in range(0, len(rows), batch_size)]
		count = 0
		with self.transaction():
			for sql, params in statements:
				self._execute(sql, params)
				count += self.count()
		self._set_metadata(count, None)
		return WriteResult(count)

	def affected_rows(self) -> int:
		return self.count()

	def get_last_id(self) -> Any:
		return self.getLastId()

	def reset_session(self):
		return self.resetSession()
