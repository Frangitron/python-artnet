
PACKET_SIZE: int = 512


def _shift(number, high_first=True):
    """Utility method: extracts MSB and LSB from number.

    Args:
    number - number to shift
    high_first - MSB or LSB first (true / false)

    Returns:
    (high, low) - tuple with shifted values

    """
    low = (number & 0xFF)
    high = ((number >> 8) & 0xFF)
    if high_first:
        return high, low

    return low, high


def _make_artsync_packet() -> bytearray:
    """Make ArtSync header"""
    artsync_header = bytearray()  # Initialize as empty bytearray
    # ID: Array of 8 characters, the final character is a null termination.
    artsync_header.extend(bytearray('Art-Net', 'utf8'))
    artsync_header.append(0x0)
    # OpCode: Defines the class of data within this UDP packet. Transmitted low byte first.
    artsync_header.append(0x00)
    artsync_header.append(0x52)
    # ProtVerHi and ProtVerLo: Art-Net protocol revision number. Current value =14.
    # Controllers should ignore communication with nodes using a protocol version lower than =14.
    artsync_header.append(0x0)
    artsync_header.append(14)
    # Aux1 and Aux2: Should be transmitted as zero.
    artsync_header.append(0x0)
    artsync_header.append(0x0)
    return artsync_header


class DmxPacketMaker:

    def __init__(self, universe_number: int, subnet: int = 0, net: int = 0):
        self._universe_number: int = universe_number
        self._subnet: int = subnet
        self._net: int = net

        self._sequence: int = 0

    def make_dmx_packet(self, buffer: bytearray) -> bytearray:
        packet = bytearray()
        packet.extend(self._make_dmx_header())
        packet.extend(buffer)
        return packet

    def _make_dmx_header(self) -> bytearray:
        """
        Make a packet header. (Borrowed from StupidArtnet)
        """
        # 0 - id (7 x bytes + Null)
        packet_header = bytearray()
        packet_header.extend(bytearray('Art-Net', 'utf8'))
        packet_header.append(0x0)
        # 8 - opcode (2 x 8 low byte first)
        packet_header.append(0x00)
        packet_header.append(0x50)  # ArtDmx data packet
        # 10 - prototocol version (2 x 8 high byte first)
        packet_header.append(0x0)
        packet_header.append(14)
        # 12 - sequence (int 8), NULL for not implemented
        packet_header.append(self._sequence)
        # 13 - physical port (int 8)
        packet_header.append(0x00)
        # 14 - universe, (2 x 8 low byte first)
        packet_header.append(self._subnet << 4 | self._universe_number)
        packet_header.append(self._net & 0xFF)

        # 16 - packet size (2 x 8 high byte first)
        msb, lsb = _shift(PACKET_SIZE)		# convert to MSB / LSB
        packet_header.append(msb)
        packet_header.append(lsb)

        return packet_header


ARTSYNC_PACKET: bytearray = _make_artsync_packet()
ARTDMX_HEADER: bytearray = bytearray(b'Art-Net\x00\x00P\x00\x0e')  # FIXME do better ?
