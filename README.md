# EasyMySQL: A Library for Managing MySQL in Python

[Sitio Web del proyecto](https://www.alvarodeleon.net/easymysql-una-libreria-para-manejo-de-mysql-en-python/)

## Downloads
| **Total** | **Last Month** | **Last Week** |
|-----------|----------------|---------------|
| [![Downloads](https://static.pepy.tech/badge/easymysql)](https://pepy.tech/project/easymysql) | [![Downloads](https://static.pepy.tech/badge/easymysql/month)](https://pepy.tech/project/easymysql) | [![Downloads](https://static.pepy.tech/badge/easymysql/week)](https://pepy.tech/project/easymysql) |



## Installing EasyMySQL

```
pip install easymysql
```
If you encounter an error due to having an older version of Python, you can use:
```
pip3 install easymysql
```
## Connecting to the Database
```
#!/usr/bin/python

from easymysql.mysql import mysql

my = mysql('localhost','user_db','pass_db','db_name')
```

## Inserting Data
Inserting data is extremely easy; you only need to provide two parameters: the table name and an array with the data to insert:
```
my.insert('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
})
```
The array uses a Key-Value format where the key corresponds to the table field name, and the value is the value to be inserted.

## Updating Data
Updating data is similar to inserting, but this time you need to pass three parameters: the table name, an array with the data to update (Key-Value format), and a third parameter specifying the **WHERE** clause, either as a Key-Value array or a SQL string:
```
my.update('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
},{
	'id':300
})
```
The third parameter, if given as an array, will generate a standard SQL string concatenated with **AND**. For example:
```
my.update('table_name',{
	'field_1':'value_1'
},{
	'field_2':'value_3',
	'field_3': 'value_3'
})
```

This translates to:
```
UPDATE table_name SET field_1=value_1 WHERE field_2='value_2' AND field_3='value_3'
```
Alternatively, if the third parameter is a string:
```
my.update('table_name',{
	'field_1':'value_1',
	'field_2':'value_2',
	'field_3':'value_3',
},
	'field_2=value_2 OR field_3=value_3
)
```
This translates to:
```
UPDATE table_name SET field_1=value_1,field_2=value_2,field_3=value_3 WHERE field_2='value_2' OR field_3='value_3'
```
## Querying and Listing Data

The SELECT function works similarly to the previous cases. You provide the table name, an optional WHERE condition as an array or string, and optionally an ORDER clause as the third parameter.

To filter data:
```
lst = my.select('table_name', {'field_1': value_1})

lst = my.select('table_name', "field_1='value_1'")
```
If there's only one result:
```
[{'field_1': 'value_1', 'field_2': 'value_2','field_3':'value_3'}]
```
If there are multiple results:
```
[{'field_1': 'value_1', 'field_2': 'value_2','field_3':'value_3'},
{'field_1': 'value4', 'field_2': 'value_5','field_3':'value_6'},
{'field_1': 'value_7', 'field_2': 'value_8','field_3':'value_9'}]
```
You can also use standard SQL WHERE clauses with LIKE, OR, >, <, etc.:
```
lst = my.select('table_name', "field_1 LIKE '%value%')
```
## ORDER Clause

Technically, the **ORDER** clause can include any SQL statement that follows the **WHERE** clause:
```
lst = my.select('table_name', "field_1 LIKE '%value%',order='LIMIT 10')
lst = my.select('table_name', "field_1 LIKE '%value%',order='LIMIT 1,10')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC LIMIT 5')
lst = my.select('table_name', "field_1 LIKE '%value%',order='ORDER BY id DESC LIMIT 1,10')
```
## Iterating Through Data

To iterate through the data, simply use a **for** loop:
```
lst = my.select('table_name')

for item in lst:
    print(item)

for item in lst:
    print(item['field_1'])
    print(item['field_2'])
    print(item['field_3'])
```
