import asyncio
import unittest

from socket_burst_dampener import Daemon, parse_args


class SocketBurstDampenerTest(unittest.TestCase):
    def test_socket_burst_dampener(self):
        args = parse_args(
            [
                "socket-burst-dampener",
                "0",
                "--processes",
                "0",
                "--load-average",
                "1",
                "--",
                "echo",
                "hello",
            ]
        )
        loop = asyncio.get_event_loop()

        try:
            with Daemon(args, loop) as daemon:
                loop.run_until_complete(self._test_daemon(loop, daemon))
        except KeyboardInterrupt:
            loop.stop()
        finally:
            loop.close()

    async def _test_daemon(self, loop, daemon):
        while daemon.addr_info is None:
            await asyncio.sleep(0.1)

        for i in range(3):
            reader, writer = await asyncio.open_connection(
                family=daemon.addr_info.family,
                host=daemon.addr_info.address[0],
                port=daemon.addr_info.address[1],
            )
            data = b""
            expect = b"hello\n"
            while len(data) < len(expect):
                data += await reader.read(len(expect))
            self.assertEqual(data, expect)
            writer.close()
            await writer.wait_closed()
