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
easymysql — capa fina sobre PyMySQL y psycopg2.

	from easymysql.mysql import mysql
	from easymysql.postgres import postgresql

	db = mysql('localhost', 'usuario', 'clave', 'basededatos')

El backend PostgreSQL requiere el extra correspondiente:

	pip install easymysql[postgres]

**Las clases de conexión se importan desde su submódulo, no desde el
paquete.** `from easymysql import mysql` devolvería el *módulo*
`easymysql.mysql`, no la clase: el submódulo tiene el mismo nombre que la
clase y el sistema de importación le da precedencia sobre `__getattr__`. Como
el error que produce (`'module' object is not callable`) es confuso, no se
ofrece esa forma para ninguno de los dos backends.
"""

# Fuente única de verdad de la versión: `pyproject.toml` la lee de acá y los
# métodos `version()` de ambos backends la devuelven. Antes había tres valores
# distintos en tres lugares (mysql 0.2.0.0, postgres 0.1.0, setup.py 0.2.0.0).
__version__ = "0.2.0.0rc1"

__all__ = ["InputRules", "check", "filter", "__version__"]


def __getattr__(name):
	"""
	Importación perezosa de `rules`, para que `import easymysql` no arrastre
	los drivers de base de datos.

	Las clases de conexión **no** se exponen acá a propósito: ver el docstring
	del módulo.
	"""
	if name in ("InputRules", "check", "filter", "jsontools"):
		from . import rules
		return getattr(rules, name)
	if name in ("mysql", "postgresql"):
		raise AttributeError(
			f"importá la clase desde su submódulo: "
			f"`from easymysql.{'mysql' if name == 'mysql' else 'postgres'} "
			f"import {name}`"
		)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
