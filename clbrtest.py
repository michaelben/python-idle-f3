import EditorWindow
import os
import os.path

class A:
    def af(self):
        pass
    pass

class B(A):
    def bf(self):
        pass
    pass

class C(B, EditorWindow.EditorWindow):
    def cf(self):
        pass
    pass

def f():
    EditorWindow.EditorWindow.goto_definition()
    pass

def g():
    print EditorWindow.keynames
    pass
