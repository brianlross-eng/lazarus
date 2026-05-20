import pkg_resources
from setuptools import setup
version = pkg_resources.get_distribution('foo').version
setup(version=version)
