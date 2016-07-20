
import argparse
import fcntl
import logging
import os
import select
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


def main_loop(args):
    cmd = [args.cmd] + args.args

    processes = {}

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((args.address, args.port))
            s.listen(args.backlog)
            epoll = select.epoll()
            set_nonblock(s.fileno())
            epoll.register(s.fileno(), select.EPOLLIN)
            accepting = True
            while True:
                for fd, event in epoll.poll(-1):
                    if fd == s.fileno():
                        if not accepting:
                            continue
                        conn, addr = s.accept()
                        proc = subprocess.Popen(cmd,
                            stdin=conn.fileno(), stdout=conn.fileno(),
                            stderr=subprocess.PIPE)
                        set_nonblock(proc.stderr.fileno())
                        # we use stderr EPOLLHUP to detect process exit
                        epoll.register(proc.stderr.fileno(), select.EPOLLIN|select.EPOLLHUP)
                        processes[proc.stderr.fileno()] = (proc, conn)
                        if len(processes) == args.processes:
                            accepting = False
                            epoll.unregister(fd)

                    elif fd in processes:
                        proc, conn = processes[fd]
                        while True:
                            stderr = proc.stderr.read()
                            if stderr:
                                sys.stderr.buffer.write(stderr)
                            else:
                                break

                        sys.stderr.buffer.flush()

                        # NOTE: If I SIGSTOP a client rsync process, I see
                        # an EPOLLHUP here even though the server process
                        # is still running. So that's why we call proc.poll()
                        # here.
                        if event & select.EPOLLHUP and proc.poll() is not None:
                            proc.wait()
                            proc.stderr.close()
                            try:
                                conn.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                            conn.close()
                            del processes[fd]
                            if not accepting:
                                epoll.register(s.fileno(), select.EPOLLIN)
                                accepting = True

    finally:
        while processes:
            fd, (proc, conn) = processes.popitem()
            proc.terminate()
            proc.wait()
            proc.stderr.close()
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()


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
        '--processes',
        action='store',
        metavar='PROCESSES',
        type=int,
        default=1,
        help='maximum number of concurrent processes (default is 1)',
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

    main_loop(args)


if __name__ == '__main__':
    sys.exit(main())
