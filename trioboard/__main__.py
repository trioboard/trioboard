"""`python -m trioboard` behaves like the `trio` command."""
import sys

from .cli import main

sys.exit(main())
