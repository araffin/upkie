#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2023 Inria

"""Balancing using proportional control from base pitch to wheel torques."""

import gymnasium as gym
import upkie.envs
from upkie.observers.base_pitch import compute_base_pitch_from_imu

upkie.envs.register()

GAIN = 10.0  # base pitch to wheel torque, in [N] * [m] / [rad]


def run(env: upkie.envs.UpkieServos):
    action = env.get_neutral_action()

    # Position commands to keep the legs extended
    action["left_hip"]["position"] = 0.0
    action["left_knee"]["position"] = 0.0
    action["right_hip"]["position"] = 0.0
    action["right_knee"]["position"] = 0.0

    # Disable velocity feedback in the wheels
    # (we don't set kp_scale as the neutral action has no position command)
    action["left_wheel"]["kd_scale"] = 0.0
    action["right_wheel"]["kd_scale"] = 0.0

    obs, _ = env.reset()  # connects to the spine
    for step in range(1_000_000):
        pitch = compute_base_pitch_from_imu(obs["imu"]["orientation"])
        action["left_wheel"]["feedforward_torque"] = +GAIN * pitch
        action["right_wheel"]["feedforward_torque"] = -GAIN * pitch
        obs, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            obs, _ = env.reset()


if __name__ == "__main__":
    with gym.make("UpkieServos-v3", frequency=200.0) as env:
        run(env)
