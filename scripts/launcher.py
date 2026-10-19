"""Entry point for the PyInstaller executable.

PyInstaller runs a script as __main__, which breaks the package's relative
imports, so the executable starts from here instead of from the package.
"""

import multiprocessing

from laminectomy.__main__ import main

if __name__ == "__main__":
    # Required in frozen executables: worker processes re-run this script,
    # and freeze_support() stops them from parsing the command line again.
    multiprocessing.freeze_support()
    main()
