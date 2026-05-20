from importlib.resources import files as _pkg_files
path = str(_pkg_files("mypackage").joinpath("data/file.txt"))
