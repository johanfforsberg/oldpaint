from oldpaint.util import Selectable


class DummyItem:
    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return str(self.n)


item1 = DummyItem(1)
item2 = DummyItem(2)
item3 = DummyItem(3)


def test_selectable():

    items = [item1, item2, item3]

    s = Selectable(items)

    assert s.current == item1
    s.select(item2)
    assert s.current == item2


def test_mro():
    items = [item1, item2, item3]
    s = Selectable(items)

    assert s.current == item1
    s.select_most_recent()
    assert s.current == item2
    assert s.mro[1] == item1
    s.select_most_recent()
    assert s.current == item1
    assert s.mro[1] == item2


def test_mro_no_update():
    items = [item1, item2, item3]
    s = Selectable(items)

    assert s.current == item1
    s.select_most_recent(update_mro=False)
    assert s.current == item2
    s.select_most_recent(update_mro=False)
    assert s.current == item3
    s.select_most_recent(update_mro=False)
    assert s.current == item1
