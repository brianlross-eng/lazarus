import subprocess, sys
def main(args): subprocess.check_call([sys.executable, "-m", "pip"] + list(args))
main(['install', 'foo'])
