def check(items):
    assert items
    return all(i.ok for i in items)
