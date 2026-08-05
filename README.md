# EasyMySQL: A Library for Managing MySQL in Python

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

### `where` — parameterized conditions (recommended)

`where` builds `Condition` objects that carry the SQL and its parameters
separately, so values never touch the query text:

```python
from easymysql.my_query import where          # or easymysql.pg_query

cond = where.equals('active', True) & where.greater_than('stock', 0)
rows = my.select('products', cond)

my.select('products', where.any_(
    where.contains('name', '50%'),            # the % is escaped, not a wildcard
    where.in_list('category_id', [1, 2, 3]),  # an empty list matches nothing
))
```

A `Condition` cannot be interpolated into a string — the parameters would be
lost — so pass it directly, or unpack it with `sql, params = cond`.

### Legacy operators (deprecated)

```python
from easymysql.my_query import select,insert,update,concat_and,concat_or,like,is_not_null,date_between,in_list,between
```

```python
from easymysql.pg_query import select,insert,update,concat_and,concat_or,like,ilike,is_not_null,date_between,in_list,between
```

These interpolate the value into the SQL string and emit a
`DeprecationWarning`. They are kept for backward compatibility; prefer
`where`.

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

## Data Validation with InputRules

EasyMySQL includes a powerful data validation system through the `InputRules` class. This class allows you to validate input data in a structured way and apply filters automatically.

### Importing

```python
from easymysql.rules import InputRules
```

### Basic Usage

```python
# Example data
data = {
    "id": 100,
    "name": "  John  ",
    "email": "john@example.com",
    "age": 25,
    "status": "active"
}

# Create InputRules instance
validator = InputRules(data)

# Define validation rules
validator.rules("id", "required,integer")
validator.rules("name", "required,string", "trim,upper")
validator.rules("email", "required,mail")
validator.rules("age", "required,integer")
validator.rules("status", "required,options", options=["active", "inactive"])

# Validate data
if validator.verify():
    print("Data is valid")
    validated_data = validator.data()
    print(validated_data)
else:
    print("Errors found:")
    for error in validator.errors():
        print(f"- {error}")
```

### Available Validation Rules

#### Basic Rules
- `required`: Field is required
- `string`: Must be a string
- `integer`: Must be an integer
- `float`: Must be a decimal number
- `numeric`: Must be a number (integer or decimal)
- `empty`: Must be empty
- `!empty`: Must not be empty
- `none`: Must be None
- `!none`: Must not be None

#### Format Rules
- `mail`: Must be a valid email address
- `domain`: Must be a valid domain
- `ip`: Must be a valid IP address
- `uuid`: Must be a valid UUID
- `options`: Must be in a list of valid options

### Available Filters

Filters are automatically applied to data after validation:

#### Text Filters
- `trim` or `strip`: Removes whitespace from beginning and end
- `lower`: Converts to lowercase
- `upper`: Converts to uppercase
- `ucfirst`: First letter uppercase
- `ucwords`: First letter of each word uppercase

#### Conversion Filters
- `int` or `integer`: Converts to integer
- `float`: Converts to decimal
- `str` or `string`: Converts to string

#### Encoding Filters
- `base64` or `b64encode`: Encodes in base64
- `b64decode`: Decodes from base64
- `md5`: Generates MD5 hash
- `urlencode`: Encodes for URL
- `urldecode`: Decodes from URL

#### Security Filters
- `xss` or `escape`: Escapes HTML characters
- `sql`: Sanitizes SQL input
- `htmlentities`: Converts characters to HTML entities
- `striptags`: Removes HTML tags

#### Format Filters
- `nl2br`: Converts line breaks to `<br>`
- `br2nl`: Converts `<br>` to line breaks
- `json`: Converts to JSON
- `serialize`: Serializes the object
- `unserialize`: Deserializes the object

### Nested Structure Validation

`InputRules` supports validation of nested data structures using dot notation:

```python
data = {
    "user": {
        "profile": {
            "name": "  Maria  ",
            "email": "maria@example.com",
            "age": 30
        },
        "settings": {
            "theme": "dark",
            "notifications": True
        }
    }
}

validator = InputRules(data)

# Validate nested fields
validator.rules("user.profile.name", "required,string", "trim,ucfirst")
validator.rules("user.profile.email", "required,mail")
validator.rules("user.profile.age", "required,integer")
validator.rules("user.settings.theme", "required,options", options=["light", "dark"])
validator.rules("user.settings.notifications", "required")

if validator.verify():
    validated_data = validator.data()
    print(validated_data)
```

### Complete Example with Options

```python
from easymysql.rules import InputRules

# Form data
form_data = {
    "username": "  admin  ",
    "password": "123456",
    "email": "admin@example.com",
    "role": "admin",
    "profile": {
        "first_name": "  john  ",
        "last_name": "  doe  ",
        "age": 35,
        "country": "US"
    }
}

# Valid options
role_options = ["admin", "user", "moderator"]
country_options = ["US", "CA", "UK", "DE", "FR"]

# Create validator
validator = InputRules(form_data)

# Define rules
validator.rules("username", "required,string", "trim,lower")
validator.rules("password", "required,string", "md5")
validator.rules("email", "required,mail")
validator.rules("role", "required,options", options=role_options)
validator.rules("profile.first_name", "required,string", "trim,ucfirst")
validator.rules("profile.last_name", "required,string", "trim,ucfirst")
validator.rules("profile.age", "required,integer")
validator.rules("profile.country", "required,options", options=country_options)

# Validate
if validator.verify():
    print("✓ Valid data")
    clean_data = validator.data()
    print("Processed data:", clean_data)
else:
    print("✗ Validation errors:")
    for error in validator.errors():
        print(f"  - {error}")
```

## check Class - Individual Validations

The `check` class provides static methods for validating individual values. It's useful for specific validations without needing to create a complete schema.

### Importing

```python
from easymysql.rules import check
```

### Validation Methods

#### Type Validation
```python
# Validate if it's a string
check.string("text")        # True
check.string(123)           # False

# Validate if it's an integer
check.integer(42)           # True
check.integer(3.14)         # False

# Validate if it's a decimal
check.float(3.14)           # True
check.float(42)             # False

# Validate if it's numeric (integer or decimal)
check.numeric(42)           # True
check.numeric(3.14)         # True
check.numeric("text")       # False
```

#### State Validation
```python
# Validate if it's empty
check.empty("")             # True
check.empty(None)           # True
check.empty(0)              # True
check.empty("text")         # False

# Validate if it's None
check.none(None)            # True
check.none("")              # False

# Validate if it's NOT None
check.notnone("text")       # True
check.notnone(None)         # False
```

#### Format Validation
```python
# Validate email
check.mail("user@example.com")      # True
check.mail("invalid-email")         # False

# Validate domain
check.domain("example.com")         # True
check.domain("invalid..domain")     # False

# Validate IP
check.ip("192.168.1.1")            # True
check.ip("999.999.999.999")        # False

# Validate UUID
check.uuid("123e4567-e89b-12d3-a456-426614174000")  # True
check.uuid("invalid-uuid")                          # False
```

#### Options Validation
```python
# Validate if it's in a list of options
options = ["red", "green", "blue"]
check.options("red", options)       # True
check.options("yellow", options)    # False
```

#### Validation with Multiple Rules
```python
# Use multiple rules separated by commas
check.rules("john@example.com", "required,mail")    # True
check.rules("", "required,string")                  # False
check.rules(25, "required,integer")                 # True
check.rules("test", "required,string,!empty")       # True
```

### Data Sanitization

```python
# Sanitize SQL input
user_input = "'; DROP TABLE users; --"
safe_input = check.sanitize_sql(user_input)
print(safe_input)  # " DROP TABLE users "
```

### Practical Examples

#### Registration Form Validation
```python
from easymysql.rules import check

def validate_registration(form_data):
    errors = []
    
    # Validate username
    if not check.rules(form_data.get('username'), 'required,string,!empty'):
        errors.append("Username is required and must be valid")
    
    # Validate email
    if not check.rules(form_data.get('email'), 'required,mail'):
        errors.append("Email must be a valid address")
    
    # Validate age
    if not check.rules(form_data.get('age'), 'required,integer'):
        errors.append("Age must be an integer")
    
    # Validate role
    valid_roles = ['admin', 'user', 'moderator']
    if not check.options(form_data.get('role'), valid_roles):
        errors.append("Role must be admin, user or moderator")
    
    return len(errors) == 0, errors

# Usage
form_data = {
    'username': 'john_doe',
    'email': 'john@example.com',
    'age': 28,
    'role': 'user'
}

is_valid, errors = validate_registration(form_data)
if is_valid:
    print("Valid form")
else:
    print("Errors:", errors)
```

#### Configuration Validation
```python
from easymysql.rules import check

def validate_config(config):
    """Validates system configuration"""
    
    # Validate database host
    if not check.rules(config.get('db_host'), 'required,string,!empty'):
        return False, "Database host is required"
    
    # Validate port
    port = config.get('db_port')
    if not check.integer(port) or port <= 0 or port > 65535:
        return False, "Port must be an integer between 1 and 65535"
    
    # Validate admin email
    admin_email = config.get('admin_email')
    if not check.mail(admin_email):
        return False, "Admin email is not valid"
    
    # Validate log level
    log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
    if not check.options(config.get('log_level'), log_levels):
        return False, "Log level must be DEBUG, INFO, WARNING or ERROR"
    
    return True, "Valid configuration"

# Usage
config = {
    'db_host': 'localhost',
    'db_port': 3306,
    'admin_email': 'admin@company.com',
    'log_level': 'INFO'
}

is_valid, message = validate_config(config)
print(message)
```

### Integration with EasyMySQL

```python
from easymysql.mysql import mysql
from easymysql.rules import InputRules, check

# Connect to database
db = mysql('localhost', 'user', 'password', 'database')

# User data
user_data = {
    'name': '  John Doe  ',
    'email': 'john@example.com',
    'age': 30,
    'status': 'active'
}

# Validate data before inserting
validator = InputRules(user_data)
validator.rules("name", "required,string", "trim,ucfirst")
validator.rules("email", "required,mail")
validator.rules("age", "required,integer")
validator.rules("status", "required,options", options=["active", "inactive"])

if validator.verify():
    # Valid data, insert into database
    clean_data = validator.data()
    user_id = db.insert('users', clean_data)
    print(f"User created with ID: {user_id}")
else:
    print("Validation errors:")
    for error in validator.errors():
        print(f"- {error}")
```

This documentation provides a complete guide for using both `InputRules` and the `check` class in the EasyMySQL context, allowing you to validate and sanitize data robustly before interacting with the database.


## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](./LICENSE.txt) file for details.