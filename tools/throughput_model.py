#!/usr/bin/env python3
"""Small transport-budget model for the FujiNet IIgs Fast-IWM experiments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    cell_us: float
    encoded_bytes: int = 604
    payload_bytes: int = 512

    @property
    def encoded_byte_us(self) -> float:
        return self.cell_us * 8.0

    @property
    def data_packet_ms(self) -> float:
        return self.encoded_bytes * self.encoded_byte_us / 1000.0

    @property
    def payload_bytes_per_s(self) -> float:
        return self.payload_bytes / (self.data_packet_ms / 1000.0)

    @property
    def payload_bits_per_s(self) -> float:
        return self.payload_bytes_per_s * 8.0


def print_model(model: Model) -> None:
    print(f"cell:                 {model.cell_us:.3f} us")
    print(f"encoded bytes/block:  {model.encoded_bytes}")
    print(f"payload bytes/block:  {model.payload_bytes}")
    print(f"data packet time:      {model.data_packet_ms:.3f} ms")
    print(f"ideal payload:         {model.payload_bytes_per_s:,.1f} B/s")
    print(f"ideal payload:         {model.payload_bits_per_s/1000:,.1f} kbit/s")


def main() -> None:
    mono = 22050
    stereo = 44100

    for cell in (4.0, 2.0):
        model = Model(cell_us=cell)
        print_model(model)
        print(f"22.05K mono ratio:     {model.payload_bytes_per_s/mono:.3f}x")
        print(f"22.05K stereo ratio:   {model.payload_bytes_per_s/stereo:.3f}x")
        print()

    print("NOTE: data-packet-only idealization; command/handshake/software")
    print("overheads must be measured on hardware and will reduce payload rate.")


if __name__ == "__main__":
    main()
