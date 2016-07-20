# socket-burst-dampener

A daemon that spawns a specified command to handle each connection, and
dampens connection bursts.

## Motivation
It is typical to configure a forking daemon such as rsync so that it
will respond with an error when a maximum number of concurrent
connections has been exceeded. Alternatively, it may be desirable to
queue excess connections, and service them in the order of arrival
while taking care to ensure that too many processes are not spawned at
once. The socket-burst-dampener daemon applies this behavior to any
daemon command that works with inetd.

## Usage
```
usage: socket-burst-dampener [-h] [--address ADDRESS] [--backlog BACKLOG]
                             [--processes PROCESSES] [-v]
                             PORT CMD [ARG [ARG ...]]

  socket-burst-dampener
  A daemon that spawns a specified command to handle each connection, and dampens connection bursts

positional arguments:
  PORT                  listen on the given port number
  CMD                   command to spawn to handle each connection
  ARG                   argument(s) for CMD

optional arguments:
  -h, --help            show this help message and exit
  --address ADDRESS     bind to the specified address
  --backlog BACKLOG     maximum number of queued connections (default from
                        net.core.somaxconn sysctl is 128)
  --processes PROCESSES
                        maximum number of concurrent processes (default is 1)
  -v, --verbose         verbose logging (each occurence increases verbosity)
```
## Example with rsync
```
socket-burst-dampener 873 --processes $(nproc) -- rsync --daemon
```
