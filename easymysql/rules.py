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
import copy
import hashlib
import ipaddress
import html
import json
import base64
import pickle
import re
import urllib
import urllib.parse
import warnings

def generate_structure(path,rules, structure=None):
	levels = path.split('.')

	if structure is None:
		structure = {}

	temp = structure

	for i, level in enumerate(levels):
		if i == len(levels) - 1:
			temp[level] = rules
		else:
			if level not in temp:
				temp[level] = {}
			temp = temp[level]

	return structure

def map_options(path,options, structure=None):

	levels = path.split('.')

	if structure is None:
		structure = {}

	temp = structure

	for i, level in enumerate(levels):
		if i == len(levels) - 1:
			temp[level] = options
		else:
			if level not in temp:
				temp[level] = {}
			temp = temp[level]

	return structure


def validate_schema(variable, schema,messages=None,options=None):

	if messages is None:
		messages = []

	if isinstance(schema, str):
		schema = json.loads(schema)

	for item in schema:
		if isinstance(schema[item],str):
	
			if item in variable:
				if not check.rules(variable[item],schema[item]):
					messages.append('{} is not valid'.format(item))

				# El flag de activación era global al validador y el dato es
				# por campo: si otro campo declaraba options, este bloque
				# corría igual y explotaba con KeyError.
				if 'options' in [r.strip() for r in schema[item].split(',')]:
					if options is None or item not in options:
						raise ValueError(
							"el campo '{}' declara la regla 'options' pero no se "
							"pasó options=[...] en rules()".format(item)
						)
					if not variable[item] in options[item]:
						messages.append('{} is not valid'.format(item))


			else:
				if schema[item].find('required') != -1:
					messages.append('{} is required'.format(item))
			
		elif isinstance(schema[item],dict):
			if item in variable and isinstance(variable[item], dict):
				if options is not None and item in options:
					messages = validate_schema(variable[item],schema[item],messages,options=options[item])
				else:
					messages = validate_schema(variable[item],schema[item],messages)
			elif item not in variable:
				# Check if any field in the nested schema is required
				nested_required = any(isinstance(v, str) and 'required' in v for v in schema[item].values() if isinstance(v, str))
				if nested_required:
					messages.append('{} is required'.format(item))

	return messages

def apply_filters_schema(variable, schema,messages=None):

	if isinstance(schema, str):
		schema = json.loads(schema)

	for item in schema:
		if isinstance(schema[item],str):
			if item in variable:
				variable[item] = filter(variable[item],schema[item])

		elif isinstance(schema[item],dict):
			# Antes recursaba sin comprobar que la rama existiera: un campo
			# anidado ausente en los datos daba KeyError.
			if item in variable and isinstance(variable[item], dict):
				apply_filters_schema(variable[item],schema[item])

	return variable

# Limpiar self.__data de valores que no esten en el schema
def clean_data(variable, schema):

	if isinstance(schema, str):
		schema = json.loads(schema)
	if isinstance(variable, str):
		try:
			variable = json.loads(variable)
		except ValueError as err:
			raise ValueError(
				"clean_data recibió un string que no es JSON válido: {}".format(err)
			) from err

	# Antes una lista producía `IndexError: list assignment index out of range`
	# al intentar borrar por clave.
	if not isinstance(variable, dict):
		raise TypeError(
			"clean_data espera un diccionario, no {}".format(type(variable).__name__)
		)

	keys_to_delete = []

	for item in variable:
		if item not in schema:
			keys_to_delete.append(item)
		elif isinstance(variable[item], dict) and isinstance(schema[item], dict):
			variable[item] = clean_data(variable[item], schema[item])

	for key in keys_to_delete:
		del variable[key]

	return variable


def getValue(path, schema, absolute=''):
	levels = path.split('.')

	if absolute == '':
		absolute = schema

	try:
		for i, level in enumerate(levels):
			if i == len(levels) - 1:
				if level in absolute:
					return absolute[level]
				else:
					return None
			else:
				if level not in absolute:
					return None
				absolute = absolute[level]
	except (KeyError, TypeError):
		return None

	return None


class InputRules:

	def __init__(self,data):
		# Copia defensiva: verify() limpia los campos no declarados y los
		# filtros transforman los valores. Sin esta copia, ambas cosas
		# mutaban el diccionario del llamante.
		self.__data = copy.deepcopy(data)
		self.__data_struct = None
		self.__data_filters = None
		self.__errors = []
		self.__options = {}
		self.__options_struct = {}
		self.__filters_applied = False

	def rules(self,field,rules,filters=None,options=None):

		if options is not None:
			self.__options[field] = options
			self.__options_struct = map_options(field,options,self.__options_struct)

		self.__data_struct = generate_structure(field,rules,self.__data_struct)
	
		if filters is not None:
			self.__data_filters = generate_structure(field,filters,self.__data_filters)

	def errors(self):
		return self.__errors

	def data(self):
		# Los filtros se aplican una única vez. Antes se re-aplicaban en cada
		# llamada: dos data() seguidos con el filtro 'md5' devolvían
		# md5(md5(valor)), y el resultado dependía de cuántas veces se hubiera
		# llamado al getter.
		if not self.__filters_applied and self.__data_filters is not None:
			self.__data = apply_filters_schema(self.__data,self.__data_filters)
			self.__filters_applied = True

		return copy.deepcopy(self.__data)

	def schema(self):
		return jsontools.convertToJson(self.__data_struct or {})
	
	def verify(self):

		if self.__options is not None:
			self.__errors = validate_schema(self.__data,self.__data_struct,options=self.__options_struct)
		else:
			self.__errors = validate_schema(self.__data,self.__data_struct)

		#Limpiar self.__data de valores que no esten en el schema
		self.__data = clean_data(self.__data,self.__data_struct)
	
		if len(self.__errors)>0:
			return False
		else:
			return True
		

class check:

	@staticmethod
	def rules(value,rules):

		rules_list = [
			'required',
			'options',
			'empty',
			'!empty',
			'!none',
			'none',
			'domain',
			'ip',
			'mail',
			'integer',
			'float',
			'numeric',
			'string',
			'uuid'

		]

		_check= True

		# Se descartan los espacios y los elementos vacíos: antes,
		# "required, integer" con un espacio tras la coma lanzaba
		# ValueError('Rule  integer not found').
		explode_rules = [r.strip() for r in rules.split(',') if r.strip()]

		for rule in explode_rules:

			if rule not in rules_list:
				raise ValueError('Rule {} not found'.format(rule))

			if rule=='required':
				# Check if value is present and not empty
				if value is None or value == '' or (isinstance(value, str) and value.strip() == ''):
					_check = False
				continue

			if rule=='uuid':
				if not check.uuid(value):
					_check= False

			if rule=='options':
				continue

			if rule=='empty':
				if not check.empty(value):
					_check= False

			if rule=='!empty':
				if check.empty(value):
					_check= False

			if rule=='!none':
				if not check.notnone(value):
					_check= False

			if rule=='none':
				if not check.none(value):
					_check= False

			if rule=='domain':
				if not check.domain(value):
					_check= False

			if rule=='ip':
				if not check.ip(value):
					_check= False

			if rule=='mail':
				if not check.mail(value):
					_check= False

			if rule=='integer':
				if not check.integer(value):
					_check= False

			if rule=='float':
				if not check.float(value):
					_check= False

			if rule=='numeric':
				if not check.numeric(value):
					_check= False

			if rule=='string':
				if not check.string(value):
					_check= False

		return _check


	@staticmethod
	def sanitize_sql(user_input):
		"""
		DEPRECADO. **No protege contra inyección SQL.**

		Es una lista negra, y como toda lista negra es evadible: la propia
		eliminación reconstruye patrones ("DROP DROP TABLE TABLE x" queda como
		"DROP  TABLE x") y no cubre variantes triviales como `OR 2=2`. Además
		destruye datos legítimos: un comentario que contenga "update the set
		of rules" o un guion doble pierde texto de forma irreversible.

		Usá consultas parametrizadas: los constructores `*_params` y `where`
		de `my_query`/`pg_query`.
		"""
		warnings.warn(
			"check.sanitize_sql() no protege contra inyección SQL: es una lista "
			"negra evadible que además mutila datos legítimos. Usá consultas "
			"parametrizadas (my_query.where / *_params).",
			DeprecationWarning,
			stacklevel=2,
		)

		if user_input is None:
			return ""

		# Convert to string if not already
		user_input = str(user_input)
		
		# Remove SQL comment indicators
		user_input = re.sub(r"--.*$", "", user_input, flags=re.MULTILINE)
		user_input = re.sub(r"/\*.*?\*/", "", user_input, flags=re.DOTALL)
		
		# Remove dangerous SQL characters
		user_input = re.sub(r"['\";]", "", user_input)
		
		# Remove multiple spaces and normalize whitespace
		user_input = re.sub(r"\s+", " ", user_input)
		
		# Remove common SQL injection patterns
		dangerous_patterns = [
			r"\bDROP\s+TABLE\b",
			r"\bDELETE\s+FROM\b",
			r"\bINSERT\s+INTO\b",
			r"\bUPDATE\s+.*\s+SET\b",
			r"\bCREATE\s+TABLE\b",
			r"\bALTER\s+TABLE\b",
			r"\bTRUNCATE\s+TABLE\b",
			r"\bEXEC\s*\(",
			r"\bEXECUTE\s*\(",
			r"\bUNION\s+SELECT\b",
			r"\bOR\s+1\s*=\s*1\b",
			r"\bAND\s+1\s*=\s*1\b"
		]
		
		for pattern in dangerous_patterns:
			user_input = re.sub(pattern, "", user_input, flags=re.IGNORECASE)
		
		return user_input.strip()
	
	@staticmethod
	def notnone(value):
		if value is None:
			return False
		else:
			return True

	@staticmethod
	def none(value):
		if value is None:
			return True
		else:
			return False

	@staticmethod
	def uuid(value):
		# Los validadores de formato devuelven False ante cualquier valor que
		# no sea string. Antes llamaban a re.match() directamente y lanzaban
		# TypeError con None, int o list: un JSON con `null` producía un 500
		# en vez de un error de validación.
		if not isinstance(value, str):
			return False
		return bool(re.match(
			r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z",
			value,
		))

	#Arrays
	@staticmethod
	def options(value,options):
		if value in options:
			return True
		else:
			return False

	#Contents
	@staticmethod
	def domain(value):
		# \w con re.UNICODE acepta dominios internacionalizados: 'ñandú.com.uy'
		# es registrable y el regex anterior lo rechazaba.
		if not isinstance(value, str):
			return False
		return bool(re.match(
			r"\A(?=.{1,255}\Z)[^\W_](?:[\w-]{0,61}[^\W_])?(?:\.[^\W\d_]{2,})+\Z",
			value,
			re.UNICODE,
		))

	@staticmethod
	def ip(value):
		"""
		Valida IPv4 e IPv6 con `ipaddress`.

		El regex anterior aceptaba '01.02.03.04': los ceros a la izquierda se
		interpretan como octal en algunas resoluciones y son un vector clásico
		de bypass de listas blancas. Tampoco soportaba IPv6.
		"""
		if not isinstance(value, str):
			return False
		try:
			ipaddress.ip_address(value)
			return True
		except ValueError:
			return False

	@staticmethod
	def mail(value):
		# \w con re.UNICODE acepta direcciones internacionalizadas (RFC 6531).
		# \A y \Z en vez de ^ y $ para que un \n final no permita colar texto.
		if not isinstance(value, str):
			return False
		return bool(re.match(
			r"\A[\w.+-]+@[\w-]+\.[\w.-]+\Z",
			value,
			re.UNICODE,
		))

	#States
	@staticmethod
	def empty(value):
		"""
		Ausencia de contenido.

		Tabla de verdad:

			None, '', '   ', [], {}, (), set()   -> True
			0, 0.0, False, '0', cualquier objeto -> False

		**Cero no es vacío.** Antes `empty(0)` era True mientras
		`rules(0,'required')` era True, con lo que `"required,!empty"` sobre
		un 0 se contradecía consigo mismo.
		"""
		if value is None:
			return True

		# bool antes que el resto: False es un valor, no una ausencia.
		if isinstance(value, bool):
			return False

		if isinstance(value, str):
			return value.strip() == ''

		if isinstance(value, (list, dict, tuple, set, frozenset)):
			return len(value) == 0

		# Los números nunca son vacíos, incluido el cero.
		if check.numeric(value):
			return False

		try:
			return len(value) == 0
		except TypeError:
			return False


	#types
	@staticmethod
	def string(value):
		if isinstance(value,str):
			return True
		else:
			return False

	@staticmethod
	def integer(value):
		# bool es subclase de int: sin la exclusión, `True` pasaba como entero
		# y luego filter('int') lo convertía en 1.
		return isinstance(value,int) and not isinstance(value,bool)

	@staticmethod
	def float(value):
		return isinstance(value,float) and not isinstance(value,bool)

	@staticmethod
	def numeric(value):
		if check.integer(value) or check.float(value):
			return True
		else:
			return False


def filter(value,rules):
	rules_list = [
		'xss',
		'sql',
		'str',
		'float',
		'int',
		'trim',
		'md5',
		'base64',
		'b64encode',
		'b64decode',
		'lower',
		'upper',
		'ucfirst',
		'ucwords',
		'json',
		'urldecode',
		'urlencode',
		'htmlentities',
		'htmlspecialchars',
		'striptags',
		'strip',
		'stripslashes',
		'addslashes',
		'nl2br',
		'br2nl'

	]

	# Se descartan los espacios: "trim, upper" lanzaba ValueError.
	tmp = [r.strip() for r in rules.split(',') if r.strip()]

	vistos = set()
	for rule in tmp:
		if rule in vistos:
			warnings.warn(
				"filtro '{}' repetido en '{}': aplicarlo dos veces no es "
				"idempotente ('a & b' con xss,xss da 'a &amp;amp; b')".format(rule, rules),
				UserWarning,
				stacklevel=2,
			)
		vistos.add(rule)

	for rule in tmp:

		if rule not in rules_list:
			raise ValueError('Filter {} not found'.format(rule))

		# None se propaga sin transformar: antes todos los filtros hacían
		# str(value) y guardaban la cadena 'None'. El filtro 'str' es la
		# excepción explícita, que lo convierte en ''.
		if value is None and rule not in ('str', 'string', 'json'):
			continue

		if rule=='int' or rule=='integer':
			try:
				if isinstance(value, float):
					# Truncar en silencio es pérdida de datos.
					if not value.is_integer():
						raise ValueError(
							'Value {!r} is not an integer: truncarlo perdería datos'.format(value)
						)
					value = int(value)
				else:
					value = int(value)
			except ValueError:
				raise
			except Exception:
				raise ValueError('Value is not integer')
			continue

		if rule=='str' or rule=='string':
			if value is None:
				value = ''
				continue

			if isinstance(value,dict) or isinstance(value,list):
				raise ValueError('Value is not string')

			try:
				value = str(value)
			except:
				raise ValueError('Value is not string')
			continue

		if rule=='float':
			try:
				value = float(value)
			except:
				raise ValueError('Value is not float')
			continue

		if rule=='trim' or rule=='strip':
			value = str(value).strip()
			continue

		if rule=='md5':
			value = hashlib.md5(str(value).encode()).hexdigest()
			continue

		if rule=='base64' or rule=='b64encode':
			value = base64.b64encode(str(value).encode()).decode()
			continue

		if rule=='b64decode':
			value = base64.b64decode(str(value)).decode()
			continue

		if rule=='lower':
			value = str(value).lower()
			continue

		if rule=='upper':
			value = str(value).upper()
			continue

		if rule=='ucfirst':
			value = str(value).capitalize()
			continue

		if rule=='ucwords':
			value = str(value).title()
			continue

		if rule=='json':
			value = json.dumps(value)
			continue

		if rule=='urldecode':
			value = urllib.parse.unquote(str(value))
			continue

		if rule=='urlencode':
			value = urllib.parse.quote(str(value))
			continue

		if rule=='htmlentities':
			value = html.escape(str(value))
			continue

		if rule=='htmlspecialchars':
			value = html.escape(str(value))
			continue

		if rule=='striptags':
			# Se aplica hasta punto fijo: en una sola pasada,
			# '<<script>script>' quedaba como '<script>' — la eliminación
			# reconstruía la etiqueta.
			value = str(value)
			while True:
				limpio = re.sub('<[^<>]*>', '', value)
				if limpio == value:
					break
				value = limpio
			value = value.replace('<', '').replace('>', '')
			continue

		if rule=='stripslashes':
			value = str(value).replace('\\','')
			continue

		if rule=='addslashes':
			value = str(value).replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
			continue

		if rule=='nl2br':
			value = str(value).replace('\n','<br>')
			continue

		if rule=='br2nl':
			value = str(value).replace('<br>','\n')
			continue
		if rule=='xss' or rule=="escape":
			value = html.escape(str(value))
			continue

		if rule=='sql':
			value = check.sanitize_sql(value)
			continue

	return value


class jsontools:

	@staticmethod
	def get(path,schema):
		levels = path.split('.')

		for i, level in enumerate(levels):
			if i == len(levels) - 1:
				return schema[level]
			else:
				if level not in schema:
					raise ValueError('Path not found')
				schema = schema[level]

		raise ValueError('Path not found')
				
	@staticmethod
	def get2(path,schema,absolute=''):
		levels = path.split('.')

		if absolute=='':
			absolute = schema

		for i, level in enumerate(levels):
			if i == len(levels) - 1:
				return absolute[level]
			else:
				if level not in absolute:
					return False
				absolute = absolute[level]

		return False
				
		
	@staticmethod
	def pretty(data):
		try:
			return json.dumps(json.loads(data),indent=1)
		except:
			return False

	@staticmethod
	def validate(data):
		try:
			json.loads(data)
		except (ValueError, TypeError) as err:
			#print(err)
			return False
		return True

	@staticmethod
	def convertJsonToList(data):
		try:
			return json.loads(data)
		except:
			return False

	@staticmethod
	def convertToJson(data):
		"""
		Serializa a JSON indentado. Devuelve False si el dato no es
		serializable.

		Antes se serializaba con str(dict) + replace("'", '"'), que produce
		repr de Python y no JSON: fallaba con comillas dobles, None, True y
		claves no-string, y el mecanismo de centinela que lo parcheaba dejaba
		el texto '### single quote ###' dentro del diccionario del llamante.
		"""
		if data is None:
			return False

		if isinstance(data,(dict,list)):
			try:
				return json.dumps(data,indent=1,ensure_ascii=False)
			except (TypeError, ValueError):
				return False

		try:
			return json.dumps(json.loads(data),indent=1,ensure_ascii=False)
		except (ValueError, TypeError) as err:
			return False

	@staticmethod
	def open(filename):
		f = open(filename,"r")
		content = f.read()
		f.close()
		return jsontools.convertToJson(content)

	@staticmethod
	def save(content,filename):
		f = open(filename, "w")
		f.write("{}\n".format(jsontools.pretty(content)))
		f.close()