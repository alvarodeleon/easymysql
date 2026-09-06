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

### Names

`MySQL` and `PostgreSQL` are aliases with the usual capitalisation, importable
from the package itself. The PostgreSQL driver is only imported when the alias
is actually used, so `MySQL` costs nothing on a machine without `psycopg2`:

```python
from easymysql import MySQL, PostgreSQL, WriteResult
```

The original lowercase classes stay where they are and keep working; import them
from their submodule, as above — `from easymysql import mysql` would give you the
*module*, not the class. `affected_rows()`, `get_last_id()` and `reset_session()`
are aliases of `count()`, `getLastId()` and `resetSession()`.

## Error handling

**Statement errors are raised, not printed.** If statement execution fails,
`insert`, `update`, `delete` and `select` propagate the driver exception without
issuing a commit:

```python
try:
    my.insert('users', {'email': 'already@taken.com'})
except Exception as e:
    ...   # inspect the error before deciding how to recover
```

Statements and commits are **never retried automatically**, including after a
connection loss. A lost response does not prove that a write or commit failed
on the server. Reconcile an uncertain result before repeating the operation.

Reconnect explicitly with `reconnect()` when a connection is lost. It replaces
the session and never repeats SQL. It rejects an open library transaction or
an unresolved transaction-control failure. In that case, the owning thread
must first use `rollback()`, or `close()` if the connection cannot recover.
Closing and reconnecting cannot undo a commit that the server already applied.

`connect()` is idempotent on a healthy connection and rejects an open library
transaction. It can explicitly reopen a closed instance; CRUD never does so.

Library messages go through the standard `logging` module under the
`easymysql` logger.

## Thread safety

Operations take an instance-level lock, so queries are serialized. A transaction
opened with `transaction()` or `begin()` belongs to its starting thread until
the outermost commit or rollback. Database operations from other threads raise
`RuntimeError` before sending SQL or changing metadata, including attempts to
close, reset or reconnect that session. Nested transactions retain the owner.

This ownership covers library-managed transactions. Raw SQL transactions and
implicit transactions outside that API do not acquire an owner. Use one
instance per worker for those workflows and for parallelism. `count()` and
`getLastId()` are instance metadata: a subsequent operation can replace them.

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

It is not a boolean either. Python's `and`, `or` and `not` would silently drop
one of the operands, so `bool(cond)`, `if cond:` and `cond and other` raise
`TypeError` pointing at `&`, `|`, `~`, `all_()` and `any_()`. Test for a missing
filter with `is None` instead.

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

`select()` takes the ordering, grouping, paging and locking clauses as keyword
arguments. They are validated and rendered by the library, so identifiers are
quoted and `having` keeps its values as parameters:

```python
rows = my.select('products', cond, ['id', 'name'],
                 order_by=[('price', 'DESC'), 'name'],
                 limit=20, offset=40)

rows = my.select('sales', fields=['region'],
                 group_by=['region'],
                 having=raw('SUM(total) > %s', (10000,)))

with my.transaction():
    row = my.select_one('accounts', {'id': 7}, for_update=True)
```

`order_by` takes a column, a `(column, 'ASC'|'DESC')` pair, or a list of either.
`group_by` takes columns. `having` requires a `Condition` — use `raw()` for an
aggregate expression. `offset` requires `limit`, `for_update` requires an open
transaction, and mixing these with the raw `order=` fragment raises `ValueError`.

The older fragment helpers still work. `order_by`, `group_by`, `limit` and
`having` imported from `my_query` / `pg_query` return a SQL fragment, not a
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
must not be empty.** In 0.1.9.3 an empty one built `DELETE FROM t WHERE ;`,
whose syntax error was caught and printed, so the call did nothing while
looking like it had worked. Now it raises before any SQL is sent, and deleting
everything has to be spelled out:

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

## Upserts and Bulk Writes

`upsert()` writes a row through the engine's own conflict clause — one statement,
no select-then-insert race:

```python
result = my.upsert('stock', {'sku': 'A-1', 'units': 10},
                   update_columns=['units'])
result.affected_rows
result.last_id
```

MySQL uses `ON DUPLICATE KEY UPDATE` and resolves the conflict against any unique
key, so it rejects `conflict_columns`. PostgreSQL uses `ON CONFLICT` and
**requires** `conflict_columns`, and can return any column:

```python
pg.upsert('stock', {'sku': 'A-1', 'units': 10},
          conflict_columns=['sku'], returning='id')
```

`update_columns` defaults to every column that is not a conflict column. Naming a
conflict column there raises `ValueError`.

`last_id` carries the generated id on MySQL. On PostgreSQL it is `None` unless
you ask for a column with `returning=`, which also works for non-integer keys
such as a UUID.

⚠️ MySQL reports `affected_rows` as 1 for an inserted row and 2 for an updated
one; PostgreSQL reports 1 either way. Don't read that number as a row count
across backends.

`insert_many()` and `upsert_many()` take an iterable of dicts and write them in
multi-row statements:

```python
my.insert_many('events', rows, batch_size=1000)
my.upsert_many('stock', rows, update_columns=['units'])   # + conflict_columns on PostgreSQL
```

Every row must be a non-empty dict with the same keys — key order does not matter,
values are reordered to match. The whole input is materialized and validated
**before the first statement is sent**, so a bad row later in the list does not
leave half the batch written. The write runs in a transaction (a savepoint when
nested), `batch_size` splits it into several statements inside that same
transaction, and an empty input sends no SQL. Both return a `WriteResult` whose
`affected_rows` totals the batch and whose `last_id` is `None`.

`WriteResult` is a frozen dataclass, independent of the cursor, so it stays valid
after the next operation. Import it as `from easymysql import WriteResult`. It is
returned by the new operations only: `insert()`, `update()` and `delete()` keep
their existing return values.

## Server-side Expressions

Values in `insert()`, `update()`, `upsert()` and the bulk writers can be a bounded
expression instead of a literal, so the server computes them:

```python
from easymysql.expressions import increment, current_timestamp

my.update('counters', {'hits': increment('hits'),          # hits = hits + 1
                       'seen': current_timestamp()},
          {'id': 7})

my.insert('events', {'name': 'signup', 'created': current_timestamp()})
```

`increment()` is atomic on the server — no read-modify-write round trip — and its
amount still travels as a parameter. It only makes sense in an update, so
`insert()` rejects it. `current_timestamp()` works in both. Anything else belongs
in `execute()` with explicit SQL.

## Querying and Listing Data

```text
select(table, condition="", fields="*", order="", *,
       order_by=None, limit=None, offset=None,
       group_by=None, having=None, for_update=False) -> list[dict]
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
above are for. A list of `fields` is quoted as identifiers instead:

```python
my.select('users', fields=['id', 'email'])   # SELECT `id`, `email` FROM `users`
```

### One row, and existence

`select_one()` returns a single row or `None`, with the limit applied on the
server. `row_exists()` returns a boolean:

```python
user = my.select_one('users', {'email': 'ann@example.com'})
if user is None:
    ...

if my.row_exists('users', {'email': 'ann@example.com'}):
    ...
```

`select_one()` accepts the same keyword clauses as `select()` and sets `limit=1`
itself; passing the raw `order=` fragment or a different `limit` raises
`ValueError`, because the two limits would collide. Order with `order_by=`.

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

Let each `with` block finish its own transaction level; do not manually close
or replace that level using `commit()`, `rollback()` or `close()` inside the
block. The context checks its level before exiting. On PostgreSQL, the outer
transaction restores the driver's previous autocommit setting when it ends.

If `begin()`, commit, rollback or a savepoint command fails, new database work
is blocked until the owning thread calls `rollback()` or `close()`. Recovery
rollback then targets the whole transaction, not just a savepoint. If rollback
also fails while an exception leaves a block, the original exception remains
the primary one and the rollback error is chained as its cause.

⚠️ `execute()` is the raw path and does **not** commit, unlike `insert` /
`update` / `delete`. Use it inside a transaction, or call `commit()` yourself.

### Pending work outside a transaction

`is_in_transaction()` reports library nesting — the depth opened by
`transaction()` or `begin()` — not every kind of pending driver work. Zero depth
is not proof of a clean session: `execute()` and `query()` can leave an open unit
of work behind.

So no operation silently commits or discards work it did not start. When there is
pending work outside `transaction()`, CRUD, batches, `begin()`, `truncate()`,
`reconnect()` and `resetSession()` raise `RuntimeError` instead:

```python
my.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
my.insert('users', {'email': 'ann@example.com'})   # RuntimeError

my.commit()                     # or rollback(); then CRUD works again
```

Group both operations from the start when they belong to the same unit:

```python
with my.transaction():
    my.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
    my.insert('users', {'email': 'ann@example.com'})
```

On PostgreSQL a plain `SELECT` outside autocommit also opens a transaction, so a
read can be enough to require an explicit `commit()` or `rollback()` before the
next operation. `resetSession()` requires a clean session on both backends: it
never commits pending work to get there — that was the previous PostgreSQL
behaviour, which ran a commit before `DISCARD ALL`.

### Batches

`executemany()`, `execute_multiple()`, `insert_many()` and `upsert_many()` always
run inside a transaction. Nested in an outer one, each batch gets its own
savepoint: if the batch fails and the caller catches the error inside the outer
block, the batch's own writes disappear and the outer work survives.

```python
with my.transaction():
    my.insert('orders', {'customer_id': 7})
    try:
        my.execute_multiple([...])    # rolled back to its savepoint
    except Exception:
        pass
    my.insert('orders', {'customer_id': 8})
# both inserts commit; nothing from the failed batch does
```

That guarantee covers transactional DML on a transactional engine. It does not
extend to DDL, raw transaction-control statements, non-transactional engines, or
errors that abort the whole server-side transaction.

An empty batch sends no SQL and commits nothing.

## Result metadata

`count()` and `getLastId()` describe the **last operation that completed
successfully** on the instance:

```python
my.insert('users', {'email': 'ann@example.com'})
my.count()       # 1
my.getLastId()   # the generated id
```

After a failed validation, a failed statement, a failed fetch or an uncertain
commit, they reset to `0` and `None`. That means *metadata is unavailable* — it
is not evidence that the server applied nothing. Close, reset, reconnect and
rollback also clear them; a successful commit keeps the metadata of the data
operation, and the library's internal savepoints never overwrite it.

For batches, `count()` describes the last data statement of a successful batch and
`getLastId()` stays `None`, because a batch can mix operations. `executemany()`
keeps the aggregate count the driver reports.

They remain instance metadata: a later operation replaces them. `affected_rows()`
and `get_last_id()` are aliases with the current naming.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](./LICENSE.txt) file for details.
