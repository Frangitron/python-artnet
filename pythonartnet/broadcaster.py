import socket

from pythonartnet import packet
from pythonartnet.universe import ArtnetUniverse


class ArtnetBroadcastError(OSError):
    pass


class ArtnetBroadcaster:
    UDP_PORT = 6454

    def __init__(self, target_ip):
        self.target_ip = target_ip
        self.universes: dict[int, ArtnetUniverse] = dict()

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._socket.settimeout(1)  # todo check if OK

        print(f"Artnet broadcaster created, target ip {target_ip}")

    def add_universe(self, universe_number: int):
        if universe_number in self.universes:
            raise ValueError(f"Universe {universe_number} already exists")

        self.universes[universe_number] = ArtnetUniverse(universe_number)

    def send_data(self):
        try:
            for universe in self.universes.values():
                packet_ = universe.make_packet()
                self._socket.sendto(packet_, (self.target_ip, self.UDP_PORT))
        except OSError:
            raise ArtnetBroadcastError(f"Failed to Artnet send data to {self.target_ip}")

    def send_artsync(self):
        self._socket.sendto(packet.ARTSYNC_PACKET, (self.target_ip, self.UDP_PORT))

    def send_data_synced(self):
        self.send_data()
        self.send_artsync()
