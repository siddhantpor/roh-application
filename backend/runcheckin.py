"""Compatibility entry point; runs the integrated application from app.py."""
import sys
from app import create_app

if __name__ == '__main__':
    create_app().run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 5001)
