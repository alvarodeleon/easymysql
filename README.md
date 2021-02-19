# EasyMySQL, una librería para manejo de MySQL en Python 

## Instalar EasyMySQL

```
pip install easymysql
```
Si les da algún error por tener una versión menor de Python pueden utilizar
```
pip3 install easymysql
```
## Conectar A La Base De Datos
```
#!/usr/bin/python

from easymysql.mysql import mysql

my = mysql('localhost','user_db','pass_db','db_name')
```

## Insertar Datos
Insertar datos es sumamente facil, solo hay que pasarle dos parámetros, el primero es el nombre de la tabla y el segundo un array con los datos a insertar:
```
my.insert('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
})
```
Donde el array será Clave-Valor donde clave corresponde con el nombre del campo de la tabla y el valor el valor a insertar.

## Actualizar Datos
Actualizar datos es similar a insertar solo que ahora le pasamos 3 datos, primero el nombre de la tabla, en segundo lugar el array con los datos a actualizar, mismo formato de array Clave-Valor que al insertar.

Por último el tercer parámetro es un array Clave-Valor con los datos del where o una cadena de texto SQL
```
my.update('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
},{
	'id':300
})
```
En el ejemplo anterior los datos del 3 parámetro (el array) toma los datos y forma una cadena SQL estándar concatenados con AND, ejemplo:
```
my.update('table_name',{
	'field_1':'value_1'
},{
	'field_2':'value_3',
	'field_3': 'value_3'
})
```

Esto se transformara en:
```
UPDATE table_name SET field_1=value_1 WHERE field_2='value_2' AND field_3='value_3'
```
En el siguiente caso, el tercer parámetro en lugar de ser un array enviamos una cadena:
```
my.update('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
},
	'field_2=value_2 OR field_3=value_3
)
```
La sentencia anterior se traduce en una sentencia SQL como la siguiente:
```
UPDATE table_name SET field_1=value_1,field_2=value_2,field_3=value_3 WHERE field_2='value_2' OR field_3='value_3'
```
## Buscar Y Listar Datos

Los select funcionan bastante parecidos que los casos anteriores, debemos pasarle el nombre de la tabla, el segundo parámetro es un array o un string con la consulta WHERE, en caso de omitir tarea los datos de toda la tabla, opcionalmente como tercer parámetro podemos establecer el orden

Para filtar datos:
```
lst = my.select('table_name', {'field_1': value_1})

lst = my.select('table_name', "field_1='value_1'")

#Si es un solo resultado:

[{'field_1': 'value_1', 'field_2': 'value_2','field_3':'value_3'}]

#Si son varios:

[{'field_1': 'value_1', 'field_2': 'value_2','field_3':'value_3'},
{'field_1': 'value4', 'field_2': 'value_5','field_3':'value_6'},
{'field_1': 'value_7', 'field_2': 'value_8','field_3':'value_9'}]

O se puede generar un WHERE con SQL estándar con LIKE, OR, >, <, etc

lst = my.select('table_name', "field_1 LIKE '%value%')
```
## Clausula Order

Técnicamente la cláusula ORDER no es solo ORDER sino que podemos colocar cualquier sentencia SQL que vaya despues del WHERE
```
lst = my.select('table_name', "field_1 LIKE '%value%',order='LIMIT 10')
lst = my.select('table_name', "field_1 LIKE '%value%',order='LIMIT 1,10')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC LIMIT 5')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC LIMIT 1,10')
```
##Recorrer Los Datos

Para recorer los datos solo se necesita un for:
```
lst = my.select('table_name')

for item in lst:
    print(item)

for item in lst:
    print(item['field_1'])
    print(item['field_2'])
    print(item['field_3'])
```
