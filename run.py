# August 2020, Lewis Gaul

import sys

import cli.__main__ as cli


if __name__ == "__main__":
    sys.path.append("bootstrap")
    sys.exit(cli.main(sys.argv[1:]))
