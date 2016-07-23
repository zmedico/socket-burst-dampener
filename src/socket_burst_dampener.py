
import argparse
import asyncio
import fcntl
import functools
import logging
import os
import signal
import socket
import subprocess
import sys

__version__ = "HEAD"
__project__ = "socket-burst-dampener"
__description__ = "A daemon that spawns a specified command to handle each connection, and dampens connection bursts"
__author__ = "Zac Medico"
__email__ = "<zmedico@gmail.com>"
__copyright__ = "Copyright 2016 Zac Medico"
__license__ = "Apache-2.0"


def set_nonblock(fd):
    fcntl.fcntl(fd, fcntl.F_SETFL,
        fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)


class Daemon:
    def __init__(self, args, loop):
        self._args = args
        self._loop = loop
        self._processes = {}
        self._accepting = False
        self._socket = None
        self._sigchld_handler = functools.partial(
            loop.call_soon_threadsafe, self._reap_children)

    def _acceptable_load(self):
        return (self._args.load_average is None or
            not self._processes or
            os.getloadavg()[0] < self._args.load_average)

    def _start_accepting(self):
        self._accepting = True
        self._loop.add_reader(self._socket.fileno(),
            self._socket_read_handler)

    def _stop_accepting(self):
        if self._accepting:
            self._accepting = False
            self._loop.remove_reader(self._socket.fileno())

    def _reap_children(self):
        while True:
            try:
                pid = os.wait3(os.WNOHANG)[0]
            except ChildProcessError:
                break

            if pid == 0:
                break

            proc, conn = self._processes.pop(pid)
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

            if not self._accepting and self._acceptable_load():
                self._start_accepting()

    def _socket_read_handler(self):
        if self._accepting:
            if self._acceptable_load():
                conn, addr = self._socket.accept()
                proc = subprocess.Popen([self._args.cmd] + self._args.args,
                    stdin=conn.fileno(), stdout=conn.fileno())
                self._processes[proc.pid] = (proc, conn)
                if len(self._processes) == self._args.processes:
                    self._stop_accepting()
            else:
                self._stop_accepting()

    def __enter__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self._args.address, self._args.port))
        self._socket.listen(self._args.backlog)
        set_nonblock(self._socket.fileno())
        self._loop.add_signal_handler(signal.SIGCHLD, self._sigchld_handler)
        self._start_accepting()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._stop_accepting()
        self._socket.close()
        self._loop.remove_signal_handler(signal.SIGCHLD)

        while self._processes:
            pid, (proc, conn) = self._processes.popitem()
            proc.terminate()
            proc.wait()
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

        return False


def main():

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="  {} {}\n  {}".format(
        __project__, __version__, __description__))

    parser.add_argument(
        'port',
        action='store',
        metavar='PORT',
        type=int,
        help='listen on the given port number',
    )

    parser.add_argument(
        '--address',
        action='store',
        metavar='ADDRESS',
        default='',
        help='bind to the specified address',
    )

    parser.add_argument(
        '--backlog',
        action='store',
        metavar='BACKLOG',
        type=int,
        default=socket.SOMAXCONN,
        help=('maximum number of queued connections '
            '(default from net.core.somaxconn '
            'sysctl is {})'.format(socket.SOMAXCONN)),
    )

    parser.add_argument(
        '--load-average',
        action='store',
        metavar='LOAD',
        type=float,
        default=None,
        help='don\'t accept multiple connections unless load is below LOAD',
    )

    parser.add_argument(
        '--processes',
        action='store',
        metavar='PROCESSES',
        type=int,
        default=1,
        help='maximum number of concurrent processes (0 means infinite, default is 1)',
    )

    parser.add_argument(
        '-v', '--verbose',
        dest='verbosity',
        action='count',
        help='verbose logging (each occurence increases verbosity)',
        default=0,
    )

    parser.add_argument(
        'cmd',
        metavar='CMD',
        help='command to spawn to handle each connection',
    )

    parser.add_argument(
        'args',
        nargs='*',
        metavar='ARG',
        help='argument(s) for CMD',
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=(logging.getLogger().getEffectiveLevel() - 10 * args.verbosity),
        format='[%(levelname)-4s] %(message)s',
    )

    logging.debug('args: %s', args)

    loop = asyncio.get_event_loop()

    try:
        with Daemon(args, loop):
            loop.run_forever()
    except KeyboardInterrupt:
        loop.stop()
    finally:
        loop.close()

if __name__ == '__main__':
    sys.exit(main())
