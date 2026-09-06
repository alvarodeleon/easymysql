"""Estado transaccional compartido; se accede bajo el lock del conector."""

from functools import wraps
from threading import current_thread


def serialized(method):
	"""Comprueba el propietario antes de validar argumentos o tocar recursos."""
	@wraps(method)
	def call(self, *args, **kwargs):
		with self._lock:
			self._tx.check_owner()
			return method(self, *args, **kwargs)
	return call


def data_operation(method):
	"""Metadatos de la operación pública, incluidos validación y fetch."""
	@serialized
	@wraps(method)
	def call(self, *args, **kwargs):
		self._clear_metadata()
		try:
			return method(self, *args, **kwargs)
		except BaseException:
			self._clear_metadata()
			raise
	return call


class TransactionState:
	def __init__(self):
		self.owner = None
		self.levels = []
		self.failed = False

	@property
	def depth(self):
		return len(self.levels)

	def check_owner(self):
		# Los identificadores numéricos de hilos pueden reutilizarse.
		if self.owner is not None and self.owner is not current_thread():
			raise RuntimeError("la transacción pertenece a otro hilo")

	def check_usable(self):
		self.check_owner()
		if self.failed:
			raise RuntimeError(
				"estado transaccional incierto: llamá a rollback() o close() "
				"antes de continuar; un commit fallido pudo haberse aplicado"
			)

	def opened(self):
		self.owner = current_thread()
		self.levels.append(object())

	def ended(self):
		self.levels.pop()
		if not self.levels:
			self.owner = None

	def fail(self):
		self.owner = current_thread()
		self.failed = True

	def clear(self):
		self.levels.clear()
		self.owner = None
		self.failed = False


class TransactionContext:
	"""Un contexto termina exactamente el nivel que abrió."""
	def __init__(self, db_connection):
		self.db = db_connection
		self._level = None

	def __enter__(self):
		with self.db._lock:
			self.db._tx.check_usable()
			if self._level is not None:
				raise RuntimeError("este contexto de transacción ya está activo")
			if not self.db.begin():
				raise RuntimeError("no hay una conexión activa para iniciar la transacción")
			self._level = self.db._tx.levels[-1]
			return self.db

	def _check_level(self):
		self.db._tx.check_owner()
		levels = self.db._tx.levels
		if not levels or levels[-1] is not self._level:
			raise RuntimeError(
				"el nivel del contexto cambió: no mezcles commit/rollback/close "
				"manuales con un contexto de transacción activo"
			)

	def __exit__(self, exc_type, exc_val, exc_tb):
		with self.db._lock:
			# Un hilo ajeno tampoco puede consumir el contexto del propietario.
			self.db._tx.check_owner()
			try:
				if exc_type is None:
					self._check_level()
					self.db.commit()
				else:
					try:
						self._check_level()
						self.db.rollback()
					except BaseException as cleanup_error:
						# La excepción del bloque sigue siendo la principal.
						raise exc_val.with_traceback(exc_tb) from cleanup_error
			finally:
				self._level = None
		return False
