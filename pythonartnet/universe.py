from pythonartnet import packet


class ArtnetUniverse:
    def __init__(self, universe_number):
        self.buffer = bytearray(packet.PACKET_SIZE)

        self._universe_number = universe_number
        self._packet_maker = packet.DmxPacketMaker(self._universe_number)

    def make_packet(self) -> bytearray:
        return self._packet_maker.make_dmx_packet(self.buffer)
