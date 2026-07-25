import socket
from collections.abc import Callable
from dataclasses import dataclass

from pythonartnet import packet


@dataclass(frozen=True)
class ArtnetDmxFrame:
    universe: int
    sequence: int
    physical: int
    data: bytearray
    sender_ip: str
    sender_port: int


class ArtnetReceiveError(OSError):
    pass


class ArtnetReceiver:
    UDP_PORT = 6454

    ARTNET_ID = b"Art-Net\x00"
    ARTDMX_OPCODE = 0x5000

    def __init__(
        self,
        bind_address: str = "0.0.0.0",
        port: int = UDP_PORT,
        timeout: float | None = 1.0,
    ):
        self.bind_address = bind_address
        self.port = port
        self.on_dmx: Callable[[ArtnetDmxFrame], None] | None = None

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.bind_address, self.port))
        self._socket.settimeout(timeout)

        self._running = False

    def close(self):
        self._running = False
        self._socket.close()

    def receive_once(self) -> ArtnetDmxFrame | None:
        try:
            raw_packet, address = self._socket.recvfrom(1024)
        except TimeoutError:
            return None
        except OSError as error:
            raise ArtnetReceiveError(str(error)) from error

        frame = self._parse_packet(raw_packet, address)

        if frame is not None and self.on_dmx is not None:
            self.on_dmx(frame)

        return frame

    def receive_forever(self):
        self._running = True

        while self._running:
            self.receive_once()

    def stop(self):
        self._running = False

    def _parse_packet(
        self,
        raw_packet: bytes,
        address: tuple[str, int],
    ) -> ArtnetDmxFrame | None:
        if len(raw_packet) < 18:
            return None

        if raw_packet[:8] != self.ARTNET_ID:
            return None

        opcode = int.from_bytes(raw_packet[8:10], byteorder="little")
        if opcode != self.ARTDMX_OPCODE:
            return None

        sequence = raw_packet[12]
        physical = raw_packet[13]

        universe_low = raw_packet[14]
        universe_high = raw_packet[15]
        universe = universe_low | universe_high << 8

        length = int.from_bytes(raw_packet[16:18], byteorder="big")
        data = bytearray(raw_packet[18:18 + length])

        if len(data) != length:
            return None

        return ArtnetDmxFrame(
            universe=universe,
            sequence=sequence,
            physical=physical,
            data=data,
            sender_ip=address[0],
            sender_port=address[1],
        )
