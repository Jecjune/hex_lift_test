#!/usr/bin/env python3
# -*- coding:utf-8 -*-
################################################################
# Copyright 2025 Jecjune. All rights reserved.
# Author: Jecjune zejun.chen@hexfellow.com
# Date  : 2025-8-1
################################################################

# Linear Lift Range Test
# Moves through [min - 0.1m, max + 0.1m] at 80% max speed for 2 rounds,
# records position/speed data to CSV at 500Hz.
#
# Quick Start: python3 device_test/lift_range_test.py --url ws://<Your controller ip>:8439

import sys
import os
import argparse
import time
import csv

import hex_device
from hex_device import HexDeviceApi
from hex_device import LinearLift
from hex_device.motor_base import CommandType
import numpy as np


def main():
    parser = argparse.ArgumentParser(
        description='Linear Lift range test — 2 rounds through [min-0.1, max+0.1] at 80% max speed',
        formatter_class=argparse.RawTextHelpFormatter,
        usage="python lift_range_test.py --url ws://<device_url>:8439 [options]"
    )
    parser.add_argument(
        '--url',
        metavar='URL',
        required=True,
        help='WebSocket URL for HEX device connection, e.g. ws://0.0.0.0:8439 or ws://[::1%%eth0]:8439'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level for hex_device package (default: INFO)'
    )
    parser.add_argument(
        '--rounds',
        type=int,
        default=2,
        help='Number of round-trips through the range (default: 2)'
    )
    parser.add_argument(
        '--speed-ratio',
        type=float,
        default=0.8,
        help='Speed ratio relative to max speed (default: 0.8 = 80%%)'
    )
    parser.add_argument(
        '--settle-time',
        type=float,
        default=1.5,
        help='Minimum settle time in seconds at each waypoint (default: 1.5)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.005,
        help='Position error tolerance in meters to consider waypoint reached (default: 0.005)'
    )
    args = parser.parse_args()

    hex_device.set_log_level(args.log_level)
    print(f"Log level set to: {args.log_level}")

    # Save CSV to device_test/csv_save/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "csv_save")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "lift_range_test.csv")
    print(f"CSV output directory: {output_dir}")

    # Open CSV file
    csv_file = open(csv_path, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        'elapsed_s', 'timestamp_s', 'round', 'waypoint_idx',
        'target_pos_m', 'current_pos_m', 'current_speed_pps',
        'max_speed_pps', 'move_speed_pps', 'min_pos_m', 'max_pos_m'
    ])

    # Initialize API
    api = HexDeviceApi(ws_url=args.url, control_hz=500, enable_kcp=True, local_port=0)

    # State tracking
    first_time = True
    test_initialized = False
    test_running = False
    test_complete = False

    # Lift parameters (populated from first data frame)
    pos_min = 0.0
    pos_max = 0.0
    max_speed = 0.0
    move_speed = 0.0
    pulse_per_meter = 0.0

    # Test range (min-0.1, max+0.1)
    test_min = 0.0
    test_max = 0.0

    # Waypoint trajectory
    waypoints = []
    waypoint_idx = 0
    rounds_completed = 0
    last_waypoint_switch_time = 0.0
    waypoint_timeout = 30.0  # max seconds per waypoint before forcing advance

    # Recording throttle (500Hz)
    last_record_time = 0.0
    record_interval = 1.0 / 500.0
    test_start_time = 0.0
    total_records = 0

    try:
        while True:
            if api.is_api_exit():
                print("Public API has exited.")
                break

            for device in api.device_list:
                if not isinstance(device, LinearLift):
                    continue
                if not device.has_new_data():
                    continue

                t_now = time.time()

                # --- First data frame: initialize test parameters ---
                if first_time:
                    first_time = False

                    # Read lift status (has_new_data is True, so data is fresh)
                    pos_min, pos_max = device.get_pos_range()
                    pos_min, pos_max = float(pos_min), float(pos_max)  # ensure float (pos_min is int 0)
                    max_speed = device.get_max_move_speed()
                    pulse_per_meter = device.get_pulse_per_meter()

                    if max_speed is None or max_speed <= 0:
                        print("ERROR: max_speed is invalid. Is the lift calibrated?")
                        csv_file.close()
                        api.close()
                        exit(1)

                    move_speed = max_speed * args.speed_ratio
                    device.set_move_speed(int(move_speed))

                    # Compute test range with ±0.1m margin
                    test_min = pos_min - 0.1
                    test_max = pos_max + 0.1

                    # Build waypoints: each round = test_min -> test_max -> test_min
                    waypoints.clear()
                    waypoints.append(test_min)
                    for _ in range(args.rounds):
                        waypoints.append(test_max)
                        waypoints.append(test_min)

                    # Estimate travel time for waypoint timeout
                    speed_mps = (move_speed / pulse_per_meter) if pulse_per_meter > 0 else 0.01
                    travel_range = abs(test_max - test_min)
                    est_travel_time = travel_range / speed_mps if speed_mps > 0 else 30.0
                    waypoint_timeout = max(est_travel_time * 1.5 + args.settle_time, 30.0)

                    print()
                    print("=" * 60)
                    print("  Linear Lift Range Test")
                    print("=" * 60)
                    print(f"  Normal range:         [{pos_min:.4f}, {pos_max:.4f}] m")
                    print(f"  Test range:           [{test_min:.4f}, {test_max:.4f}] m")
                    print(f"  Max speed:            {max_speed:.0f} pulse/s")
                    print(f"  Move speed (80%):     {move_speed:.0f} pulse/s")
                    print(f"  Speed in m/s:         {speed_mps:.3f}")
                    print(f"  Pulse per meter:      {pulse_per_meter:.0f}")
                    print(f"  Rounds:               {args.rounds}")
                    print(f"  Waypoints:            {[f'{w:.3f}' for w in waypoints]}")
                    print(f"  Settle time:          {args.settle_time} s")
                    print(f"  Tolerance:            {args.tolerance} m")
                    print(f"  Waypoint timeout:     {waypoint_timeout:.0f} s")
                    print(f"  Record frequency:     500 Hz")
                    print("=" * 60)
                    print()

                    test_initialized = True
                    test_running = True
                    test_start_time = t_now
                    waypoint_idx = 0
                    rounds_completed = 0
                    last_waypoint_switch_time = t_now

                    # Send first waypoint (clip to [0, pos_max] to avoid ValueError)
                    first_target = max(pos_min, min(pos_max, waypoints[0]))
                    device.motor_command(CommandType.POSITION, first_target)
                    print(f"[{t_now - test_start_time:.2f}s] WP{waypoint_idx}: target={waypoints[0]:.4f} m  "
                          f"(clipped={first_target:.4f} m)")

                # --- Read position once per data frame (resets has_new_data flag) ---
                # get_motor_positions() returns meters; single-motor lift returns a 0-d scalar, not an array
                current_pos_raw = device.get_motor_positions()
                if current_pos_raw is not None:
                    current_pos_m = float(np.asarray(current_pos_raw).ravel()[0])
                else:
                    current_pos_m = 0.0
                current_speed = device.get_move_speed()

                # --- Collect data (500Hz throttled) ---
                if test_running and (t_now - last_record_time >= record_interval):
                    elapsed = t_now - test_start_time
                    csv_writer.writerow([
                        f"{elapsed:.6f}",
                        f"{t_now:.6f}",
                        rounds_completed,
                        waypoint_idx,
                        f"{waypoints[waypoint_idx]:.6f}" if waypoint_idx < len(waypoints) else "0.000000",
                        f"{current_pos_m:.6f}",
                        f"{current_speed:.1f}" if current_speed is not None else "0.0",
                        f"{max_speed:.1f}",
                        f"{move_speed:.1f}",
                        f"{pos_min:.4f}",
                        f"{pos_max:.4f}"
                    ])
                    total_records += 1
                    last_record_time = t_now

                # --- Waypoint progression ---
                if test_running and waypoint_idx < len(waypoints):
                    target = waypoints[waypoint_idx]

                    # Since LinearLift clips position commands to [0, pos_max],
                    # compute the effective target for arrival checking.
                    effective_target = max(pos_min, min(pos_max, target))

                    pos_error = abs(current_pos_m - effective_target)
                    waypoint_elapsed = t_now - last_waypoint_switch_time

                    # Must satisfy: error within tolerance AND enough settle time elapsed
                    advance = False
                    if pos_error < args.tolerance and waypoint_elapsed >= args.settle_time:
                        advance = True
                    elif waypoint_elapsed >= waypoint_timeout:
                        print(f"  WARNING: waypoint {waypoint_idx} timed out after {waypoint_timeout:.0f}s "
                              f"(err={pos_error:.4f}m), advancing to next.")
                        advance = True

                    if advance:
                        waypoint_idx += 1
                        if waypoint_idx < len(waypoints):
                            # Clip target to [0, pos_max] to avoid ValueError from motor_command
                            next_target = max(pos_min, min(pos_max, waypoints[waypoint_idx]))
                            device.motor_command(CommandType.POSITION, next_target)
                            last_waypoint_switch_time = t_now
                            rounds_completed = waypoint_idx // 2
                            elapsed = t_now - test_start_time
                            print(f"[{elapsed:.2f}s] WP{waypoint_idx}: target={waypoints[waypoint_idx]:.4f} m  "
                                  f"(pos={current_pos_m:.4f}, err={pos_error:.4f})")
                        else:
                            # All waypoints finished
                            rounds_completed = args.rounds
                            test_running = False
                            test_complete = True
                            elapsed = t_now - test_start_time
                            print()
                            print(f"[{elapsed:.2f}s] All {args.rounds} rounds completed!")
                            print(f"  Total records: {total_records}")
                            print(f"  CSV saved to:  {csv_path}")

                # --- Post-test: flush remaining CSV data ---
                if test_complete:
                    # Let the last data frames flush, then exit
                    if t_now - last_record_time > 0.5:
                        break

            if test_complete:
                time.sleep(0.5)
                break

            time.sleep(0.0001)

    except KeyboardInterrupt:
        print("\nReceived Ctrl-C. Shutting down...")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        csv_file.flush()
        csv_file.close()
        api.close()
        print(f"\nCSV saved to: {csv_path}")
        print(f"Total records written: {total_records}")
        print("Resources cleaned up.")
        sys.exit(0)


if __name__ == "__main__":
    main()
