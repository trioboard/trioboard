"""Command-line entry point. The real implementation is being ported from the author's daily setup;
this placeholder only reports the version so that packaging can be tested."""
import sys
from . import __version__


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["--version"], ["-V"]):
        print(f"trioboard {__version__}")
        return 0
    print("trioboard is in the workshop. Commands (init, status, send, ack, reserve, check) arrive with the first release.")
    print("https://trioboard.com")
    return 0


if __name__ == "__main__":
    sys.exit(main())
