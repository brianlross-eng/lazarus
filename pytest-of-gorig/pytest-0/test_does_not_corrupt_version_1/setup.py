from setuptools import setup
class MyCmd:
    user_options = [
        ('version=', 'v', 'Show version'),
    ]
setup(name='mypkg', version='1.0.0.post314')
