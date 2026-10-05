"""models.py(ORM)가 db/schema.sql과 같은 테이블·컬럼을 갖는지 검사한다."""
from pathlib import Path

import pglast

import models  # noqa: F401
from database import Base

SQL = (Path(__file__).parent.parent / "db" / "schema.sql").read_text(encoding="utf8")


def sql_tables():
    out = {}
    for stmt in pglast.parse_sql(SQL):
        n = stmt.stmt
        if type(n).__name__ == "CreateStmt":
            out[n.relation.relname] = {e.colname for e in n.tableElts if type(e).__name__ == "ColumnDef"}
    return out


def test_tables_and_columns_match():
    sql = sql_tables()
    orm = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert set(sql) == set(orm)
    for t in sql:
        assert sql[t] == orm[t], (t, sql[t] ^ orm[t])
