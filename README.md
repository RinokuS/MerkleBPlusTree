# Отчет
## Постановка задачи
Необходимо реализовать Merkle B+ Tree или же B+ дерево с возможностью сравнения любых поддеревьев с помощью рекурсивного подсчета хэша каждой вершины по значениям хэшей ее детей.

## Реализация
В качестве референса для реализации был выбран данный исходный код: https://github.com/NicolasLM/bplustree

Дерево реализовано с сохранением данных на диске в силу эффективности данного подхода при хранении больших объемов данных (Эффективность конкретно для Merkle Tree оказалась сомнительной, подробнее в разделе "Проблемы")

В первую очередь, в имплементацию вершины было добавлено поле для хранение хэша, что потребовало также изменения функциий записи данных в файл и чтения из файла. Так как для хранения данных выбран обычный бинарный файл, то решением оказалось простая сериализация хэша в массив байт и включение этого массива вместе с его размером (для корректного считывания) в общий.

``` python
def dump(self) -> bytearray:
    data = bytearray()
    for record in self.entries:
        data.extend(record.dump())

    # used_page_length = len(header) + len(data), but the header is
    # generated later
    used_page_length = len(data) + 4 + PAGE_REFERENCE_BYTES
    assert 0 < used_page_length <= self._tree_conf.page_size
    assert len(data) <= self.max_payload

    next_page = 0 if self.next_page is None else self.next_page
    header = (
            self._node_type_int.to_bytes(1, ENDIAN) +
            used_page_length.to_bytes(3, ENDIAN) +
            next_page.to_bytes(PAGE_REFERENCE_BYTES, ENDIAN)
    )

    hash_as_bytes = self._tree_conf.hash_serializer.serialize(
        self._hash, self._tree_conf.hash_size
    )
    used_hash_length = len(hash_as_bytes)

    data = (
            bytearray(header) +

            used_hash_length.to_bytes(USED_VALUE_LENGTH_BYTES, ENDIAN) +
            hash_as_bytes +
            bytes(self._tree_conf.hash_size - used_hash_length) +

            data
    )

    padding = self._tree_conf.page_size - (used_page_length + USED_VALUE_LENGTH_BYTES + self._tree_conf.hash_size)
    assert padding >= 0
    data.extend(bytearray(padding))
    assert len(data) == self._tree_conf.page_size

    return data
```
В данном фрагменте кода представлен метод сериализации вершины в массив байт.

Далее в том же классе вершины был добавлен метод пересчета хэша для вершины. Хэширующей функцией выбран blake2 из-за того, что изменение одного бита данных приводит к изменению каждого бита хэша с 50% вероятностью, что позволяет сделать абсолютно любую функцию комбирирования хэшей дочерних вершин эффективной, ибо даже при незначительном изменении одной из вершин спровоцирует сильное изменение её хэш-значения.

В зависимости от типа вершины метод хэширования будет отличаться, если в случае с промежуточной вершиной мы можем просто скомбинировать хэши её дочерних вершин, то в случае с листовой вершиной мы этого сделать не можем, поэтому используем функцию строковой репрезентации каждой Entry (обертка над значением в листовой вершине) и обновим хэш с помощью кадого из Entry, лежащих в узле.

``` python
def compute_hash(self, mem):
    _hash = blake2b()

    if self._entry_class == Record:
        for i in self.entries:
            _hash.update(str(i).encode())
    elif self._entry_class == Reference:
        for i in self.entries:
            if i == self.entries[0]:
                left = mem.get_node(i.before)
                _hash.update(left.hash_.encode())

            right = mem.get_node(i.after)
            _hash.update(right.hash_.encode())

    self._hash = _hash.hexdigest()
```

Основная логика работы с деревом Меркля, а именно обновление хэша была добавлена в операциях добавления элемента в дерево и разделения вершины при переполнении. Стоит также уточнить, что выбран не рекурсивный подсчет хэша корня при вызове метода, а обновление хэша всего поддерева при изменении какого-либо из его элементов, что позволяет проводить сравнение двух непустых деревьев за константу.

Для корректного обновления хэш-значения в поддереве пришлось несколько пожертвовать оптимизацией, а именно добавить операцию пересчета хэш-значения для каждой вершины на пути к изменяемой, что приводит к вызову операции чтения всех дочерних вершин для каждой из тех, которые мы обновляем, а также добавить операцию записи для сохранения обновленных хэш-значений также для всех вершин в цепочке. Данные изменения никак не влияют на оптимизацию при выборе достаточно большого размера кэша, но при хранении большинства данных на диске вызывает сильное замедление работы дерева при операции добавления элемента.

``` python
def insert(self, key, value: bytes, replace=False):
    """Insert a value in the tree.

    :param key: The key at which the value will be recorded, must be of the
                same type used by the Serializer
    :param value: The value to record in bytes
    :param replace: If True, already existing value will be overridden,
                    otherwise a ValueError is raised.
    """
    if not isinstance(value, bytes):
        ValueError('Values must be bytes objects')

    with self._mem.write_transaction:
        node = self._search_in_tree(key, self._root_node)

        # Check if a record with the key already exists
        try:
            existing_record = node.get_entry(key)
        except ValueError:
            pass
        else:
            if not replace:
                raise ValueError('Key {} already exists'.format(key))

            if existing_record.overflow_page:
                self._delete_overflow(existing_record.overflow_page)

            if len(value) <= self._tree_conf.value_size:
                existing_record.value = value
                existing_record.overflow_page = None
            else:
                existing_record.value = None
                existing_record.overflow_page = self._create_overflow(
                    value
                )
            self._mem.set_node(node)
            return

        if len(value) <= self._tree_conf.value_size:
            record = self.Record(key, value=value)
        else:
            # Record values exceeding the max value_size must be placed
            # into overflow pages
            first_overflow_page = self._create_overflow(value)
            record = self.Record(key, value=None,
                                    overflow_page=first_overflow_page)

        if node.can_add_entry:
            node.insert_entry(record)
        else:
            node.insert_entry(record)
            self._split_leaf(node)
            node = self._search_in_tree(node.entries[0].key, self._root_node)

        curr_node = node
        while curr_node is not None:
            curr_node.compute_hash(self._mem)
            self._mem.set_node(curr_node)

            curr_node = curr_node.parent
```

Операции разделения вершин при переполнении также притерпели изменения, связанные с добавлением дополнительных операций записи данных.

``` python
def _split_leaf(self, old_node: 'Node'):
    """Split a leaf Node to allow the tree to grow."""
    parent = old_node.parent
    new_node = self.LeafNode(page=self._mem.next_available_page,
                                next_page=old_node.next_page)
    new_entries = old_node.split_entries()
    new_node.entries = new_entries
    ref = self.Reference(new_node.smallest_key,
                            old_node.page, new_node.page)

    if isinstance(old_node, LonelyRootNode):
        # Convert the LonelyRoot into a Leaf
        old_node = old_node.convert_to_leaf()
        self._create_new_root(ref)

        old_node.next_page = new_node.page

        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)
    elif parent.can_add_entry:
        parent.insert_entry(ref)
        self._mem.set_node(parent)

        old_node.next_page = new_node.page

        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)
    else:
        parent.insert_entry(ref)
        old_node.next_page = new_node.page

        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)

        self._split_parent(parent)

def _split_parent(self, old_node: Node):
    parent = old_node.parent
    new_node = self.InternalNode(page=self._mem.next_available_page)
    new_entries = old_node.split_entries()
    new_node.entries = new_entries

    ref = new_node.pop_smallest()
    ref.before = old_node.page
    ref.after = new_node.page

    if isinstance(old_node, RootNode):
        # Convert the Root into an Internal
        old_node = old_node.convert_to_internal()
        self._create_new_root(ref)

        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)
    elif parent.can_add_entry:
        parent.insert_entry(ref)
        self._mem.set_node(parent)

        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)
    else:
        parent.insert_entry(ref)
        new_node.compute_hash(self._mem)
        self._mem.set_node(old_node)
        self._mem.set_node(new_node)

        self._split_parent(parent)
```

Также для тестирования реализации были написаны примитивные юнит-тесты, проверяющие способность дерева верно подсчитывать свой хэш.

``` python
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
```
## Проблемы
### Неверный референс
Выбор неверного референса привел к тому, что в дереве неоказалось операции удаления, а самостоятельное добавление данной операции усложнено довольно громоздкой, хоть и удобной для использования, структурой дерева.

### Хранение данных на диске
Выбор на данный метод хранения данных пал в силу его эффективности при работе с большим объемом данных, но все преимущества данного подхода испарились в силу необходимости добавления дополнительных операций записи/чтения для корректного обновления хэш-значения вершин при каком-либо изменении дерева. <br>
Данный недостаток частично исправляется фактом наличия кэша в данной реализации дерева, но всплывает вторая проблема - невозможность валидации хэшей, считанных с диска, ибо они могут быть изменены во время использования дерева.