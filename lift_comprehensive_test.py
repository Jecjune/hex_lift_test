#!/usr/bin/env python3
# -*- coding:utf-8 -*-
################################################################
# Copyright 2025 Jecjune. All rights reserved.
# Author: Jecjune zejun.chen@hexfellow.com
# Date  : 2025-8-1
################################################################

# 发货测试
# Linear Lift Comprehensive Test Suite
#
# Three test phases executed sequentially by default:
#   1. High-Speed Round-Trip:  max speed, [min, max], 5 minutes, 500Hz CSV 高速运动
#   2. High-Frequency Oscillation: 100Hz, mid±0.05m, 5 minutes, 500Hz CSV 震荡测试
#   3. Durability Test: 80% max speed, [min, max], 2 hours, 50Hz CSV 耐久性测试
#
# Quick Start:
#   python3 device_test/lift_comprehensive_test.py --url ws://<Your controller ip>:8439
#
# Start from a specific test:
#   python3 device_test/lift_comprehensive_test.py --url ws://<ip>:8439 --start-from 2
# Start for different test durations:
#   python3 device_test/lift_comprehensive_test.py --url ws://<ip>:8439 --phase1-duration 10 --phase2-duration 10 --phase3-duration 10

# CSV reading tips:
# The pos range is in the first line of the csv file, like this:
# # min_pos_m=0.0000, max_pos_m=1.0000
# Use pandas.read_csv(comment='#') to correctly parse the data.

import sys
import os
# 注意csv保存路径！！！！
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comprehensive_csv_save")

import argparse
import time
import csv
import datetime
from urllib.parse import urlparse

import hex_device
from hex_device import HexDeviceApi
from hex_device import LinearLift
from hex_device.motor_base import CommandType
import numpy as np

from utils.controller_id_capture import find_hostname_by_ip_live


# ---------------------------------------------------------------------------
# Acceptance check
# ---------------------------------------------------------------------------

def acceptance_check(device, timeout=10.0):
    """
    Run a basic acceptance check: send a position command and verify the
    lift responds correctly (position changes toward target).
    Returns True if lift is operational, False otherwise.
    """
    if not isinstance(device, LinearLift):
        return True

    pos_min, pos_max = device.get_pos_range()
    pos_min, pos_max = float(pos_min), float(pos_max)
    mid_pos = (pos_min + pos_max) / 2.0

    # Read current position
    current_raw = device.get_motor_positions()
    if current_raw is not None:
        start_pos = float(np.asarray(current_raw).ravel()[0])
    else:
        start_pos = mid_pos

    # Choose a target away from current position
    if abs(start_pos - pos_min) < abs(start_pos - pos_max):
        test_target = pos_max * 0.3  # go to 30% of max
    else:
        test_target = pos_max * 0.3

    test_target = max(pos_min, min(pos_max, test_target))
    device.set_move_speed(int(device.get_max_move_speed() * 0.5))
    # wait for the speed to be set
    time.sleep(0.2)
    device.motor_command(CommandType.POSITION, test_target)

    print(f"  Acceptance check: moving from {start_pos:.4f} to {test_target:.4f} ...")
    start_time = time.time()
    moved = False
    while time.time() - start_time < timeout:
        time.sleep(0.05)
        if device.has_new_data():
            cur_raw = device.get_motor_positions()
            if cur_raw is not None:
                cur_pos = float(np.asarray(cur_raw).ravel()[0])
                if abs(cur_pos - start_pos) > 0.01:
                    moved = True
                    print(f"  Acceptance check: lift moved to {cur_pos:.4f} — PASS")
                    break
    if not moved:
        print("  Acceptance check: FAILED — lift did not move!")
        return False
    return True


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

class TestConfig:
    """Configuration for a single test phase."""

    def __init__(self, name, duration_s, record_hz, speed_ratio,
                 csv_path, test_type):
        self.name = name
        self.duration_s = duration_s
        self.record_hz = record_hz
        self.speed_ratio = speed_ratio
        self.csv_path = csv_path
        self.test_type = test_type  # 'roundtrip', 'oscillation', 'durability'


def run_test_phase(api, config, lift_device, controller_id="unknown"):
    """
    Run a single test phase.
    Returns True if test completed successfully, False on error.
    """
    device = lift_device
    record_interval = 1.0 / config.record_hz

    # CSV setup
    os.makedirs(os.path.dirname(config.csv_path), exist_ok=True)
    csv_file = open(config.csv_path, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'elapsed_s', 'timestamp_s',
        'target_pos_m', 'current_pos_m', 'current_speed_pps',
        'move_speed_pps'
    ])

    # Lift parameters (read from first data frame already received)
    pos_min, pos_max = device.get_pos_range()
    pos_min, pos_max = float(pos_min), float(pos_max)
    max_speed = device.get_max_move_speed()

    # Write min/max position as a single metadata comment row
    csv_file.write(f"# min_pos_m={pos_min:.4f}, max_pos_m={pos_max:.4f}\n")
    csv_file.write(f"# controller_id={controller_id}\n")
    pulse_per_meter = device.get_pulse_per_meter()

    if max_speed is None or max_speed <= 0:
        print(f"ERROR: max_speed is invalid for test '{config.name}'.")
        csv_file.close()
        return False

    move_speed = max_speed * config.speed_ratio
    device.set_move_speed(int(move_speed))
    # wait for the speed to be set
    time.sleep(0.2)
    mid_pos = (pos_min + pos_max) / 2.0

    # Print test header
    speed_mps = (move_speed / pulse_per_meter) if pulse_per_meter > 0 else 0.0
    print()
    print("=" * 60)
    print(f"  {config.name}")
    print("=" * 60)
    print(f"  Duration:             {config.duration_s:.0f} s")
    print(f"  Position range:       [{pos_min:.4f}, {pos_max:.4f}] m")
    print(f"  Mid position:         {mid_pos:.4f} m")
    print(f"  Max speed:            {max_speed:.0f} pulse/s")
    print(f"  Move speed ({config.speed_ratio*100:.0f}%):  {move_speed:.0f} pulse/s")
    print(f"  Speed in m/s:         {speed_mps:.3f}")
    print(f"  Record frequency:     {config.record_hz} Hz")
    print(f"  Test type:            {config.test_type}")
    print(f"  CSV:                  {config.csv_path}")
    print("=" * 60)
    print()

    # ---- Phase-specific state ----
    if config.test_type == 'roundtrip':
        # Oscillate between min and max
        current_target = pos_min
        last_direction_switch = 0.0
        direction = 1  # 1 = moving toward max, -1 = moving toward min
        settle_tolerance = 0.005
        min_settle_time = 0.3

    elif config.test_type == 'oscillation':
        # 100Hz toggling between mid+0.05 and mid-0.05
        osc_amplitude = 0.05
        osc_direction = 1  # 1 = mid+amp, -1 = mid-amp
        last_osc_command_time = 0.0
        osc_interval = 1.0 / 100.0  # 100Hz command rate

    elif config.test_type == 'durability':
        # Same as roundtrip but at 80% speed
        current_target = pos_min
        last_direction_switch = 0.0
        direction = 1
        settle_tolerance = 0.005
        min_settle_time = 0.5

    # ---- Recording state ----
    last_record_time = 0.0
    test_start_time = 0.0
    total_records = 0
    test_initialized = False
    test_running = True
    test_complete = False

    # Progress print and CSV flush intervals
    progress_interval = min(30.0, config.duration_s / 10.0)  # every 30s or 1/10 of duration
    last_progress_time = 0.0
    flush_interval_records = 5000  # flush CSV every 5000 records
    records_since_flush = 0

    # Send initial command
    if config.test_type == 'roundtrip' or config.test_type == 'durability':
        first_target = max(pos_min, min(pos_max, pos_min))
        device.motor_command(CommandType.POSITION, first_target)
    elif config.test_type == 'oscillation':
        first_target = max(pos_min, min(pos_max, mid_pos + osc_amplitude))
        device.motor_command(CommandType.POSITION, first_target)

    try:
        while True:
            if api.is_api_exit():
                print("Public API has exited.")
                break

            if not device.has_new_data():
                time.sleep(0.0001)
                continue

            t_now = time.time()

            if not test_initialized:
                test_initialized = True
                test_start_time = t_now
                last_record_time = t_now
                if config.test_type == 'oscillation':
                    last_osc_command_time = t_now
                if config.test_type in ('roundtrip', 'durability'):
                    last_direction_switch = t_now
                last_progress_time = t_now
                print(f"[0.00s] Test '{config.name}' started.")

            # ---- Read current position ----
            current_pos_raw = device.get_motor_positions()
            if current_pos_raw is not None:
                current_pos_m = float(np.asarray(current_pos_raw).ravel()[0])
            else:
                current_pos_m = 0.0
            current_speed = device.get_move_speed()
            elapsed = t_now - test_start_time

            # ---- Check duration ----
            if elapsed >= config.duration_s and not test_complete:
                test_running = False
                test_complete = True
                print(f"\n[{elapsed:.2f}s] Test '{config.name}' completed!")
                print(f"  Total records: {total_records}")

            # ---- Phase-specific logic ----
            osc_dir_label = 0
            if test_running:
                if config.test_type in ('roundtrip', 'durability'):
                    effective_target = max(pos_min, min(pos_max, current_target))
                    pos_error = abs(current_pos_m - effective_target)
                    switch_elapsed = t_now - last_direction_switch

                    advance = False
                    if pos_error < settle_tolerance and switch_elapsed >= min_settle_time:
                        advance = True

                    if advance:
                        direction *= -1
                        if direction == 1:
                            current_target = pos_max
                        else:
                            current_target = pos_min
                        next_target = max(pos_min, min(pos_max, current_target))
                        device.motor_command(CommandType.POSITION, next_target)
                        last_direction_switch = t_now
                        print(f"[{elapsed:.2f}s] Switching to {current_target:.4f} m  "
                              f"(pos={current_pos_m:.4f}, err={pos_error:.4f})")

                elif config.test_type == 'oscillation':
                    if t_now - last_osc_command_time >= osc_interval:
                        osc_direction *= -1
                        if osc_direction == 1:
                            target = mid_pos + osc_amplitude
                        else:
                            target = mid_pos - osc_amplitude
                        target = max(pos_min, min(pos_max, target))
                        device.motor_command(CommandType.POSITION, target)
                        last_osc_command_time = t_now
                    osc_dir_label = osc_direction

            # ---- Progress print ----
            if test_running and (t_now - last_progress_time >= progress_interval):
                pct = (elapsed / config.duration_s) * 100.0
                print(f"[{elapsed:.1f}s / {config.duration_s:.0f}s] {pct:.1f}%  "
                      f"pos={current_pos_m:.4f}m  records={total_records}")
                last_progress_time = t_now

            # ---- CSV recording ----
            if test_running and (t_now - last_record_time >= record_interval):
                csv_writer.writerow([
                    f"{elapsed:.6f}",
                    f"{t_now:.6f}",
                    f"{current_target if config.test_type in ('roundtrip', 'durability') else (mid_pos + osc_amplitude * osc_direction):.6f}",
                    f"{current_pos_m:.6f}",
                    f"{current_speed:.1f}" if current_speed is not None else "0.0",
                    f"{move_speed:.1f}"
                ])
                total_records += 1
                records_since_flush += 1
                last_record_time = t_now

                # Periodic flush for data safety (especially important for 2-hour test)
                if records_since_flush >= flush_interval_records:
                    csv_file.flush()
                    records_since_flush = 0

            # ---- Post-test flush ----
            if test_complete:
                if t_now - last_record_time > 0.5:
                    break

            time.sleep(0.0001)

    except KeyboardInterrupt:
        print(f"\nReceived Ctrl-C during '{config.name}'. Shutting down...")
    except Exception as e:
        print(f"\nERROR in '{config.name}': {e}")
        import traceback
        traceback.print_exc()
        csv_file.flush()
        csv_file.close()
        return False
    finally:
        csv_file.flush()
        csv_file.close()
        print(f"\nCSV saved to: {config.csv_path}")
        print(f"Total records written: {total_records}")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Linear Lift Comprehensive Test Suite — 3 phases executed sequentially',
        formatter_class=argparse.RawTextHelpFormatter,
        usage="python lift_comprehensive_test.py --url ws://<device_url>:8439 [options]"
    )
    parser.add_argument(
        '--url',
        metavar='URL',
        required=True,
        help='WebSocket URL for HEX device connection, e.g. ws://0.0.0.0:8439'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level for hex_device package (default: INFO)'
    )
    parser.add_argument(
        '--start-from',
        type=int,
        choices=[1, 2, 3],
        default=1,
        help='Test phase to start from (1, 2, or 3). Default: 1 (run all three sequentially)'
    )
    # Phase-specific durations (for debugging / custom runs)
    parser.add_argument(
        '--phase1-duration',
        type=float,
        default=300.0,
        help='Duration of phase 1 (high-speed round-trip) in seconds (default: 300 = 5 min)'
    )
    parser.add_argument(
        '--phase2-duration',
        type=float,
        default=300.0,
        help='Duration of phase 2 (high-freq oscillation) in seconds (default: 300 = 5 min)'
    )
    parser.add_argument(
        '--phase3-duration',
        type=float,
        default=7200.0,
        help='Duration of phase 3 (durability) in seconds (default: 7200 = 2 hours)'
    )
    args = parser.parse_args()

    # Extract controller IP from WebSocket URL and resolve its hostname
    parsed_url = urlparse(args.url)
    controller_ip = parsed_url.hostname or "unknown"
    print(f"Resolving controller ID for IP: {controller_ip} ...")
    controller_id = find_hostname_by_ip_live(controller_ip)
    if controller_id:
        # Strip .local suffix and trailing dot for a clean id
        controller_id_short = controller_id.replace(".local", "")
        print(f"  Controller ID: {controller_id_short}")
    else:
        controller_id_short = "unknown"
        print("  WARNING: Could not resolve controller ID via avahi-browse")

    hex_device.set_log_level(args.log_level)
    print(f"Log level set to: {args.log_level}")

    # ---- Output directory ----
    folder_name = datetime.datetime.now().strftime("test_suite_%Y%m%d_%H%M%S")
    output_dir = os.path.join(CSV_PATH, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # ---- Build test configs ----
    test_configs = []

    if args.start_from <= 1:
        test_configs.append(TestConfig(
            name="1_HighSpeed_RoundTrip",
            duration_s=args.phase1_duration,
            record_hz=500,
            speed_ratio=1.0,  # max speed
            csv_path=os.path.join(output_dir, "test_1_high_speed_round_trip.csv"),
            test_type='roundtrip'
        ))

    if args.start_from <= 2:
        test_configs.append(TestConfig(
            name="2_HighFreq_Oscillation",
            duration_s=args.phase2_duration,
            record_hz=500,
            speed_ratio=1.0,  # max speed for fast response
            csv_path=os.path.join(output_dir, "test_2_high_freq_oscillation.csv"),
            test_type='oscillation'
        ))

    if args.start_from <= 3:
        test_configs.append(TestConfig(
            name="3_Durability",
            duration_s=args.phase3_duration,
            record_hz=50,
            speed_ratio=0.8,  # 80% max speed
            csv_path=os.path.join(output_dir, "test_3_durability.csv"),
            test_type='durability'
        ))

    if not test_configs:
        print("No test phases to run. Check --start-from value.")
        sys.exit(0)

    print(f"\nTest plan ({len(test_configs)} phase(s)):")
    for cfg in test_configs:
        print(f"  - {cfg.name}: {cfg.duration_s:.0f}s, {cfg.record_hz}Hz, "
              f"speed={cfg.speed_ratio*100:.0f}%, type={cfg.test_type}")
    print()

    # ---- Initialize API ----
    api = HexDeviceApi(ws_url=args.url, control_hz=500, enable_kcp=True, local_port=0)

    # ---- Wait for device to appear ----
    print("Waiting for LinearLift device to appear...")
    lift_device = None
    wait_start = time.time()
    while lift_device is None:
        if api.is_api_exit():
            print("API exited before device appeared.")
            api.close()
            sys.exit(1)
        for device in api.device_list:
            if isinstance(device, LinearLift):
                lift_device = device
                break
        if lift_device is None:
            if time.time() - wait_start > 30.0:
                print("ERROR: No LinearLift device found within 30 seconds.")
                api.close()
                sys.exit(1)
            time.sleep(0.1)

    print(f"Found device: {lift_device}")

    # Wait for first data frame to populate parameters
    print("Waiting for first data frame...")
    while not lift_device.has_new_data():
        if api.is_api_exit():
            print("API exited before first data.")
            api.close()
            sys.exit(1)
        time.sleep(0.01)

    # Read initial parameters
    pos_min, pos_max = lift_device.get_pos_range()
    max_speed = lift_device.get_max_move_speed()
    if max_speed is None or max_speed <= 0:
        print("ERROR: Cannot read max speed. Is the lift calibrated?")
        api.close()
        sys.exit(1)

    print(f"Lift parameters: range=[{pos_min:.4f}, {pos_max:.4f}] m, "
          f"max_speed={max_speed:.0f} pulse/s")

    # ---- Run tests sequentially ----
    all_passed = True
    for config in test_configs:
        success = run_test_phase(api, config, lift_device, controller_id_short)
        if not success:
            print(f"\nTest '{config.name}' FAILED or was interrupted.")
            all_passed = False
            break

        # ---- Acceptance check after each test ----
        print(f"\nRunning acceptance check after '{config.name}'...")
        if not acceptance_check(lift_device, timeout=10.0):
            print(f"Acceptance check FAILED after '{config.name}'!")
            all_passed = False
            break
        print(f"Acceptance check PASSED after '{config.name}'.")

        # ---- Wait 3 seconds before next test ----
        print("Waiting 3 seconds before next test...")
        time.sleep(3.0)
        print()

    # ---- Cleanup ----
    api.close()

    print()
    print("=" * 60)
    if all_passed:
        print("  All tests PASSED!")
    else:
        print("  Some tests FAILED or were interrupted.")
    print(f"  Output directory: {output_dir}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
