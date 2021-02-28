
import sys

from setuptools import setup

sys.path.insert(0, "src")
from socket_burst_dampener import (
    __author__,
    __description__,
    __email__,
    __project__,
    __version__,
)
sys.path.remove("src")

setup(
    name=__project__,
    version=__version__,
    description=__description__,
    author=__author__,
    author_email=__email__,
    package_dir={'': 'src'},
    py_modules=['socket_burst_dampener'],
    entry_points={
        'console_scripts': 'socket-burst-dampener = socket_burst_dampener:main',
    },
    python_requires = ">=3.6",
)
