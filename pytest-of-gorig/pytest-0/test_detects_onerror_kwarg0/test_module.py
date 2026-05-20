import shutil
shutil.rmtree("/tmp/foo", onerror=lambda *a: None)
