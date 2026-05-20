from importlib.metadata import version as get_distribution
__version__ = get_distribution("mypackage").version
