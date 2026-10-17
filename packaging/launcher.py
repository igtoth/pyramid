"""Entry point the desktop builds compile (Nuitka): the same as `pyramid`."""

import sys

from pyramid.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
