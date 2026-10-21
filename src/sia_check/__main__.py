"""python -m sia_check … ; point d'entrée de l'exécutable embarqué (PyInstaller)."""

import sys

from sia_check.cli import main

sys.exit(main())
