# EasyMySQL: A Python Library for MySQL and PostgreSQL

[Website](https://www.easymysql.com/)

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

### MySQL
```
#!/usr/bin/python

from easymysql.mysql import mysql

my = mysql('localhost','user_db','pass_db','db_name')
```

### PostgreSQL

PostgreSQL support requires the extra: `pip install easymysql[postgres]`

```python
#!/usr/bin/python

from easymysql.postgres import postgresql

my = postgresql('localhost','user_db','pass_db','db_name')
```

### Connection options

Any extra keyword argument is passed straight to the underlying driver:

```python
my = mysql('localhost','user','pass','db',
           port=3307, connect_timeout=5, charset='utf8mb4')

pg = postgresql('localhost','user','pass','db',
                port=5433, sslmode='require')
```

`charset` defaults to `utf8mb4` on MySQL. Both classes work as context
managers:

```python
with mysql('localhost','user','pass','db') as my:
    rows = my.select('table_name')
```

## Error handling

**Statement errors are raised, not printed.** A failed `insert`, `update`,
`delete` or `select` propagates the driver exception and no commit happens:

```python
try:
    my.insert('users', {'email': 'already@taken.com'})
except Exception as e:
    ...   # the row was NOT inserted and NOT committed
```

Library messages go through the standard `logging` module under the
`easymysql` logger.

## Thread safety

A connection instance is **safe** to share between threads but **not
parallel**: every operation takes an instance-level lock, so queries are
serialized. For real parallelism use one instance per thread, or a connection
pool.

## Query Builder

### Conditions

Every constructor returns a `Condition`, which carries the SQL and its
parameters separately, so values never touch the query text:

```python
from easymysql.my_query import equals, greater_than, any_, contains, in_list

cond = equals('active', True) & greater_than('stock', 0)
rows = my.select('products', cond)

my.select('products', any_(
    contains('name', '50%'),            # the % is escaped, not a wildcard
    in_list('category_id', [1, 2, 3]),  # an empty list matches nothing
))
```

Compose with `&` (AND), `|` (OR) and `~` (NOT), or with `all_()` / `any_()` /
`not_()` for lists. `all_()` and `any_()` skip `None`, which makes optional
filters straightforward:

```python
my.select('products', all_(
    equals('published', True),
    contains('title', text) if text else None,
    in_list('category', cats) if cats else None,
))
```

A `Condition` cannot be interpolated into a string — the parameters would be
lost — so pass it directly, or unpack it with `sql, params = cond`.

Anything the constructors don't cover goes through `raw()`, with the values
still travelling as parameters:

```python
from easymysql.my_query import raw

my.select('articles', raw('MATCH(title) AGAINST (%s IN BOOLEAN MODE)', ('+python',)))
```

Available: `equals`, `not_equals`, `greater_than`, `greater_than_or_equal`,
`less_than`, `less_than_or_equal`, `between`, `not_between`, `in_list`,
`not_in_list`, `is_null`, `is_not_null`, `contains`, `not_contains`,
`starts_with`, `ends_with`, `like`, `not_like`, `date_equals`,
`date_greater_than`, `date_less_than`, `date_between`, `exists`, `all_`,
`any_`, `not_`, `raw`. PostgreSQL adds `ilike` and `icontains`.

### Clauses

`order_by`, `group_by`, `limit` and `having` return a SQL fragment, not a
`Condition`, and go in the fourth argument of `select()`:

```python
from easymysql.my_query import order_by, limit

my.select('products', cond, 'id, name', order_by('price', 'DESC') + ' ' + limit(20, 40))
```

They validate instead of escaping, because there is no value to parameterize:
`order_by` only accepts `ASC` / `DESC`, and `limit` casts to `int`. Both raise
`ValueError` otherwise. `limit(20, 40)` renders as `LIMIT 40, 20` on MySQL and
`LIMIT 20 OFFSET 40` on PostgreSQL.

## Inserting Data

Two parameters: the table name and a dict with the data. The keys are column
names, the values are the values — and they travel as driver parameters, never
interpolated into the SQL:

```python
uid = my.insert('users', {
    'email':  'ann@example.com',
    'active': True,
    'meta':   {'source': 'web'},   # dicts and lists are stored as JSON
})
```

It returns the generated ID, or `None` if the table doesn't produce one. An
empty dict raises `ValueError`.

On PostgreSQL the ID comes from a `RETURNING` clause, so the column is
configurable:

```python
pg.insert('users', {'email': 'ann@example.com'}, returning='user_id')
pg.insert('audit_log', {'message': 'x'}, returning=None)   # table without an id
```

⚠️ JSON conversion is one-way. A JSON column reads back as `str`, not `dict`:
deserialize it yourself with `json.loads`.

## Updating and Deleting Data

`update()` takes the table, a dict of new values, and a condition.
`delete()` takes the table and a condition. **The condition is mandatory and
must not be empty** — in 0.1.9.3 an empty one silently emptied the table:

```python
my.update('users', {'active': 0}, {'id': 7})
my.delete('users', {'id': 7})

my.delete('users', '')      # ValueError
my.delete('users', 7)       # TypeError — an integer is not a condition
my.delete('users', '1=1')   # delete everything, explicitly
my.truncate('users')        # or this
```

A dict condition joins its entries with `AND`, and `None` becomes `IS NULL`:

```python
my.update('users', {'active': 0}, {'role': 'guest', 'deleted_at': None})
# UPDATE `users` SET `active` = %s WHERE `role` = %s AND `deleted_at` IS NULL
```

## Querying and Listing Data

```python
select(table, condition="", fields="*", order="") -> list[dict]
```

⚠️ The third positional argument is **`fields`**, not `order`. Pass `order=`
by name.

```python
rows = my.select('users')
rows = my.select('users', {'active': 1})
rows = my.select('users', {'active': 1, 'role': 'admin'})   # joined with AND
rows = my.select('users', equals('active', 1), fields='id, email')
rows = my.select('users', {'active': 1}, order='ORDER BY id DESC LIMIT 10')
rows = my.select('public.users', {'id': 1})                 # schema.table
```

The result is always a list of dicts, one per row:

```python
[{'id': 1, 'email': 'ann@example.com', 'active': 1},
 {'id': 2, 'email': 'bob@example.com', 'active': 1}]
```

No matching rows gives `[]`. That means zero rows — never an error; errors are
raised.

Iterate with a plain `for`:

```python
for row in my.select('users'):
    print(row['email'])
```

`fields` and `order` are interpolated **raw** — they are SQL, not data. Never
build them from user input without validating: that is what the clause helpers
above are for.

## Transactions

```python
with my.transaction():
    order_id = my.insert('orders', {'customer_id': 7})
    my.update('customers', {'last_order_id': order_id}, {'id': 7})
# commits on exit, rolls back if an exception propagates
```

Nesting is supported through savepoints: an inner block rolls back its own work
without killing the outer one. `begin()`, `commit()` and `rollback()` are there
for manual control.

⚠️ `execute()` is the raw path and does **not** commit, unlike `insert` /
`update` / `delete`. Use it inside a transaction, or call `commit()` yourself.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](./LICENSE.txt) file for details.