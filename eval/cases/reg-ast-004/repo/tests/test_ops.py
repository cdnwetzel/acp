import importlib

def test_divide():
    ops = importlib.import_module("ops")
    assert ops.divide(6, 2) == 3
