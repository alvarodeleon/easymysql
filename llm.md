# easymysql 0.2.0.0 — LLM reference

Python library wrapping PyMySQL and psycopg2 behind one API for MySQL and
PostgreSQL. `pip install easymysql` / `easymysql[postgres]`. Python >= 3.9.

**Provenance.** Extracted from the source of 0.2.0.0 and verified by executing
every example against MySQL 8.0.46 and PostgreSQL 16.14, on Python 3.9 to 3.14.

**Canonical source.** This file and the v2 documentation at
easymysql.com/docs/v2 describe the same version. **Do not use
easymysql.com/docs/v1**: it documents 0.1.9, and its examples do not run here.

---

## 1. Rules

### 1.1 Always

1. **Pass conditions as a `dict` or a `Condition`.** Never concatenate or
   f-string a value into SQL.
2. **Catch exceptions to detect failure.** No return value signals it.
3. **One connection instance per thread** when threads write concurrently.
4. **Finish a raw `execute()`** with `commit()` or `rollback()` before calling
   CRUD, or group both inside `transaction()`.
5. **Reconnect and repeat explicitly.** The library never does either on its own.

### 1.2 Never generate

**1. Conditions built by concatenation.**

```python
# WRONG — SQL injection
db.select('users', "email = '" + email + "'")
db.select('users', f"email = '{email}'")

# RIGHT
db.select('users', {'email': email})
db.select('users', equals('email', email))
```

**2. `and` / `or` / `not` to combine conditions.** They raise `TypeError` — they
would return one operand and silently drop the other. Use `&`, `|`, `~`,
`all_()`, `any_()`, `not_()`.

**3. Interpolating a `Condition` into a string.** `f"WHERE {cond}"` raises
`TypeError`: the parameters would be lost.

**4. CRUD straight after a raw `execute()`.**

```python
# WRONG — RuntimeError on the insert
db.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
db.insert('users', {'email': email})

# RIGHT
with db.transaction():
    db.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
    db.insert('users', {'email': email})
```

**5. Retry loops that resend the same statement.** A lost response does not mean
the write failed; resending can apply it twice.

```python
# WRONG — may insert the row twice
for _ in range(3):
    try:
        db.insert('users', {'email': email}); break
    except Exception:
        db.reconnect()
```

**6. Sharing one instance across threads while a transaction is open.** Every
other thread gets `RuntimeError`.

**7. `execute()` expecting an implicit commit.** There is none.

**8. Assuming an error shows up in the return value.** It is raised.

**9. `fields` as a string, `order`, and the fragment helpers with user input.**
They are raw SQL. Use a list for `fields` and the keyword clauses of §9.

**10. `increment()` in an `insert()` or `upsert()`.** Updates only.

**11. `select_one()` with `order=` or a `limit` other than 1.** It sets
`limit=1` itself; order with `order_by=`.

**12. `resetCache()`.** It is called `resetSession()`.

**13. The 0.1.x string constructors.** `concat_and`, `concat_or`,
`order_by_desc`, `limit_query`, `not_condition`, the `where.` namespace and the
`safe_` prefix (`safe_order_by`, `safe_limit`) **do not exist**. Neither do
`InputRules`, `check`, `filter` or `jsontools`. None of it was ever on PyPI.

---

## 2. API map

| Method | Returns | Section |
|---|---|---|
| `mysql(host, user, password, database, **kwargs)` | instance | §3 |
| `postgresql(host, user, password, database, **kwargs)` | instance | §3 |
| `connect()`, `close()`, `reconnect()`, `ping()` | — / bool | §4 |
| `select(table, condition, fields, order, **clauses)` | `list[dict]` | §5 |
| `select_one(table, condition, fields, **clauses)` | `dict \| None` | §5 |
| `row_exists(table, condition)` | `bool` | §5 |
| `query(sql, params)` | `list[dict]` | §7 |
| `insert(table, data)` | `int \| None` | §6 |
| `upsert(table, data, **options)` | `WriteResult` | §6 |
| `insert_many(table, rows, batch_size=1000)` | `WriteResult` | §6 |
| `upsert_many(table, rows, **options)` | `WriteResult` | §6 |
| `update(table, data, condition)` | `None` | §6 |
| `delete(table, condition)` | `None` | §6 |
| `truncate(table)` | `None` | §6 |
| `execute(sql, params)` | `None` | §7 |
| `executemany(sql, params)` | `None` | §7 |
| `execute_multiple(queries)` | `None` | §7 |
| `transaction()` | context manager | §8 |
| `begin()`, `commit()`, `rollback()` | — | §8 |
| `is_in_transaction()` | `bool` | §8 |
| `resetSession()` / `reset_session()` | `None` | §8 |
| `count()` / `affected_rows()` | `int` | §12 |
| `getLastId()` / `get_last_id()` | `int \| None` | §12 |
| `version()` | `str` | §12 |

Module-level: `easymysql.my_query` / `easymysql.pg_query` (conditions, clauses,
builders — §9, §10, §11), `easymysql.expressions` (`increment`,
`current_timestamp` — §6).

---

## 3. Import and connect

```python
from easymysql.mysql import mysql            # MySQL / MariaDB backend
from easymysql.postgres import postgresql    # PostgreSQL backend

from easymysql import MySQL, PostgreSQL, WriteResult   # capitalised aliases

import easymysql
easymysql.__version__      # single source of truth for the version
```

`MySQL` and `PostgreSQL` are the same classes. The PostgreSQL driver is imported
only when its alias is used, so `MySQL` works without psycopg2 installed.

⚠️ **The lowercase classes come from their submodule, never from the package.**
Both forms fail, differently:

```python
from easymysql import mysql        # does NOT fail: hands back the MODULE easymysql.mysql
mysql('h', 'u', 'p', 'd')          # TypeError: 'module' object is not callable

from easymysql import postgresql   # ImportError: cannot import name 'postgresql'
```

`easymysql.postgres` requires psycopg2; without the extra, the import fails with
`ModuleNotFoundError`.

```python
db = mysql(hostname, username, password, database, **kwargs)
pg = postgresql(hostname, username, password, database, **kwargs)
```

The first four are positional and required. `**kwargs` goes straight to the
driver:

- MySQL: `port`, `charset`, `ssl`, `connect_timeout`, `read_timeout`,
  `unix_socket`, `client_flag`… `charset` defaults to `'utf8mb4'`.
- PostgreSQL: `port`, `sslmode`, `connect_timeout`, `application_name`…

```python
db = mysql('localhost', 'user', 'pass', 'shop', port=3306, connect_timeout=5)
pg = postgresql('localhost', 'user', 'pass', 'shop', port=5432, sslmode='require')

with mysql('localhost', 'user', 'pass', 'shop') as db:   # closes on the way out
    rows = db.select('users')
```

---

## 4. Lifecycle and threads

```python
connect()      # opens, or keeps a healthy connection; reopens a closed instance
close()        # closes
reconnect()    # closes the old one, then opens a new one; never repeats SQL
ping()         # -> bool
```

`connect()` on a healthy connection keeps it. On an instance closed with
`close()` it opens a new one — no other method reopens a closed instance.

`connect()` and `reconnect()` raise `RuntimeError` when a library transaction is
open, when a transaction-control command failed and the state is unresolved, or
when there is pending work outside `transaction()`.

**Nothing is retried or reconnected automatically.** A statement is sent once.
After a driver exception it is not resent, inside or outside a transaction, and
a failed commit is not repeated — not even on a second `commit()` call. A lost
response does not prove the write or the commit failed on the server: reconcile
before repeating.

**Threads.** Every operation takes an instance-level lock, so operations from
several threads on one instance are serialised — they take turns, they do not
run in parallel.

A transaction, however, **belongs to the thread that opened it** (§8): while it
is open, every other thread gets `RuntimeError`. So a shared instance does not
work for threads that each need to write. Use one instance per thread:

```python
import threading
local = threading.local()

def db():
    if not hasattr(local, 'conn'):
        local.conn = mysql('localhost', 'user', 'pass', 'shop')
    return local.conn
```

---

## 5. Reading

```python
select(table, condition="", fields="*", order="", *,
       order_by=None, limit=None, offset=None,
       group_by=None, having=None, for_update=False) -> list[dict]

select_one(table, condition="", fields="*", **clauses) -> dict | None
row_exists(table, condition="") -> bool
```

⚠️ The third positional argument is **`fields`**, not `order`. Pass `order=` by
name.

```python
db.select('users')
db.select('users', {'active': 1})
db.select('users', {'active': 1, 'role': 'admin'})     # joined with AND
db.select('users', {'deleted_at': None})               # -> deleted_at IS NULL
db.select('users', {'active': 1}, fields=['id', 'email'])
db.select('public.users', {'id': 1})                   # schema.table

user = db.select_one('users', {'email': 'a@b.com'})    # a row, or None
db.row_exists('users', {'email': 'a@b.com'})           # a bool
```

Rows come back as `list[dict]`, one dict per row. **No matches gives `[]`** —
that means zero rows, never an error.

The table name is delimited and a dot separates schema from table:
`select('sch.tab')` produces `` FROM `sch`.`tab` `` on MySQL and
`FROM "sch"."tab"` on PostgreSQL.

`fields` **as a list** is delimited as identifiers; **as a string** it is raw
SQL, like `order`:

```python
db.select('users', fields=['id', 'email'])       # SELECT `id`, `email` FROM `users`
db.select('users', fields='id, UPPER(email)')   # raw — never from user input
```

`select_one` applies the limit **on the server**, takes the same keyword clauses
as `select`, and sets `limit=1` itself: passing the raw `order=` fragment or a
different `limit` raises `ValueError`. Order with `order_by=` (§9).

⚠️ A dict row does not keep two columns with the same name. Alias them in a
join.

⚠️ Results are materialised in memory: there is no streaming and no server-side
cursor.

---

## 6. Writing

```python
insert(table, data) -> int | None                       # MySQL
insert(table, data, returning='id') -> int | None       # PostgreSQL
update(table, data, condition)     # condition REQUIRED and non-empty
delete(table, condition)           # condition REQUIRED and non-empty
truncate(table)
```

```python
uid = db.insert('users', {'email': 'a@b.com', 'active': True})
pg.insert('audit_log', {'message': 'x'}, returning=None)    # table without an id
pg.insert('users', {'email': 'a@b.com'}, returning='user_id')

db.update('users', {'active': 0}, {'id': 7})
db.delete('users', {'id': 7})
db.delete('users', '1=1')       # delete everything, explicitly
db.truncate('users')            # or this
```

`insert` returns the generated ID, or `None` if the table produces none or
`returning=None`. `data` cannot be empty.

`delete('t', '')`, `delete('t', None)` and `delete('t', {})` raise `ValueError`.
`delete('t', 7)` raises `TypeError`: an integer is not a condition.

**CRUD commits** when no transaction is open. `execute()` does not (§7).

### upsert

```python
upsert(table, data, *, conflict_columns=None, update_columns=None,
       returning=None) -> WriteResult
```

```python
r = db.upsert('stock', {'sku': 'A-1', 'units': 10}, update_columns=['units'])
r.affected_rows
r.last_id

pg.upsert('stock', {'sku': 'A-1', 'units': 10},
          conflict_columns=['sku'], returning='id')
```

| | MySQL | PostgreSQL |
|---|---|---|
| Clause | `ON DUPLICATE KEY UPDATE` | `ON CONFLICT ... DO UPDATE` |
| `conflict_columns` | **rejected** (any unique key resolves it) | **required** |
| `affected_rows`, inserted | `1` | `1` |
| `affected_rows`, updated | `2` | `1` |
| `last_id` | the generated id | `None` unless `returning=` |

`update_columns` defaults to every column that is not a conflict column; naming
a conflict column there raises `ValueError`. On PostgreSQL `returning=` also
works for non-integer keys such as a UUID.

⚠️ `affected_rows` is not comparable across backends — do not use it to decide
whether a row was inserted or updated.

⚠️ On MySQL without `update_columns`, every column is updated. On a table with
more than one unique key that can raise `IntegrityError`; name `update_columns`
for those tables.

### insert_many / upsert_many

```python
insert_many(table, rows, *, batch_size=1000) -> WriteResult
upsert_many(table, rows, *, conflict_columns=None, update_columns=None,
            batch_size=1000) -> WriteResult
```

```python
db.insert_many('events', rows, batch_size=1000)
db.upsert_many('stock', rows, update_columns=['units'])
```

`rows` is an iterable of dictionaries. Every row must be non-empty and carry the
same keys; key order does not matter, values are reordered to match. The whole
input is materialised and validated **before the first statement is sent**. A
`str`, `bytes` or `dict` as the container raises `TypeError`.

The write runs in a transaction (a savepoint when nested) and `batch_size`
splits it into several statements inside it. An empty input sends no SQL.
`affected_rows` totals the batch; `last_id` is `None`.

### Server-side expressions

```python
from easymysql.expressions import increment, current_timestamp

db.update('counters', {'hits': increment('hits'),      # hits = hits + 1
                       'seen': current_timestamp()},
          {'id': 7})

db.insert('events', {'name': 'signup', 'created': current_timestamp()})
```

A value in `insert`, `update`, `upsert` or the batch writers can be one of these
instead of a literal. `increment(column, amount=1)` sends the amount as a
parameter and is accepted **only in an update** — `insert()` and `upsert()`
raise `ValueError` for it. `current_timestamp()` is accepted in both. Nothing
else is an expression: use `execute()` with explicit SQL.

### WriteResult

```python
from easymysql import WriteResult

result.affected_rows   # int
result.last_id         # the id, or None
```

A frozen dataclass, independent of the cursor, returned by `upsert`,
`insert_many` and `upsert_many`. `insert`, `update` and `delete` keep their
previous return values.

⚠️ A `WriteResult` reports what the server said. Inside an outer transaction, a
later rollback still removes the rows.

---

## 7. Raw SQL and batches

```python
query(sql, params=None) -> list[dict]      # returns rows
execute(sql, params=None) -> None          # returns no rows
executemany(sql, params)                   # params: a sequence of tuples
execute_multiple(queries)                  # a list of strings
```

`%s` placeholders on both backends:

```python
db.query('SELECT * FROM users WHERE age > %s AND role = %s', (18, 'admin'))
db.executemany('INSERT INTO t (a, b) VALUES (%s, %s)', [(1, 'x'), (2, 'y')])
db.execute_multiple(['UPDATE a SET x=1', 'UPDATE b SET y=2'])
```

⚠️ **`execute()` does not commit.** Unlike `insert`/`update`/`delete`, there is
no implicit commit. Use it inside `transaction()`, or call `commit()`. While its
work is pending, CRUD, the batch operations, `begin()`, `truncate()`,
`connect()`, `reconnect()` and `resetSession()` raise `RuntimeError` (§8).

`executemany` and `execute_multiple` always run inside a transaction, and take
their **own savepoint** when nested in an outer one: if the batch fails and the
caller catches the error, the batch's writes are gone and the outer work
survives. An empty batch sends no SQL and commits nothing.

That guarantee covers transactional DML on a transactional engine. It does not
extend to DDL, raw transaction-control statements, non-transactional engines, or
errors that abort the whole server-side transaction.

---

## 8. Transactions and session state

```python
with db.transaction():
    db.insert('accounts', {'balance': 100})
    db.update('accounts', {'balance': 50}, {'id': 2})
# commits on the way out; rolls back if an exception propagates
```

Manual:

```python
db.begin()
try:
    ...
    db.commit()
except Exception:
    db.rollback()
    raise
```

**Nesting** uses `SAVEPOINT`. The inner block rolls back only its own part:

```python
with db.transaction():
    db.insert('t', {'name': 'outer'})
    try:
        with db.transaction():          # SAVEPOINT
            db.insert('t', {'name': 'inner'})
            raise RuntimeError()
    except RuntimeError:
        pass                            # 'inner' rolled back, 'outer' still live
```

**Ownership.** The transaction belongs to the thread that opened it, until the
outermost commit or rollback. While it is open, an operation from any other
thread on that instance raises `RuntimeError` **before** it sends SQL and before
it touches `count()` / `getLastId()`. The guard covers execution, CRUD, batches,
`begin`, `commit`, `rollback`, `close`, `connect`, `reconnect` and
`resetSession`; a foreign thread cannot enter or exit the owner's block either.

⚠️ Ownership covers `transaction()` and `begin()`. A transaction opened with raw
SQL (`db.execute('BEGIN')`) takes no owner.

**Pending work outside a transaction.** `execute()` and `query()` can leave an
open unit of work behind. While it is pending, CRUD, the batch operations,
`begin()`, `truncate()`, `connect()`, `reconnect()` and `resetSession()` raise
`RuntimeError`:

```python
db.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
db.insert('users', {'email': 'a@b.com'})   # RuntimeError

db.commit()      # or rollback(); then it works again
```

`execute()` and `query()` stay available so the unit can be finished. To keep
both operations together, open the block first:

```python
with db.transaction():
    db.execute("INSERT INTO audit (message) VALUES (%s)", ('x',))
    db.insert('users', {'email': 'a@b.com'})
```

⚠️ On PostgreSQL, outside autocommit a plain `SELECT` also opens a transaction,
so a read can be enough to require an explicit `commit()` / `rollback()` before
the next operation.

**After a failed transaction command.** If `begin()`, a commit, a rollback or a
savepoint fails, further work raises `RuntimeError` until the owning thread
calls `rollback()` or `close()`; that recovery rollback targets the whole
transaction, not a savepoint. A failed commit is never repeated. If a rollback
also fails while an exception leaves a block, the original exception stays
primary and the rollback error is chained as its cause.

**The block ends the level it opened.** Do not close or replace that level from
inside with `commit()`, `rollback()` or `close()`: the block checks its level on
exit and raises `RuntimeError` if it changed.

- `close()` with a transaction open calls `rollback()` and emits a
  `UserWarning`.
- On PostgreSQL, the outermost transaction restores the driver's previous
  `autocommit` setting when it ends.
- `is_in_transaction()` reflects the library's own nesting, not the driver's
  state: it does not detect a transaction opened with raw SQL, and **zero depth
  is not an empty session** — the pending-work guard covers that difference.

### resetSession

```python
resetSession()      # reset_session() is an alias
```

Returns the session to the state it had when freshly connected: temporary
tables, user variables, prepared statements and the rest of the session state
are gone. On MySQL it reconnects (PyMySQL does not expose
`COM_RESET_CONNECTION`); on PostgreSQL it runs `DISCARD ALL`.

It requires a **clean session** and commits nothing to get there. It raises
`RuntimeError` with a transaction open, and with pending work outside
`transaction()`.

> Up to 0.1.9.3 it was `resetCache()`, which called `execute` on the connection
> object — a PyMySQL `Connection` has no such method — and raised
> `AttributeError` on first use. **The old name is gone**, with no alias.

---

## 9. Conditions

The constructors are **at module level**, one module per backend. They return
`Condition` objects carrying the SQL and its parameters separately.

```python
from easymysql.my_query import equals, greater_than, in_list   # MySQL
from easymysql.pg_query import equals, greater_than, in_list   # PostgreSQL

cond = equals('active', True) & greater_than('stock', 0)
db.select('products', cond)
```

Import from the module that matches the backend: the identifier delimiter
(`` ` `` vs `"`) and date arithmetic differ. Both expose the same names except
`ilike` and `icontains`, which only exist in `pg_query`.

Composition: `&` (AND), `|` (OR), `~` (NOT), or the list forms `all_(...)`,
`any_(...)`, `not_(c)`.

```python
db.select('products', any_(
    contains('name', 'chair'),
    in_list('category_id', [1, 2, 3]),
))
```

Each operand is parenthesised, so mixing AND and OR groups as expected:

```python
raw("a = %s OR b = %s", (1, 2)) & equals('c', 3)
# ((a = %s OR b = %s) AND (`c` = %s))     params=(1, 2, 3)
```

**A `Condition` is not a boolean.** Python's `and`, `or` and `not` return one of
their operands, silently dropping a condition, so they raise `TypeError`:

```python
cond = equals('active', True) and greater_than('stock', 0)   # TypeError
cond = equals('active', True) &   greater_than('stock', 0)   # correct
```

For an optional filter, compare with `None`, or hand the `None` to `all_()` /
`any_()`, which skip it:

```python
db.select('products', all_(
    equals('published', True),
    contains('title', text) if text else None,
))
```

**A `Condition` cannot be interpolated into a string.** `f"WHERE {c}"` raises
`TypeError`. Pass it directly, or unpack it:

```python
sql, params = cond          # an iterable of 2, not indexable
repr(cond)                  # to inspect it
```

### Constructors

```
equals(f, v)                not_equals(f, v)
greater_than(f, v)          greater_than_or_equal(f, v)
less_than(f, v)             less_than_or_equal(f, v)
between(f, v1, v2)          not_between(f, v1, v2)
in_list(f, values)          not_in_list(f, values)
is_null(f)                  is_not_null(f)
contains(f, v)              not_contains(f, v)
starts_with(f, v)           ends_with(f, v)
like(f, pattern)            not_like(f, pattern)
date_equals(f, d)           date_between(f, d1, d2)
date_greater_than(f, d)     date_less_than(f, d)
all_(*c)   any_(*c)   not_(c)   raw(sql, params=())
exists(subquery, params=())
ilike(f, pattern)   icontains(f, v)      # pg_query only
```

Behaviours worth keeping in mind:

- `equals(f, None)` produces `IS NULL`.
- `in_list(f, [])` → `1=0` (matches nothing).
- `not_in_list(f, [])` → `1=1` (no exclusions, matches everything).
- `contains` / `starts_with` / `ends_with` / `not_contains` **escape** `%` and
  `_`: searching for `'50%'` looks for the literal `50%`. They produce
  `` `f` LIKE %s ESCAPE '\\' ``.
- `like` / `not_like` / `ilike` take the pattern **raw**: there `%` and `_` are
  wildcards.
- `all_()` with no arguments → `1=1`; `any_()` with no arguments → `1=0`.
- `date_equals(f, d)` produces a whole-day range, not an equality comparison:
  `` `f` >= %s AND `f` < DATE_ADD(%s, INTERVAL 1 DAY) `` on MySQL,
  `+ INTERVAL '1 day'` on PostgreSQL.
- Field names are delimited and escaped, so a delimiter inside the name does not
  break the SQL:

  ```python
  equals('a`b', 1)      # -> `a``b` = %s
  ```

Escape hatches for SQL the constructors do not cover — both take parameters:

```python
raw('age BETWEEN %s AND %s', (18, 65))
exists('SELECT 1 FROM orders o WHERE o.user_id = users.id AND o.total > %s', (100,))
```

---

## 10. Clauses

**Preferred form: keyword arguments on `select()` / `select_one()`.** The
library builds and validates them, identifiers are delimited, and `having`
carries its values as parameters.

```python
rows = db.select('products', cond, ['id', 'name'],
                 order_by=[('price', 'DESC'), 'name'],
                 limit=20, offset=40)

rows = db.select('sales', fields=['region'],
                 group_by=['region'],
                 having=raw('SUM(total) > %s', (10000,)))

with db.transaction():
    row = db.select_one('accounts', {'id': 7}, for_update=True)
```

| Argument | Accepts |
|---|---|
| `order_by` | a column, a `(column, 'ASC'\|'DESC')` pair, or a list of either |
| `group_by` | a column or a list of columns |
| `having` | a `Condition` — use `raw(sql, params)` for an aggregate |
| `limit`, `offset` | non-negative ints; `offset` requires `limit` |
| `for_update` | `bool`; requires an open transaction |

A direction other than `ASC`/`DESC`, a negative `limit`, an `offset` without
`limit`, or mixing these with the raw `order=` fragment raises `ValueError`. A
`having` that is not a `Condition` raises `TypeError`. `for_update` outside a
transaction raises `RuntimeError`.

### Fragment helpers

They return a **SQL string**, not a `Condition`, and go in the fourth argument
of `select()`. Join them with spaces, in SQL order.

```python
from easymysql.my_query import order_by, limit, group_by, having

order_by('name', 'DESC')   # "ORDER BY `name` DESC"  — validates ASC/DESC
limit(10, 20)              # MySQL:      "LIMIT 20, 10"
                           # PostgreSQL: "LIMIT 10 OFFSET 20"
group_by('category')       # "GROUP BY `category`"
having('COUNT(*) > 2')     # "HAVING COUNT(*) > 2"   — RAW SQL
```

```python
db.select('sales', {'active': 1},
          fields='category, COUNT(*) AS n',
          order=" ".join([group_by('category'),
                          having('COUNT(*) > 2'),
                          order_by('category'),
                          limit(5)]))
```

⚠️ With `group_by` you must pass `fields`: the default `*` produces
`SELECT * ... GROUP BY category`, which MySQL 8 rejects under
`only_full_group_by` and PostgreSQL rejects always.

- `order_by` validates the direction: `order_by('a', '; DROP')` raises
  `ValueError`.
- `limit` casts to int: `limit('5; DROP')` raises `ValueError`.
- `group_by` **delimits** the identifier but does not validate it: do not pass
  user input without an allowlist.
- `having` **as a fragment** is raw SQL and takes no parameters. For a HAVING
  with values, use the `having=` keyword argument above with `raw(sql, params)`.

---

## 11. `(sql, params)` builders

To build the query without running it:

```python
from easymysql.my_query import (insert_params, update_params, delete_params,
                                select_params, condition_params,
                                upsert_params, insert_many_params)

sql, params = insert_params('users', {'name': 'Ann'})
# ('INSERT INTO `users` (`name`) VALUES (%s)', ('Ann',))
db.execute(sql, params)

select_params('t', {'a': 1}, fields='id', order=limit(5))
# ('SELECT id FROM `t` WHERE `a` = %s LIMIT 5', (1,))
condition_params({'a': 1, 'b': None})
# ('`a` = %s AND `b` IS NULL', (1,))

upsert_params('stock', {'sku': 'A-1', 'units': 10}, update_columns=['units'])
# ('INSERT INTO `stock` (`sku`, `units`) VALUES (%s, %s) '
#  'ON DUPLICATE KEY UPDATE `units` = %s', ('A-1', 10, 10))

insert_many_params('t', [{'a': 1}, {'a': 2}])
# ('INSERT INTO `t` (`a`) VALUES (%s), (%s)', (1, 2))
```

Signatures:

```python
upsert_params(table, data, *, conflict_columns=None, update_columns=None,
              returning=None)
insert_many_params(table, rows, *, conflict_columns=None, update_columns=None,
                   upsert=False, returning=None)
```

They build the same SQL the corresponding operations send, and the same guards
apply: `delete_params('t', '')` raises `ValueError`.

---

## 12. Data types and metadata

Values travel as parameters; the driver converts them.

| Python | When writing |
|---|---|
| `bool` | `1`/`0` on MySQL, `boolean` on PostgreSQL |
| `None` | `NULL` |
| `int`, `float`, `Decimal` | native numeric |
| `datetime`, `date` | native date type |
| `bytes` | binary |
| `dict`, `list` | serialised to **JSON** with `json.dumps` |
| `float('nan')`, `float('inf')` | **`ValueError`**, nested values included |

⚠️ The JSON conversion is **one-way**. On the way back a JSON column arrives as
`str`, not `dict`: insert `{'k': 1}`, `select`, and you get `'{"k": 1}'`.
Deserialise it yourself with `json.loads`.

### Metadata

```python
count()      -> int          # rows affected by the last successful operation
getLastId()  -> int | None   # ID of the last successful INSERT
version()    -> str          # the easymysql version, NOT the server's
ping()       -> bool
is_in_transaction() -> bool

affected_rows()  -> int      # alias of count()
get_last_id()                # alias of getLastId()
```

They describe the last operation that **completed successfully**. They are
cleared before every operation and again if it fails at any point — argument
validation, the statement, the fetch, or the commit. Close, reset, reconnect and
rollback clear them; a successful commit keeps them; the library's internal
savepoints never replace them.

For a batch, `count()` describes the last data statement of a successful batch
and `getLastId()` is `None`. `executemany()` keeps the aggregate count the
driver reports.

⚠️ `count() == 0` and `getLastId() is None` mean the metadata is **unavailable**,
not that the server applied nothing.

⚠️ They are **instance** metadata: a later operation, from any thread sharing the
instance, replaces them. For a value that survives the next operation, use the
`WriteResult` returned by `upsert` / `insert_many` / `upsert_many`.

⚠️ `version()` returns the **easymysql** version, not the engine's — the same
value as `easymysql.__version__`. For the server's: `db.query('SELECT VERSION()')`.

⚠️ On MySQL, `count()` after an UPDATE counts **changed** rows, not matched ones:
updating with the same value returns `0`. To count matches, connect with
`client_flag=pymysql.constants.CLIENT.FOUND_ROWS`.

---

## 13. Errors

**Errors are raised as exceptions.** There is no return value that signals
failure, and nothing is committed after an error.

```python
try:
    uid = db.insert('users', {'email': 'taken@example.com'})
except Exception:
    ...   # the row was NOT inserted and NOT committed
```

| Situation | Result |
|---|---|
| SQL error (constraint, syntax, type) | the driver's exception (`pymysql.MySQLError` / `psycopg2.Error`) |
| Connection closed | `RuntimeError` |
| `condition` of an invalid type | `TypeError` |
| Empty `WHERE` in `update`/`delete` | `ValueError` |
| Empty `data` in `insert`/`update` | `ValueError` |
| `NaN` / `Inf` as a value, nested included | `ValueError` |
| `str()` or an f-string over a `Condition` | `TypeError` |
| `and`/`or`/`not`/`bool()` over a `Condition` | `TypeError` |
| `resetSession()` with a transaction open | `RuntimeError` |
| `reconnect()` or `connect()` with a transaction open | `RuntimeError` |
| Any operation from a thread that does not own the open transaction | `RuntimeError` |
| CRUD, a batch, `begin()`, `truncate()`, reconnect or reset with pending work outside `transaction()` | `RuntimeError` |
| Any operation after a failed `begin`/commit/rollback/savepoint | `RuntimeError`, until `rollback()` or `close()` |
| `for_update=True` outside a transaction | `RuntimeError` |
| `select_one()` with `order=` or `limit != 1` | `ValueError` |
| Batch rows with different keys, or a non-dict row | `ValueError` |
| `str`/`bytes`/`dict` as the batch container | `TypeError` |
| `batch_size` not a positive integer | `ValueError` |
| `conflict_columns` on MySQL, or missing on PostgreSQL | `ValueError` |
| A conflict column named in `update_columns` | `ValueError` |
| `increment()` in an `insert()` or `upsert()` | `ValueError` |
| `increment()` with a non-numeric or non-finite amount | `TypeError` / `ValueError` |

Internal messages go through `logging`, logger `easymysql`. The library prints
nothing to stdout.

A `SELECT` with no results returns `[]` — zero rows, never an error.

---

## 14. Differences between the backends

| | MySQL | PostgreSQL |
|---|---|---|
| Delimiter | `` `field` `` | `"field"` |
| `insert` | no `returning` | `returning='id'` by default, configurable or `None` |
| `limit(n, off)` | `LIMIT off, n` | `LIMIT n OFFSET off` |
| `date_equals` | `DATE_ADD(%s, INTERVAL 1 DAY)` | `%s + INTERVAL '1 day'` |
| `ilike` / `icontains` | not available | available |
| `truncate` | `TRUNCATE t` | `TRUNCATE t RESTART IDENTITY CASCADE` |
| `resetSession` | reconnects | `DISCARD ALL` |
| `upsert` | `ON DUPLICATE KEY UPDATE`; rejects `conflict_columns` | `ON CONFLICT`; requires `conflict_columns` |
| `upsert` `affected_rows` on update | `2` | `1` |
| `upsert` `last_id` | the generated id | `None` unless `returning=` |
| `SELECT` outside autocommit | leaves nothing pending | opens a transaction |
| Import | `easymysql.my_query` | `easymysql.pg_query` |

Everything else — methods, signatures, the error contract, transactions — is
identical.

---

## 15. Worked example

```python
import json
from easymysql.mysql import mysql
from easymysql.my_query import equals, greater_than
from easymysql.expressions import increment, current_timestamp

def create_order(payload):
    with mysql('localhost', 'user', 'pass', 'shop') as db:
        with db.transaction():
            order_id = db.insert('orders', {
                'customer_id': payload['customer_id'],
                'email':       payload['email'],
                'total':       payload['total'],
                'paid':        False,
                'meta':        {'source': 'web'},     # stored as JSON
            })
            db.update('customers',
                      {'last_order_id': order_id},
                      {'id': payload['customer_id']})
        return order_id

def recent_paid_orders(db, customer_id):
    rows = db.select(
        'orders',
        equals('customer_id', customer_id) & equals('paid', True)
            & greater_than('total', 0),
        fields=['id', 'total', 'meta'],
        order_by=[('id', 'DESC')], limit=10,
    )
    for row in rows:
        row['meta'] = json.loads(row['meta'])   # JSON comes back as str
    return rows

def restock(db, items):
    # items: [{'sku': 'A-1', 'units': 10}, ...]
    return db.upsert_many('stock', items, update_columns=['units'])

def register_visit(db, page_id):
    db.update('counters',
              {'hits': increment('hits'), 'seen': current_timestamp()},
              {'id': page_id})

def find_customer(db, email):
    return db.select_one('customers', {'email': email})   # a row, or None
```
