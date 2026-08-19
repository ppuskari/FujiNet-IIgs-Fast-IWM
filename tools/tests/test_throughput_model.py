from tools.throughput_model import Model


def test_four_us_packet_time():
    m = Model(cell_us=4.0)
    assert abs(m.data_packet_ms - 19.328) < 0.001


def test_two_us_packet_time():
    m = Model(cell_us=2.0)
    assert abs(m.data_packet_ms - 9.664) < 0.001


def test_fast_mode_doubles_packet_only_payload():
    normal = Model(cell_us=4.0)
    fast = Model(cell_us=2.0)
    assert abs(fast.payload_bytes_per_s / normal.payload_bytes_per_s - 2.0) < 1e-9
