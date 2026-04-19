"""
Mock tkinter/customtkinter variables and widgets for headless operation.
Allows original tab classes to work without a GUI by simulating StringVar, BooleanVar, etc.
"""

class MockVar:
    """Mock variable that mimics tkinter StringVar/IntVar/BooleanVar"""
    def __init__(self, value=''):
        self._value = value
    
    def get(self):
        return self._value
    
    def set(self, value):
        self._value = value
    
    def __repr__(self):
        return f"MockVar({self._value!r})"


class MockStringVar(MockVar):
    pass

class MockBooleanVar(MockVar):
    def __init__(self, value=False):
        super().__init__(value)

class MockIntVar(MockVar):
    def __init__(self, value=0):
        super().__init__(value)


class MockWidget:
    """Mock widget that does nothing but stores attributes"""
    def __init__(self, *args, **kwargs):
        self._children = []
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def pack(self, **kwargs): pass
    def pack_forget(self): pass
    def grid(self, **kwargs): pass
    def place(self, **kwargs): pass
    def configure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def cget(self, key):
        return getattr(self, key, '')
    def winfo_children(self):
        return self._children
    def destroy(self): pass
    def update(self): pass


class MockFrame(MockWidget):
    pass

class MockLabel(MockWidget):
    pass

class MockButton(MockWidget):
    pass

class MockEntry(MockWidget):
    pass
