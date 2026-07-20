"""Console entry point: `andp <command>` maps to the ASC manager commands."""
import sys

from .asc.asc_manager import main as asc_main


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    return asc_main(argv)


if __name__ == "__main__":
    sys.exit(main())
