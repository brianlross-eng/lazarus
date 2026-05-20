def parse_requirements(filename, session=None, options=None):
    """Minimal shim replacing pip.req.parse_requirements."""
    import os
    class _Req:
        def __init__(self, line):
            self.requirement = line
            self.req = line
            self.name = line.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].split("!=")[0].split("[")[0].strip()
            self.comes_from = filename
        def __str__(self):
            return self.requirement
    reqs = []
    if os.path.exists(filename):
        with open(filename) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    reqs.append(_Req(line))
    return reqs

reqs = parse_requirements('requirements.txt')
