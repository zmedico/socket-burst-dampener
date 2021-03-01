
import os
import subprocess
import sys

from setuptools import (
    Command,
    setup,
)

sys.path.insert(0, "src")
from socket_burst_dampener import (
    __author__,
    __description__,
    __email__,
    __project__,
    __version__,
)
sys.path.remove("src")


class PyTest(Command):
    user_options = [
        ("match=", "k", "Run only tests that match the provided expressions")
    ]

    def initialize_options(self):
        self.match = None

    def finalize_options(self):
        pass

    def run(self):
        testpath = "./test"
        os.environ["EPYTHON"] = "python{}.{}".format(
            sys.version_info.major, sys.version_info.minor
        )
        pythonpath = list(filter(None, os.environ.get("PYTHONPATH", "").split(":")))
        pythonpath.insert(0, os.path.join(os.path.abspath(os.path.dirname(testpath)), "src"))
        os.environ["PYTHONPATH"] = ":".join(pythonpath)
        pytest_cmd = (
            ["py.test", "-v", testpath, "--cov-report=xml", "--cov-report=term-missing"]
            + (["-k", self.match] if self.match else [])
            + ["--cov=socket_burst_dampener"]
        )
        subprocess.check_call(pytest_cmd)


setup(
    name=__project__,
    version=__version__,
    description=__description__,
    author=__author__,
    author_email=__email__,
    cmdclass={'test': PyTest},
    package_dir={'': 'src'},
    py_modules=['socket_burst_dampener'],
    entry_points={
        'console_scripts': 'socket-burst-dampener = socket_burst_dampener:main',
    },
    python_requires = ">=3.6",
)
