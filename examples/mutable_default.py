"""A small execution-fidelity example; expected output is [1], then [1, 2]."""


def append(value, items=[]):
    items.append(value)
    return items


print(append(1))
print(append(2))
