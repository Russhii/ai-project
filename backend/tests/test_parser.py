from app.services.parser import parse_python_file


SRC = '''
import os
from shop.db import save_order

@router.post("/checkout")
def handler(a: int, b=2) -> dict:
    """Doc."""
    return save_order(a, b)

class A(Base):
    def m(self):
        self.n()
    def n(self):
        pass
'''


def test_parser_extracts_structure():
    pf = parse_python_file("pkg/mod.py", SRC)
    by = {s.qualname: s for s in pf.symbols}
    assert set(by) == {"pkg.mod", "pkg.mod.handler", "pkg.mod.A", "pkg.mod.A.m", "pkg.mod.A.n"}
    h = by["pkg.mod.handler"]
    assert h.meta["params"] == ["a: int", "b"] and h.meta["returns"] == "dict"
    assert h.meta["route"] == "POST /checkout" and "save_order" in h.calls
    assert by["pkg.mod.A.m"].kind == "method" and by["pkg.mod.A"].bases == ["Base"]
    assert pf.imports["save_order"] == "shop.db.save_order"


def test_parser_reports_syntax_errors():
    assert parse_python_file("bad.py", "def (:").error
