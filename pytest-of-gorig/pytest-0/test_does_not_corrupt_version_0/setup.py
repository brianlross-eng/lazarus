from setuptools import setup
with open('setup.cfg') as f:
    for line in f:
        if line.startswith("version"):
            ver = line.replace("version = ", "")
setup(name='vprint', version='0.0.46.post314')
