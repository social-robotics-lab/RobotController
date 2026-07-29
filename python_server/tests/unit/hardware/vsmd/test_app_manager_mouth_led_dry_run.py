"""The mouth-LED integration dry-run cannot create live transports."""

import inspect
import socket

from robot_controller.hardware.vsmd import (
    app_manager_mouth_led_dry_run as module,
)


def test_dry_run_uses_real_controller_order_with_fake_ports_only(capsys):
    original_create_connection = socket.create_connection

    def fail_live_socket(*unused_args, **unused_kwargs):
        raise AssertionError("dry-run attempted a live socket")

    socket.create_connection = fail_live_socket
    try:
        status = module.main()
    finally:
        socket.create_connection = original_create_connection

    assert status == 0
    output = capsys.readouterr().out
    assert "led_id=14" in output
    assert "lock_acquired=true" in output
    assert "timer_address=502" in output
    assert "lock_released=true" in output
    assert "live_network=false" in output
    assert "live_write=false" in output
    assert "result=success" in output
    assert (
        "processing_order=LOCK>CONVERT>validate timer address>"
        "prepare VSMD LED operations>perform Fake VSMD operations>UNLOCK"
    ) in output


def test_dry_run_event_order_places_all_vsmd_access_inside_lock():
    result = module.execute_dry_run()
    assert result.events[0:2] == ("INTERP_LOCK", "INTERP_CNV_KEY_2_ADDR")
    assert result.events[-1] == "INTERP_UNLOCK"
    first_memory_event = next(
        index
        for index, event in enumerate(result.events)
        if isinstance(event, tuple)
    )
    assert first_memory_event > 1


def test_planned_operations_come_from_existing_controller(capsys):
    assert module.main() == 0
    output = capsys.readouterr().out
    planned = next(
        line
        for line in output.splitlines()
        if line.startswith("planned_vsmd_operations=")
    )
    assert "read_bytes(address=0x0124,size=2)" in planned
    assert "read_bytes(address=0x0a9c,size=2)" in planned
    assert "write_bytes(address=0x0124,payload=9c0c)" in planned
    assert "write_bytes(address=0x0a9c,payload=1000)" in planned
    assert "write_bytes(address=0x01f6,payload=c800)" in planned
    assert "write_bytes(address=0x01f6,payload=0000)" in planned
    assert "write_bytes(address=0x0124,payload=8a00)" in planned
    assert "address=0x0c9c" not in planned


def test_dry_run_source_has_no_live_transport_or_socket_factory():
    source = inspect.getsource(module)
    forbidden = (
        "AppManagerTcpTransport",
        "VsmdTcpTransport",
        "VsmdMemoryClient",
        "socket",
        "create_connection",
    )
    assert all(value not in source for value in forbidden)
