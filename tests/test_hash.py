import unittest

from bplustree.tree import BPlusTree
from .conftest import filename


def test_hash_simple():
    b = BPlusTree(filename, order=5)
    for i in [10, 20, 30, 40]:
        b.insert(i, str(i).encode())

    c = BPlusTree('/tmp/bplustree-test.index', order=5)
    for i in [20, 10, 40, 30]:
        c.insert(i, str(i).encode())

    assert b._root_node.hash_ == c._root_node.hash_

    for i in [1, 2, 3, 4]:
        b.insert(i, str(i).encode())
    for i in [1, 2, 3, 4]:
        c.insert(i, str(i).encode())

    assert b._root_node.hash_ == c._root_node.hash_

    b.insert(5, b'5')
    c.insert(6, b'6')

    assert b._root_node.hash_ != c._root_node.hash_


def test_hash_advanced():
    b = BPlusTree('/tmp/bplustree-test-advanced.index', order=5)
    for i in [10, 20, 30, 40, 70, 110]:
        b.insert(i, str(i).encode())

    c = BPlusTree('/tmp/bplustree-test_advanced.index', order=5)
    for i in [20, 10, 40, 30, 110, 70]:
        c.insert(i, str(i).encode())

    assert b._root_node.hash_ == c._root_node.hash_

    for i in [50, 55, 60, 65]:
        b.insert(i, str(i).encode())
    for i in [50, 55, 60, 65]:
        c.insert(i, str(i).encode())

    assert b._root_node.hash_ == c._root_node.hash_

    b.insert(5, b'5')
    c.insert(6, b'6')

    assert b._root_node.hash_ != c._root_node.hash_


def test_hash_advanced2():
    b = BPlusTree('/tmp/bplustree-test-advanced_.index', order=5)
    for i in range(2, 10001):
        b.insert(i, str(i).encode())

    for i in [0, 1, 10001, 10002]:
        b.insert(i, str(i).encode())

    c = BPlusTree('/tmp/bplustree-test_advanced_.index', order=5)
    for i in range(2, 10001):
        c.insert(i, str(i).encode())

    for i in [1, 0, 10002, 10001]:
        c.insert(i, str(i).encode())

    assert b._root_node.hash_ == c._root_node.hash_


class MyTestCase(unittest.TestCase):
    pass


if __name__ == '__main__':
    unittest.main()
