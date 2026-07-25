import json
import select
import socket
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pythonartnet.broadcaster import ArtnetBroadcaster

ARTNET_LISTEN_IP = "10.0.0.2"
ARTNET_TARGET_IP = "192.168.20.7"
ARTNET_PORT = 6454

OSC_LISTEN_IP = "0.0.0.0"
OSC_LISTEN_PORT = 8000

DEFAULT_MAPPING_FILE = Path(__file__).with_name("osc_mapping.json")


@dataclass(frozen=True)
class OscMapping:
    universe: int
    address: int

    @property
    def buffer_index(self) -> int:
        return self.address - 1


class OscParseError(ValueError):
    pass


def main():
    mapping_file = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAPPING_FILE
    mapping = load_mapping(mapping_file)

    artnet_receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    artnet_receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    artnet_receive_socket.bind((ARTNET_LISTEN_IP, ARTNET_PORT))

    artnet_forward_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    osc_receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    osc_receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    osc_receive_socket.bind((OSC_LISTEN_IP, OSC_LISTEN_PORT))

    osc_artnet = ArtnetBroadcaster(ARTNET_LISTEN_IP)
    for universe in sorted({entry.universe for entry in mapping.values()}):
        osc_artnet.add_universe(universe)

    sockets = [artnet_receive_socket, osc_receive_socket]

    print(f"Forwarding Art-Net from {ARTNET_LISTEN_IP}:{ARTNET_PORT} to {ARTNET_TARGET_IP}:{ARTNET_PORT}")
    print(f"Listening for OSC on {OSC_LISTEN_IP}:{OSC_LISTEN_PORT}")
    print(f"Sending OSC-generated Art-Net to forwarder at {ARTNET_LISTEN_IP}:{ARTNET_PORT}")
    print(f"Loaded {len(mapping)} OSC mapping(s) from {mapping_file}")

    while True:
        readable_sockets, _, _ = select.select(sockets, [], [])

        for readable_socket in readable_sockets:
            if readable_socket is artnet_receive_socket:
                forward_artnet_packet(artnet_receive_socket, artnet_forward_socket)

            elif readable_socket is osc_receive_socket:
                handle_osc_packet(osc_receive_socket, osc_artnet, mapping)


def forward_artnet_packet(receive_socket: socket.socket, send_socket: socket.socket):
    packet, _sender = receive_socket.recvfrom(1024)
    send_socket.sendto(packet, (ARTNET_TARGET_IP, ARTNET_PORT))


def handle_osc_packet(
    receive_socket: socket.socket,
    artnet: ArtnetBroadcaster,
    mapping: dict[str, OscMapping],
):
    packet, sender = receive_socket.recvfrom(4096)

    try:
        osc_address, values = parse_osc_message(packet)
    except OscParseError as error:
        print(f"Ignoring invalid OSC packet from {sender}: {error}")
        return

    if not values:
        return

    mapped_address = mapping.get(osc_address)
    if mapped_address is None:
        return

    value = osc_value_to_dmx(values[0])

    universe = artnet.universes[mapped_address.universe]
    universe.buffer[mapped_address.buffer_index] = value

    artnet.send_data_synced()


def load_mapping(path: Path) -> dict[str, OscMapping]:
    with path.open("r", encoding="utf-8") as file:
        raw_mapping = json.load(file)

    mapping: dict[str, OscMapping] = {}

    for osc_address, target in raw_mapping.items():
        universe = int(target["universe"])
        address = int(target["address"])

        if not osc_address.startswith("/"):
            raise ValueError(f"OSC address must start with '/': {osc_address}")

        if not 0 <= universe <= 32767:
            raise ValueError(f"Universe must be between 0 and 32767 for {osc_address}")

        if not 1 <= address <= 512:
            raise ValueError(f"DMX address must be between 1 and 512 for {osc_address}")

        mapping[osc_address] = OscMapping(universe=universe, address=address)

    return mapping


def parse_osc_message(packet: bytes) -> tuple[str, list[Any]]:
    offset = 0

    address, offset = read_osc_string(packet, offset)
    if not address.startswith("/"):
        raise OscParseError("OSC address is missing or invalid")

    type_tags, offset = read_osc_string(packet, offset)
    if not type_tags.startswith(","):
        raise OscParseError("OSC type tag string is missing or invalid")

    values: list[Any] = []

    for type_tag in type_tags[1:]:
        if type_tag == "i":
            require_size(packet, offset, 4)
            values.append(struct.unpack(">i", packet[offset:offset + 4])[0])
            offset += 4
        elif type_tag == "f":
            require_size(packet, offset, 4)
            values.append(struct.unpack(">f", packet[offset:offset + 4])[0])
            offset += 4
        elif type_tag == "s":
            value, offset = read_osc_string(packet, offset)
            values.append(value)
        elif type_tag == "T":
            values.append(True)
        elif type_tag == "F":
            values.append(False)
        else:
            raise OscParseError(f"Unsupported OSC type tag: {type_tag}")

    return address, values


def read_osc_string(packet: bytes, offset: int) -> tuple[str, int]:
    try:
        end = packet.index(0, offset)
    except ValueError as error:
        raise OscParseError("Unterminated OSC string") from error

    raw_value = packet[offset:end]
    value = raw_value.decode("utf-8")

    next_offset = align_osc_offset(end + 1)
    if next_offset > len(packet):
        raise OscParseError("OSC string padding exceeds packet size")

    return value, next_offset


def align_osc_offset(offset: int) -> int:
    remainder = offset % 4
    if remainder == 0:
        return offset

    return offset + 4 - remainder


def require_size(packet: bytes, offset: int, size: int):
    if offset + size > len(packet):
        raise OscParseError("OSC argument exceeds packet size")


def osc_value_to_dmx(value: Any) -> int:
    if isinstance(value, bool):
        return 255 if value else 0

    if isinstance(value, int):
        return clamp(value, 0, 255)

    if isinstance(value, float):
        return clamp(round(value * 255), 0, 255)

    raise OscParseError(f"Cannot convert OSC value to DMX: {value!r}")


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


if __name__ == "__main__":
    main()