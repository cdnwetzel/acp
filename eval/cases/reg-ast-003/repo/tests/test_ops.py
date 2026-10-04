from ops import divide as safe_divide

def test_divide():
    assert safe_divide(6, 2) == 3
