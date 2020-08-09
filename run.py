# August 2020, Lewis Gaul

import sys


if __name__ == "__main__":
    sys.path.append("bootstrap")
    import cli.__main__ as cli

    sys.exit(cli.main(sys.argv[1:]))
