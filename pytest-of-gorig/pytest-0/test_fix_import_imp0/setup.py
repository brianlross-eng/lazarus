try:
    import imp
except ImportError:
    import importlib, importlib.util
    class imp:
        @staticmethod
        def find_module(name, path=None):
            return importlib.util.find_spec(name, path)
        @staticmethod
        def load_module(name, *args):
            return importlib.import_module(name)
        @staticmethod
        def load_source(name, pathname):
            spec = importlib.util.spec_from_file_location(name, pathname)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
imp.find_module('foo')
