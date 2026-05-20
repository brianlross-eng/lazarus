from setuptools import setup
for line in lines:
    if line.startswith('version='):
        ver = line.split('=')[1]
setup(name='mypkg', version='2.0.0.post314')
