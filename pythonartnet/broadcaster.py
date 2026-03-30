import socket

from pythonartnet import packet
from pythonartnet.universe import ArtnetUniverse


class ArtnetBroadcastError(OSError):
    pass


class ArtnetBroadcaster:
    UDP_PORT = 6454

    def __init__(self, target_ip: str, bind_address: str | None = None):
        self.target_ip = target_ip
        self.universes: dict[int, ArtnetUniverse] = dict()

        self._bind_address = bind_address
        self._socket = None
        self.reset_connection()

    def close(self):
        """Close the socket and clean up resources."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def reset_connection(self):
        self.close()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if self._bind_address is not None:
            self._socket.bind((self._bind_address, 0))
        self._socket.settimeout(1)  # todo check if OK

    def clear(self):
        self.universes.clear()

    def add_universe(self, universe_number: int):
        if universe_number in self.universes:
            raise ValueError(f"Universe {universe_number} already exists")

        self.universes[universe_number] = ArtnetUniverse(universe_number)

    def send_data(self):
        for universe in self.universes.values():
            packet = universe.make_packet()
            self._socket.sendto(packet, (self.target_ip, self.UDP_PORT))

    def send_artsync(self):
        self._socket.sendto(packet.ARTSYNC_PACKET, (self.target_ip, self.UDP_PORT))

    def send_data_synced(self):
        self.send_data()
        self.send_artsync()

    def __del__(self):
        """Ensure socket is closed when object is garbage collected."""
        self.close()
