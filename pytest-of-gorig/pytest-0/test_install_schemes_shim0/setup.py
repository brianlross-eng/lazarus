try:
    from setuptools.command.install import INSTALL_SCHEMES
except ImportError:
    INSTALL_SCHEMES = {}
INSTALL_SCHEMES['unix_prefix']['data'] = '/usr'
