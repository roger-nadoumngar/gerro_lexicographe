"""Lanceur de Gerro Lexicographe : `python app.py` (équivaut à `python -m lexicographe`)."""

import sys

from lexicographe.ui.application import main

if __name__ == "__main__":
    sys.exit(main())
