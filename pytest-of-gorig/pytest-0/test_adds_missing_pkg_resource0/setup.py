from setuptools import setup
import pkg_resources
version = pkg_resources.get_distribution('foo').version
setup(version=version)
