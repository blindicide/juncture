import sys

from juncture.cli import main

raise SystemExit(main(["analyze", "--run-dir", sys.argv[1]]))
