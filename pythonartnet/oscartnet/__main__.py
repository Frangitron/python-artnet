import json
import select
import socket
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pythonartnet.broadcaster import ArtnetBroadcaster

DEFAULT_CONFIG_FILE = Path(__file__).with_name("config.json")
ARTNET_SEND_FPS = 40.0
ARTNET_SEND_INTERVAL = 1.0 / ARTNET_SEND_FPS


@dataclass(frozen=True)
class OscMapping:
    universe: int
    address: int

    @property
    def buffer_index(self) -> int:
        return self.address - 1


@dataclass(frozen=True)
class AppConfig:
    artnet_listen_ip: str
    artnet_target_ip: str
    artnet_port: int
    osc_listen_ip: str
    osc_listen_port: int
    osc_mapping: dict[str, OscMapping]


class OscParseError(ValueError):
    pass


def main():
    config_file = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    config = load_config(config_file)
    mapping = config.osc_mapping

    artnet_receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    artnet_receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    artnet_receive_socket.bind((config.artnet_listen_ip, config.artnet_port))
    artnet_receive_socket.setblocking(False)

    artnet_forward_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    artnet_forward_target = (config.artnet_target_ip, config.artnet_port)

    osc_receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    osc_receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    osc_receive_socket.bind((config.osc_listen_ip, config.osc_listen_port))
    osc_receive_socket.setblocking(False)

    osc_artnet = ArtnetBroadcaster(config.artnet_listen_ip)
    for universe in sorted({entry.universe for entry in mapping.values()}):
        osc_artnet.add_universe(universe)

    sockets = [artnet_receive_socket, osc_receive_socket]

    print(
        f"Forwarding Art-Net from "
        f"{config.artnet_listen_ip}:{config.artnet_port} "
        f"to {config.artnet_target_ip}:{config.artnet_port}"
    )
    print(f"Listening for OSC on {config.osc_listen_ip}:{config.osc_listen_port}")
    print(f"Sending OSC-generated Art-Net to forwarder at {config.artnet_listen_ip}:{config.artnet_port}")
    print(f"Loaded {len(mapping)} OSC mapping(s) from {config_file}")
    print(f"Continuously sending OSC-generated Art-Net at {ARTNET_SEND_FPS:g} FPS")

    next_artnet_send = time.monotonic()

    while True:
        now = time.monotonic()
        timeout = max(0.0, next_artnet_send - now)

        readable_sockets, _, _ = select.select(sockets, [], [], timeout)

        for readable_socket in readable_sockets:
            if readable_socket is artnet_receive_socket:
                forward_pending_artnet_packets(
                    artnet_receive_socket,
                    artnet_forward_socket,
                    artnet_forward_target,
                )

            elif readable_socket is osc_receive_socket:
                handle_pending_osc_packets(osc_receive_socket, osc_artnet, mapping)

        now = time.monotonic()
        if now >= next_artnet_send:
            osc_artnet.send_data_synced()
            next_artnet_send += ARTNET_SEND_INTERVAL

            if next_artnet_send <= now:
                next_artnet_send = now + ARTNET_SEND_INTERVAL


def forward_pending_artnet_packets(
    receive_socket: socket.socket,
    send_socket: socket.socket,
    target: tuple[str, int],
):
    while True:
        try:
            packet, _sender = receive_socket.recvfrom(1024)
        except BlockingIOError:
            return

        send_socket.sendto(packet, target)


def handle_pending_osc_packets(
    receive_socket: socket.socket,
    artnet: ArtnetBroadcaster,
    mapping: dict[str, OscMapping],
):
    while True:
        try:
            packet, sender = receive_socket.recvfrom(4096)
        except BlockingIOError:
            return

        handle_osc_packet(packet, sender, artnet, mapping)


def handle_osc_packet(
    packet: bytes,
    sender: tuple[str, int],
    artnet: ArtnetBroadcaster,
    mapping: dict[str, OscMapping],
):
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


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as file:
        raw_config = json.load(file)

    artnet_config = raw_config["artnet"]
    osc_config = raw_config["osc"]

    artnet_port = int(artnet_config["port"])
    osc_listen_port = int(osc_config["listen_port"])

    if not 1 <= artnet_port <= 65535:
        raise ValueError("Art-Net port must be between 1 and 65535")

    if not 1 <= osc_listen_port <= 65535:
        raise ValueError("OSC listen port must be between 1 and 65535")

    return AppConfig(
        artnet_listen_ip=str(artnet_config["listen_ip"]),
        artnet_target_ip=str(artnet_config["target_ip"]),
        artnet_port=artnet_port,
        osc_listen_ip=str(osc_config["listen_ip"]),
        osc_listen_port=osc_listen_port,
        osc_mapping=load_mapping(osc_config["mapping"]),
    )


def load_mapping(raw_mapping: dict[str, Any]) -> dict[str, OscMapping]:
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