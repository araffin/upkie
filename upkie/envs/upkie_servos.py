#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2023 Inria

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pinocchio as pin
import upkie_description
from gymnasium import spaces

from upkie.utils.clamp import clamp_and_warn
from upkie.utils.exceptions import ActionError, ModelError
from upkie.utils.pinocchio import (
    box_position_limits,
    box_torque_limits,
    box_velocity_limits,
)

from .upkie_base_env import UpkieBaseEnv


class UpkieServos(UpkieBaseEnv):

    """!
    Upkie with full observation and joint position-velocity-torque actions.

    ### Action space

    Vectorized actions have the following structure:

    <table>
        <tr>
            <td><strong>Index</strong></td>
            <td><strong>Description</strong></td>
            </tr>
        <tr>
            <td>``[0:nq]``</td>
            <td>Joint position commands in [rad].</td>
        </tr>
        <tr>
            <td>``[nq:nq + nv]``</td>
            <td>Joint velocity commands in [rad] / [s].</td>
        </tr>
        <tr>
            <td>``[nq + nv:nq + 2 * nv]``</td>
            <td>Joint torques in [N] * [m].</td>
        </tr>
    </table>

    ### Observation space

    Vectorized observations have the following structure:

    <table>
        <tr>
            <td><strong>Index</strong></td>
            <td><strong>Description</strong></td>
            </tr>
        <tr>
            <td>``[0:nq]``</td>
            <td>Joint positions in [rad].</td>
        </tr>
        <tr>
            <td>``[nq:nq + nv]``</td>
            <td>Joint velocities in [rad] / [s].</td>
        </tr>
        <tr>
            <td>``[nq + nv:nq + 2 * nv]``</td>
            <td>Joint torques in [N] * [m].</td>
        </tr>
    </table>

    ### Attributes

    The environment has the following attributes:

    - ``robot``: Pinocchio robot wrapper.
    - ``state_max``: Maximum values for the action and observation vectors.
    - ``state_min``: Minimum values for the action and observation vectors.
    - ``version``: Environment version number.

    See also @ref envs.upkie_base_env.UpkieBaseEnv "UpkieBaseEnv" for notes on
    using this environment.
    """

    ACTION_KEYS: Tuple[str, str, str, str, str, str] = (
        "position",
        "velocity",
        "feedforward_torque",
        "kp_scale",
        "kd_scale",
        "maximum_torque",
    )

    JOINT_NAMES: Tuple[str, str, str, str, str, str] = (
        "left_hip",
        "left_knee",
        "left_wheel",
        "right_hip",
        "right_knee",
        "right_wheel",
    )

    robot: pin.RobotWrapper
    version: int = 2

    def __init__(
        self,
        fall_pitch: float = 1.0,
        frequency: float = 200.0,
        shm_name: str = "/vulp",
        spine_config: Optional[dict] = None,
    ):
        """!
        Initialize environment.

        @param fall_pitch Fall pitch angle, in radians.
        @param frequency Regulated frequency of the control loop, in Hz.
        @param shm_name Name of shared-memory file.
        @param spine_config Additional spine configuration overriding the
            defaults from ``//config:spine.yaml``. The combined configuration
            dictionary is sent to the spine at every :func:`reset`.
        """
        super().__init__(
            fall_pitch=fall_pitch,
            frequency=frequency,
            shm_name=shm_name,
            spine_config=spine_config,
        )

        robot = upkie_description.load_in_pinocchio(root_joint=None)
        model = robot.model
        q_min, q_max = box_position_limits(model)
        v_max = box_velocity_limits(model)
        tau_max = box_torque_limits(model)
        joint_names = list(model.names)[1:]
        if set(joint_names) != set(self.JOINT_NAMES):
            raise ModelError(
                "Upkie joints don't match:"
                f"expected {self.JOINT_NAMES} "
                f"got {joint_names}"
            )

        action_space = {}
        default_action = {}
        max_action = {}
        min_action = {}
        observation_space = {}
        for name in joint_names:
            joint = model.joints[model.getJointId(name)]
            default_action[name] = {
                # "position": np.nan,  # no default, needs to be explicit
                # "velocity": 0.0,  # no default, needs to be explicit
                "feedforward_torque": 0.0,
                "kp_scale": 1.0,
                "kd_scale": 1.0,
                "maximum_torque": tau_max[joint.idx_v],
            }
            max_action[name] = {
                "position": q_max[joint.idx_q],
                "velocity": v_max[joint.idx_v],
                "feedforward_torque": tau_max[joint.idx_v],
                "kp_scale": 1.0,
                "kd_scale": 1.0,
                "maximum_torque": tau_max[joint.idx_v],
            }
            min_action[name] = {
                "position": q_min[joint.idx_q],
                "velocity": -v_max[joint.idx_v],
                "feedforward_torque": -tau_max[joint.idx_v],
                "kp_scale": 0.0,
                "kd_scale": 0.0,
                "maximum_torque": 0.0,
            }
            for space in (action_space, observation_space):
                space[name] = spaces.Dict(
                    {
                        "position": spaces.Box(
                            low=q_min[joint.idx_q],
                            high=q_max[joint.idx_q],
                            shape=(1,),
                            dtype=np.float32,
                        ),
                        "velocity": spaces.Box(
                            low=-v_max[joint.idx_v],
                            high=+v_max[joint.idx_v],
                            shape=(1,),
                            dtype=np.float32,
                        ),
                        "feedforward_torque": spaces.Box(
                            low=-tau_max[joint.idx_v],
                            high=+tau_max[joint.idx_v],
                            shape=(1,),
                            dtype=np.float32,
                        ),
                        "kp_scale": spaces.Box(
                            low=0.0,
                            high=1.0,
                            shape=(1,),
                            dtype=np.float32,
                        ),
                        "kd_scale": spaces.Box(
                            low=0.0,
                            high=1.0,
                            shape=(1,),
                            dtype=np.float32,
                        ),
                        "maximum_torque": spaces.Box(
                            low=0.0,
                            high=tau_max[joint.idx_v],
                            shape=(1,),
                            dtype=np.float32,
                        ),
                    }
                )

        # gymnasium.Env: action_space
        self.action_space = spaces.Dict(action_space)

        # gymnasium.Env: observation_space
        self.observation_space = spaces.Dict(observation_space)

        # Class members
        self.__default_action = default_action
        self.__max_action = max_action
        self.__min_action = min_action
        self.robot = robot

    def get_env_observation(self, spine_observation: dict):
        """!
        Extract environment observation from spine observation dictionary.

        @param spine_observation Full observation dictionary from the spine.
        @returns Environment observation.
        """
        return spine_observation

    def get_spine_action(self, env_action: Dict[str, Any]) -> dict:
        """!
        Convert environment action to a spine action dictionary.

        @param action Environment action.
        @returns Spine action dictionary.
        """
        spine_action = {"servo": {}}
        for joint in self.JOINT_NAMES:
            servo_action = {}
            for key in self.ACTION_KEYS:
                try:
                    action = (
                        env_action[joint][key]
                        if key in env_action[joint]
                        else self.__default_action[joint][key]
                    )
                except KeyError as key_error:
                    raise ActionError(
                        f'Missing key "{key}" required for joint "{joint}"'
                    ) from key_error
                servo_action[key] = clamp_and_warn(
                    action,
                    self.__min_action[joint][key],
                    self.__max_action[joint][key],
                    label=f"{joint}: {key}",
                )
            spine_action["servo"][joint] = servo_action
        return spine_action

    def get_reward(
        self,
        observation: Dict[str, Any],
        action: Dict[str, Any],
    ) -> float:
        """!
        Get reward from observation and action.

        @param observation Environment observation.
        @param action Environment action.
        @returns Reward.
        """
        return 1.0
