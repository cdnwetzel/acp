from metrics import store

def test_record_event():
    s = []
    store.record_event(s, "e")
    assert s == ["e"]
