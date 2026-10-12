import json
import re
import struct
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional, Union

from core.config import mssql_settings

JSON_COLUMNS = {
    "employees": {"badges"},
    "tests": {"in_progress", "proctoring", "ai_analysis"},
    "test_questions": {"options"},
    "portal_settings": {"value"},
    "evaluations": {"bloom_scores", "bloom_submissions", "bloom_graded"},
    "candidate_interview_data": {"evaluation"},
}

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UUID_VALUE_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ISO_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
MAX_IN = 1000
OPS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "like": "LIKE"}

Where = Union[None, dict, list]


def ident(name: str) -> str:
    if not IDENT_RE.match(name):
        raise ValueError(f"Invalid identifier: {name}")
    return f"[{name}]"


def normalize_where(where: Where) -> list[tuple]:
    if not where:
        return []
    if isinstance(where, dict):
        out = []
        for col, val in where.items():
            if val is None:
                out.append((col, "is_null", None))
            elif isinstance(val, (list, tuple, set)):
                out.append((col, "in", list(val)))
            else:
                out.append((col, "eq", val))
        return out
    return [tuple(item) if len(item) == 3 else (item[0], item[1], None) for item in where]


def normalize_order(order: Union[None, str, list]) -> list[tuple[str, bool]]:
    if not order:
        return []
    items = [order] if isinstance(order, str) else list(order)
    out = []
    for item in items:
        if isinstance(item, str):
            parts = item.split()
            out.append((parts[0], len(parts) > 1 and parts[1].lower() == "desc"))
        else:
            out.append((item[0], str(item[1]).lower() == "desc"))
    return out


def normalize_columns(columns: Union[None, str, Iterable[str]]) -> Optional[list[str]]:
    if not columns or columns == "*":
        return None
    if isinstance(columns, str):
        return [c.strip() for c in columns.split(",") if c.strip()]
    return list(columns)


def encode_value(column: str, value: Any, json_cols: set) -> Any:
    if column in json_cols:
        return None if value is None else json.dumps(value, ensure_ascii=False)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str) and (column.endswith("_at") or column.endswith("_date")) and ISO_VALUE_RE.match(value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return value
    return value


def decode_row(table: str, row: dict) -> dict:
    json_cols = JSON_COLUMNS.get(table, set())
    out = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, uuid.UUID):
            value = str(value).lower()
        elif isinstance(value, str):
            if key in json_cols:
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            elif UUID_VALUE_RE.match(value):
                value = value.lower()
        out[key] = value
    return out


class Store:
    def select(self, table: str, where: Where = None, columns=None, order=None, limit: Optional[int] = None,
               offset: Optional[int] = None) -> list[dict]:
        raise NotImplementedError

    def first(self, table: str, where: Where = None, columns=None, order=None) -> Optional[dict]:
        rows = self.select(table, where, columns, order, limit=1)
        return rows[0] if rows else None

    def count(self, table: str, where: Where = None) -> int:
        raise NotImplementedError

    def insert(self, table: str, rows: Union[dict, list[dict]]) -> list[dict]:
        raise NotImplementedError

    def update(self, table: str, values: dict, where: Where) -> int:
        raise NotImplementedError

    def delete(self, table: str, where: Where) -> int:
        raise NotImplementedError

    def upsert(self, table: str, row: dict, key: Union[str, list[str]]) -> dict:
        raise NotImplementedError

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        raise NotImplementedError

    def execute(self, sql: str, params: tuple = ()) -> int:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError


def _dto_converter(raw: bytes) -> datetime:
    t = struct.unpack("<6hI2h", raw)
    return datetime(t[0], t[1], t[2], t[3], t[4], t[5], t[6] // 1000,
                    tzinfo=timezone(timedelta(hours=t[7], minutes=t[8])))


def _str_converter(raw: Optional[bytes]) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")


class MssqlStore(Store):
    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or mssql_settings()
        self.pool_max = max(1, int(self.settings.get("pool_max") or 10))
        self.pool_wait_s = float(self.settings.get("pool_wait_s") or 20)
        self.slots = threading.BoundedSemaphore(self.pool_max)
        self.idle: list = []
        self.idle_lock = threading.Lock()

    def _conn_string(self) -> str:
        s = self.settings

        def esc(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        parts = [
            f"DRIVER={{{s['driver']}}}",
            f"SERVER={s['server']},{s['port']}",
            f"DATABASE={s['database']}",
            f"UID={esc(s['user'])}",
            f"PWD={esc(s['password'])}",
            f"Encrypt={'yes' if s['encrypt'] else 'no'}",
            f"TrustServerCertificate={'yes' if s['trust_cert'] else 'no'}",
            "Connection Timeout=15",
        ]
        return ";".join(parts)

    def _connect(self):
        import pyodbc

        conn = pyodbc.connect(self._conn_string(), autocommit=True)
        conn.add_output_converter(-155, _dto_converter)
        conn.add_output_converter(pyodbc.SQL_CHAR, _str_converter)
        conn.add_output_converter(pyodbc.SQL_VARCHAR, _str_converter)
        conn.add_output_converter(pyodbc.SQL_LONGVARCHAR, _str_converter)
        conn.setencoding(encoding="utf-8")
        return conn

    def _acquire(self):
        if not self.slots.acquire(timeout=self.pool_wait_s):
            raise RuntimeError("Database connection pool exhausted")
        try:
            with self.idle_lock:
                conn = self.idle.pop() if self.idle else None
            return conn or self._connect()
        except BaseException:
            self.slots.release()
            raise

    def _release(self, conn, broken: bool = False) -> None:
        try:
            if broken:
                try:
                    conn.close()
                except Exception:
                    pass
            else:
                with self.idle_lock:
                    self.idle.append(conn)
        finally:
            self.slots.release()

    def pool_stats(self) -> dict:
        with self.idle_lock:
            idle = len(self.idle)
        return {"max": self.pool_max, "idle": idle, "inUse": self.pool_max - self.slots._value}

    def _run(self, sql: str, params: tuple, fetch: bool):
        import pyodbc

        def transient(err) -> bool:
            state = str(err.args[0]) if err.args else ""
            return state.startswith("08") or state in {"HY000", "HYT00", "01000"}

        for attempt in (0, 1):
            try:
                conn = self._acquire()
            except pyodbc.Error as err:
                if attempt == 0 and transient(err):
                    continue
                raise
            broken = False
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                if fetch and cursor.description:
                    names = [d[0] for d in cursor.description]
                    rows = [dict(zip(names, r)) for r in cursor.fetchall()]
                    cursor.close()
                    return rows
                count = cursor.rowcount
                cursor.close()
                return count
            except pyodbc.Error as err:
                broken = transient(err)
                if attempt == 0 and broken:
                    continue
                raise
            finally:
                self._release(conn, broken)

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        return [decode_row("", r) for r in self._run(sql, params, True)]

    def execute(self, sql: str, params: tuple = ()) -> int:
        return self._run(sql, params, False)

    def ping(self) -> bool:
        try:
            return bool(self._run("SELECT 1 AS ok", (), True))
        except Exception:
            return False

    def _where(self, table: str, where: list[tuple]) -> tuple[str, list]:
        json_cols = JSON_COLUMNS.get(table, set())
        clauses, params = [], []
        for col, op, val in where:
            c = ident(col)
            if op == "is_null":
                clauses.append(f"{c} IS NULL")
            elif op == "not_null":
                clauses.append(f"{c} IS NOT NULL")
            elif op in ("in", "not_in"):
                vals = list(val or [])
                if not vals:
                    clauses.append("1=0" if op == "in" else "1=1")
                    continue
                marks = ",".join("?" for _ in vals)
                clauses.append(f"{c} {'IN' if op == 'in' else 'NOT IN'} ({marks})")
                params.extend(encode_value(col, v, set()) for v in vals)
            elif op == "ilike":
                clauses.append(f"{c} LIKE ?")
                params.append(val)
            elif op in OPS:
                clauses.append(f"{c} {OPS[op]} ?")
                params.append(encode_value(col, val, set()))
            else:
                raise ValueError(f"Unsupported operator: {op}")
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def _split_big_in(self, where: list[tuple]):
        for i, (col, op, val) in enumerate(where):
            if op in ("in", "not_in") and len(val or []) > MAX_IN and op == "in":
                vals = list(val)
                for start in range(0, len(vals), MAX_IN):
                    yield where[:i] + [(col, "in", vals[start:start + MAX_IN])] + where[i + 1:]
                return
        yield where

    def select(self, table, where=None, columns=None, order=None, limit=None, offset=None):
        w = normalize_where(where)
        chunks = list(self._split_big_in(w))
        if len(chunks) > 1:
            rows = []
            for chunk in chunks:
                rows.extend(self.select(table, chunk, columns, order, None, None))
            for col, desc in reversed(normalize_order(order)):
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
            start = offset or 0
            return rows[start:start + limit] if limit is not None else rows[start:]
        cols = normalize_columns(columns)
        col_sql = ", ".join(ident(c) for c in cols) if cols else "*"
        where_sql, params = self._where(table, w)
        order_items = normalize_order(order)
        order_sql = ", ".join(f"{ident(c)} {'DESC' if d else 'ASC'}" for c, d in order_items)
        if offset is not None:
            sql = f"SELECT {col_sql} FROM [dbo].{ident(table)}{where_sql} ORDER BY {order_sql or '(SELECT NULL)'} OFFSET ? ROWS"
            params.append(int(offset))
            if limit is not None:
                sql += " FETCH NEXT ? ROWS ONLY"
                params.append(int(limit))
        else:
            top = f"TOP ({int(limit)}) " if limit is not None else ""
            sql = f"SELECT {top}{col_sql} FROM [dbo].{ident(table)}{where_sql}"
            if order_sql:
                sql += f" ORDER BY {order_sql}"
        return [decode_row(table, r) for r in self._run(sql, tuple(params), True)]

    def count(self, table, where=None):
        where_sql, params = self._where(table, normalize_where(where))
        rows = self._run(f"SELECT COUNT(*) AS n FROM [dbo].{ident(table)}{where_sql}", tuple(params), True)
        return int(rows[0]["n"])

    def _insert_one(self, table: str, row: dict) -> dict:
        json_cols = JSON_COLUMNS.get(table, set())
        data = dict(row)
        if table != "portal_settings" and not data.get("id"):
            data["id"] = str(uuid.uuid4())
        cols = list(data.keys())
        marks = ",".join("?" for _ in cols)
        sql = (f"INSERT INTO [dbo].{ident(table)} ({', '.join(ident(c) for c in cols)}) "
               f"OUTPUT INSERTED.* VALUES ({marks})")
        params = tuple(encode_value(c, data[c], json_cols) for c in cols)
        rows = self._run(sql, params, True)
        return decode_row(table, rows[0]) if rows else decode_row(table, data)

    def insert(self, table, rows):
        items = [rows] if isinstance(rows, dict) else list(rows)
        return [self._insert_one(table, r) for r in items]

    def update(self, table, values, where):
        if not values:
            return 0
        json_cols = JSON_COLUMNS.get(table, set())
        cols = list(values.keys())
        set_sql = ", ".join(f"{ident(c)} = ?" for c in cols)
        set_params = [encode_value(c, values[c], json_cols) for c in cols]
        total = 0
        for chunk in self._split_big_in(normalize_where(where)):
            where_sql, params = self._where(table, chunk)
            result = self._run(f"UPDATE [dbo].{ident(table)} SET {set_sql}{where_sql}", tuple(set_params + params), False)
            total += max(int(result), 0)
        return total

    def delete(self, table, where):
        total = 0
        for chunk in self._split_big_in(normalize_where(where)):
            where_sql, params = self._where(table, chunk)
            result = self._run(f"DELETE FROM [dbo].{ident(table)}{where_sql}", tuple(params), False)
            total += max(int(result), 0)
        return total

    def upsert(self, table, row, key):
        keys = [key] if isinstance(key, str) else list(key)
        json_cols = JSON_COLUMNS.get(table, set())
        data = dict(row)
        updatable = [c for c in data if c not in keys]
        where_sql = " AND ".join(f"{ident(k)} = ?" for k in keys)
        key_params = [encode_value(k, data[k], set()) for k in keys]
        if updatable:
            set_sql = ", ".join(f"{ident(c)} = ?" for c in updatable)
            update_params = [encode_value(c, data[c], json_cols) for c in updatable]
            updated = self._run(f"UPDATE [dbo].{ident(table)} SET {set_sql} WHERE {where_sql}",
                                tuple(update_params + key_params), False)
        else:
            updated = 1 if self.count(table, {k: data[k] for k in keys}) else 0
        if not updated or int(updated) <= 0:
            self._insert_one(table, data)
        return self.first(table, {k: data[k] for k in keys}) or decode_row(table, data)


def _match(row: dict, where: list[tuple]) -> bool:
    for col, op, val in where:
        cur = row.get(col)
        if op == "is_null":
            ok = cur is None
        elif op == "not_null":
            ok = cur is not None
        elif op == "eq":
            ok = _eq(cur, val)
        elif op == "neq":
            ok = not _eq(cur, val)
        elif op == "in":
            ok = any(_eq(cur, v) for v in (val or []))
        elif op == "not_in":
            ok = not any(_eq(cur, v) for v in (val or []))
        elif op in ("like", "ilike"):
            pattern = "^" + re.escape(str(val)).replace("%", ".*").replace("_", ".") + "$"
            ok = cur is not None and re.match(pattern, str(cur), re.I | re.S) is not None
        elif cur is None:
            ok = False
        else:
            ok = {"gt": cur > val, "gte": cur >= val, "lt": cur < val, "lte": cur <= val}[op]
        if not ok:
            return False
    return True


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


class MemoryStore(Store):
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.lock = threading.RLock()

    def seed(self, table: str, rows: list[dict]) -> None:
        with self.lock:
            self.tables.setdefault(table, []).extend(json.loads(json.dumps(rows, default=str)))

    def _rows(self, table: str) -> list[dict]:
        return self.tables.setdefault(table, [])

    def select(self, table, where=None, columns=None, order=None, limit=None, offset=None):
        with self.lock:
            w = normalize_where(where)
            rows = [dict(r) for r in self._rows(table) if _match(r, w)]
            for col, desc in reversed(normalize_order(order)):
                rows.sort(key=lambda r: (r.get(col) is None, r.get(col) if r.get(col) is not None else 0), reverse=desc)
            start = offset or 0
            rows = rows[start:start + limit] if limit is not None else rows[start:]
            cols = normalize_columns(columns)
            if cols:
                rows = [{c: r.get(c) for c in cols} for r in rows]
            return rows

    def count(self, table, where=None):
        with self.lock:
            w = normalize_where(where)
            return sum(1 for r in self._rows(table) if _match(r, w))

    def insert(self, table, rows):
        with self.lock:
            items = [rows] if isinstance(rows, dict) else list(rows)
            out = []
            for item in items:
                data = dict(item)
                if table != "portal_settings" and not data.get("id"):
                    data["id"] = str(uuid.uuid4())
                if "created_at" not in data and table != "portal_settings":
                    data["created_at"] = datetime.now(timezone.utc).isoformat()
                self._rows(table).append(data)
                out.append(dict(data))
            return out

    def update(self, table, values, where):
        with self.lock:
            w = normalize_where(where)
            n = 0
            for row in self._rows(table):
                if _match(row, w):
                    row.update(values)
                    n += 1
            return n

    def delete(self, table, where):
        with self.lock:
            w = normalize_where(where)
            keep = [r for r in self._rows(table) if not _match(r, w)]
            removed = len(self._rows(table)) - len(keep)
            self.tables[table] = keep
            return removed

    def upsert(self, table, row, key):
        with self.lock:
            keys = [key] if isinstance(key, str) else list(key)
            cond = {k: row[k] for k in keys}
            if self.update(table, {k: v for k, v in row.items() if k not in keys}, cond) == 0:
                self.insert(table, row)
            return self.first(table, cond)

    def ping(self) -> bool:
        return True


_store: Optional[Store] = None
_store_lock = threading.Lock()


def get_store() -> Store:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = MssqlStore()
    return _store


def set_store(store: Optional[Store]) -> None:
    global _store
    _store = store
