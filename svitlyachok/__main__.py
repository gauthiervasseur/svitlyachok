import multiprocessing
import sys

from svitlyachok.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # PyInstaller on Windows
    sys.exit(main())
