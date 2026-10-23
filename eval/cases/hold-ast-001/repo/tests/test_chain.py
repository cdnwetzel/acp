from ledger.chain import append_row

def test_append_row():
    assert append_row([], {"seq": 0}) == [{"seq": 0}]
