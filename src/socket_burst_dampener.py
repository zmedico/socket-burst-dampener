
import argparse
import asyncio
import functools
import logging
import os
import signal
import socket
import subprocess
import sys
import types

__version__ = "HEAD"
__project__ = "socket-burst-dampener"
__description__ = "A daemon that spawns a specified command to handle each connection, and dampens connection bursts"
__author__ = "Zac Medico"
__email__ = "<zmedico@gmail.com>"
__copyright__ = "Copyright 2016 Zac Medico"
__license__ = "Apache-2.0"


class Daemon:
    def __init__(self, args, loop):
        self._args = args
        self._loop = loop
        self._processes = {}
        self._accepting = False
        self._sockets = None
        self._addr_info = None
        self._child_handler_threadsafe = functools.partial(
            loop.call_soon_threadsafe, self._child_handler)

    def _acceptable_load(self):
        return (self._args.load_average is None or
            not self._processes or
            os.getloadavg()[0] < self._args.load_average)

    def _start_accepting(self):
        self._accepting = True
        for sock in self._sockets:
            self._loop.add_reader(sock.fileno(),
                functools.partial(self._socket_read_handler, sock))

    def _stop_accepting(self):
        if self._accepting:
            self._accepting = False
            for sock in self._sockets:
                self._loop.remove_reader(sock.fileno())

    def _child_handler(self, pid, status):
        proc = self._processes.pop(pid)

        # Suppress warning messages like this:
        # ResourceWarning: subprocess 1234 is still running
        proc.returncode = status

        if not self._accepting and self._acceptable_load():
            self._start_accepting()

    def _socket_read_handler(self, sock):
        if self._accepting:
            if self._acceptable_load():
                try:
                    conn, addr = sock.accept()
                except Exception as e:
                    logging.debug('socket.accept: %s', e)
                else:
                    proc = subprocess.Popen([self._args.cmd] + self._args.args,
                        stdin=conn.fileno(), stdout=conn.fileno())
                    # Close the socket immediately, in order to conserve file
                    # descriptors (the subprocess holds a duplicate).
                    conn.close()
                    self._processes[proc.pid] = proc
                    asyncio.get_child_watcher().add_child_handler(
                        proc.pid, self._child_handler_threadsafe
                    )
                    if len(self._processes) == self._args.processes:
                        self._stop_accepting()
            else:
                self._stop_accepting()

    def _init_sockets(self):
        self._sockets = sockets = []

        af_hint = 0
        if self._args.ipv4 and self._args.ipv6:
            pass
        elif self._args.ipv6 and socket.has_ipv6:
            af_hint = socket.AF_INET6
        elif self._args.ipv4:
            af_hint = socket.AF_INET

        addresses = []

        for addrinfo in socket.getaddrinfo(
            self._args.address, self._args.port,
            family=af_hint, type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP, flags=socket.AI_PASSIVE):

            # Validate structures returned from getaddrinfo(),
            # since they may be corrupt (especially if python
            # has IPv6 support disabled).
            if len(addrinfo) != 5:
                continue
            family, sock_type, proto, canonname, sockaddr = addrinfo
            if len(sockaddr) < 2:
                continue
            if not isinstance(sockaddr[0], str):
                continue

            addresses.append(addrinfo)

        # On Linux, if dual-stack support is enabled then we want to
        # use the IPv6 address for IPv4 as well, since attempting to
        # listen on both addresses separately results in EADDRINUSE.
        if len(addresses) > 1 and socket.has_ipv6:
            try:
                with open('/proc/sys/net/ipv6/bindv6only', 'rb') as f:
                    ipv6_bindv6only = b'0' not in f.readline()
            except EnvironmentError:
                ipv6_bindv6only = True

            if not ipv6_bindv6only:
                filtered_addresses = [addrinfo for addrinfo in addresses
                    if addrinfo[0] == socket.AF_INET6]
                if filtered_addresses:
                    addresses = filtered_addresses

        for family, sock_type, proto, canonname, sockaddr in addresses:

            sock = None
            try:
                logging.debug('family=%s type=%s proto=%s addr=%s',
                    family, sock_type, proto, sockaddr)
                sock = socket.socket(
                    family=family, type=sock_type|getattr(socket, 'SOCK_NONBLOCK', 0), proto=proto)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # Disable dual-stack support if the user requested
                # IPv6 and not IPv4.
                if (hasattr(socket, 'AF_INET6') and
                    hasattr(socket, 'IPV6_V6ONLY') and
                    family == socket.AF_INET6 and
                    self._args.ipv6 and not self._args.ipv4):
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)

                sock.bind(sockaddr)
                self._addr_info = types.SimpleNamespace(
                    address=sock.getsockname(),
                    family=family,
                    proto=proto,
                    sock_type=sock_type,
                )
                sock.listen(self._args.backlog)
            except Exception as e:
                logging.exception(e)
                if sock is not None:
                    sock.close()
                continue
            sockets.append(sock)

        if not sockets:
            raise AssertionError('could not bind socket(s)')

    @property
    def addr_info(self):
        return self._addr_info

    def __enter__(self):
        self._init_sockets()
        self._start_accepting()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self._stop_accepting()
        while self._sockets:
            self._sockets.pop().close()

        while self._processes:
            pid, proc = self._processes.popitem()
            proc.terminate()
            proc.wait()

        return False


def parse_args(argv=None):
    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(
        prog=os.path.basename(argv[0]),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="  {} {}\n  {}".format(
        __project__, __version__, __description__))

    try:
        with open('/proc/sys/net/core/somaxconn', 'rt') as f:
            max_backlog = int(f.readline().strip())
    except Exception:
        max_backlog = socket.SOMAXCONN

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
        default=None,
        help='bind to the specified address',
    )

    parser.add_argument(
        '--backlog',
        action='store',
        metavar='BACKLOG',
        default=None,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        '--ipv4',
        action='store_true',
        default=None,
        help='prefer IPv4',
    )

    parser.add_argument(
        '--ipv6',
        action='store_true',
        default=None,
        help='prefer IPv6',
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

    args = parser.parse_args(argv[1:])

    logging.basicConfig(
        level=(logging.getLogger().getEffectiveLevel() - 10 * args.verbosity),
        format='[%(levelname)-4s] %(message)s',
    )

    logging.debug('args: %s', args)

    if args.ipv6 and not socket.has_ipv6:
        logging.warning('the platform has IPv6 support disabled')

    if args.backlog is not None:
        logging.warning('the --backlog option is deprecated and ignored')
    args.backlog = max_backlog
    return args


def sigterm_handler(loop, task, signum, _frame):
    loop.call_soon_threadsafe(task.cancel)
    signal.signal(signal.SIGINT, signal.SIG_IGN)


async def main():
    args = parse_args()
    loop = asyncio.get_running_loop()
    task = loop.create_future()

    signal.signal(signal.SIGINT, functools.partial(sigterm_handler, loop, task))
    with Daemon(args, loop):
        try:
            await task
        except asyncio.CancelledError:
            print("interrupted.", file=sys.stderr)


def main_entry_point():
    asyncio.run(main())


if __name__ == "__main__":
    main_entry_point()
