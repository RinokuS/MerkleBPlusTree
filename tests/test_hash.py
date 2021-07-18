import unittest

from bplustree.memory import FileMemory
from bplustree.node import LonelyRootNode, LeafNode
from bplustree.tree import BPlusTree
from bplustree.serializer import (
    IntSerializer, StrSerializer, UUIDSerializer, DatetimeUTCSerializer
)
from .conftest import filename


class MyTestCase(unittest.TestCase):
    def test_something(self):
        b = BPlusTree(filename, order=5)
        for i in [10, 20, 30, 40]:
            b.insert(i, str(i).encode())

        c = BPlusTree('/tmp/bplustree-test.index', order=5)
        for i in [20, 10, 40, 30]:
            c.insert(i, str(i).encode())

        assert b._root_node.hash_ == c._root_node.hash_


if __name__ == '__main__':
    unittest.main()
