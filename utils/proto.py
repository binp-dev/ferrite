import re

_REDEF = re.compile("^#define\s+(\S+)\s+(.*)$")
_RECOM = [re.compile("/\*.*\*/"), re.compile("//.*$")]

def _remove_comments(line):
    for rec in _RECOM:
        line = re.sub(rec, "", line)
    return line

def read_definitions(path):
    pairs = {}
    for l in open(path, "r"):
        l = l.strip()
        m = re.search(_REDEF, l)

        if m is not None:
            v = _remove_comments(m.group(2)).strip()
            try:
                v = int(v, 0)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass

            pairs[m.group(1)] = v

    return pairs
