import pathlib
import sys
import copy
import types


class CheckImport:
    def find_spec(self, fullname, path, target=None):
        if fullname in ('cablewatch', 'cablewatch.config'):
            return None
        elif fullname.startswith('cablewatch.'):
            raise ImportError(f"{fullname!r} module not available")
        else:
            return None

try:
    import cablewatch
except ImportError:
    SRC_DIR=str(pathlib.Path(__file__).parent.parent.parent)
    sys.path.append(SRC_DIR)
    sys.meta_path.insert(0, CheckImport())
