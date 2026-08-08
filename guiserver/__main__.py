import argparse
import os
import sys

from .server import run


def main():
    parser = argparse.ArgumentParser(
        description="Serve the current directory (or --directory) with a GUI file browser, "
                    "just like `python -m http.server` but with a nicer index page."
    )
    parser.add_argument("port", nargs="?", default=8000, type=int,
                         help="Port to listen on (default: 8000)")
    parser.add_argument("--bind", "-b", default="", metavar="ADDRESS",
                         help="Address to bind to (default: all interfaces)")
    parser.add_argument("--directory", "-d", default=os.getcwd(), metavar="DIR",
                         help="Directory to serve (default: current directory)")
    parser.add_argument("--upload", action="store_true",
                        help="Enable file uploads to the served directory")
    args = parser.parse_args()

    try:
        run(port=args.port, bind=args.bind, directory=args.directory, allow_uploads=args.upload)
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
