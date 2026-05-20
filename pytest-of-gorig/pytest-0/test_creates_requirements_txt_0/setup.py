from setuptools import setup
reqs = open('requirements.txt').read().splitlines()
setup(install_requires=reqs)
