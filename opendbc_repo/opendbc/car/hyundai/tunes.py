#!/usr/bin/env python3
from enum import Enum
from openpilot.common.params import Params

class LatTunes(Enum):
  TORQUE = 0


###### LAT ######
def set_lat_tune(tune, name, max_lat_accel=2.5, FRICTION=.1):
  params = Params()
  if name == LatTunes.TORQUE:
    TorqueKp = params.get("TorqueKp", return_default=True) * 0.1
    TorqueKf = params.get("TorqueKf", return_default=True) * 0.1
    TorqueKi = params.get("TorqueKi", return_default=True) * 0.1
    TorqueKd = params.get("TorqueKd", return_default=True) * 0.1
    TorqueFriction = params.get("TorqueFriction", return_default=True) * 0.001
    max_lat_accel = params.get("TorqueMaxLatAccel", return_default=True) * 0.1
    steer_ang_deadzone = params.get("TorqueAngDeadZone", return_default=True) * 0.1
    tune.init('torque')
    tune.torque.kp = TorqueKp # 1.0
    tune.torque.kf = TorqueKf # 1.0
    tune.torque.ki = TorqueKi # 0.3
    tune.torque.kd = TorqueKd # 0.0
    tune.torque.friction = TorqueFriction
    tune.torque.steeringAngleDeadzoneDeg = steer_ang_deadzone
  else:
    raise NotImplementedError('This lateral tune does not exist')
