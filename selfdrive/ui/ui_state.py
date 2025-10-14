import pyray as rl
import numpy as np
import time
import threading
from collections.abc import Callable
from enum import Enum
from cereal import messaging, car, log
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.lib.prime_state import PrimeState
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.hardware import HARDWARE

UI_BORDER_SIZE = 30
BACKLIGHT_OFFROAD = 50


class UIStatus(Enum):
  DISENGAGED = "disengaged"
  ENGAGED = "engaged"
  OVERRIDE = "override"


class UIState:
  _instance: 'UIState | None' = None

  def __new__(cls):
    if cls._instance is None:
      cls._instance = super().__new__(cls)
      cls._instance._initialize()
    return cls._instance

  def _initialize(self):
    self.params = Params()
    self.sm = messaging.SubMaster(
      [
        "modelV2",
        "controlsState",
        "liveCalibration",
        "radarState",
        "deviceState",
        "pandaStates",
        "carParams",
        "driverMonitoringState",
        "carState",
        "driverStateV2",
        "roadCameraState",
        "wideRoadCameraState",
        "managerState",
        "selfdriveState",
        "longitudinalPlan",
        "rawAudioData",
        "liveENaviData",
        "liveMapData",
      ]
    )

    self.prime_state = PrimeState()

    # UI Status tracking
    self.status: UIStatus = UIStatus.DISENGAGED
    self.started_frame: int = 0
    self.started_time: float = 0.0
    self._engaged_prev: bool = False
    self._started_prev: bool = False

    # Core state variables
    self.is_metric: bool = self.params.get_bool("IsMetric")
    self.started: bool = False
    self.ignition: bool = False
    self.recording_audio: bool = False
    self.panda_type: log.PandaState.PandaType = log.PandaState.PandaType.unknown
    self.personality: log.LongitudinalPersonality = log.LongitudinalPersonality.standard
    self.has_longitudinal_control: bool = False
    self.CP: car.CarParams | None = None
    self.light_sensor: float = -1.0
    self._param_update_time: float = 0.0

    # Kisa state variables
    self.lateralControlMethod: int = -1
    self.output_scale: float = 0.0
    self.alertTextMsg1: str = ""
    self.alertTextMsg2: str = ""
    self.alertTextMsg3: str = ""
    self.limitSpeedCamera: float = 0
    self.limitSpeedCameraDist: float = 0
    self.mapSign: str = ""
    self.steerRatio: float = 0.0
    self.dynamic_tr_mode: int = 0
    self.dynamic_tr_value: float = 0.0
    self.accel: float = 0.0
    self.ctrl_speed: float = 0
    self.desired_angle_steers: float = 0.0
    self.gap_by_speed_on: bool = False
    self.exp_mode_temp: bool = False
    self.btn_pressing: int = 0
    self.standStill: bool = False
    self.standstillElapsedTime: int = 0

    self.brakePress: bool = False
    self.gasPress: bool = False
    self.brakeLights: bool = False
    self.getGearShifter: int = 0
    self.leftBlinker: bool = False
    self.rightBlinker: bool = False
    self.leftblindspot: bool = False
    self.rightblindspot: bool = False
    self.tpmsUnit: int = 0
    self.tpmsPressureFl: float = 0
    self.tpmsPressureFr: float = 0
    self.tpmsPressureRl: float = 0
    self.tpmsPressureRr: float = 0
    self.radarDRel: float = 0.0
    self.radarVRel: float = 0.0
    self.vSetDis: float = 0
    self.cruiseAccStatus: bool = False
    self.driverAcc: bool = False
    self.angleSteers: float = 0.0
    self.cruise_gap: int = 0
    self.autoHold: bool = False
    self.steer_warning: bool = False
    self.a_req_value: float = 0.0
    self.engine_rpm: float = 0.0
    self.gear_step: int = 0
    self.charge_meter: float = 0.0
    self.pause_spdlimit: bool = False

    self.op_long_enabled: bool = False

    self.navi_select: int = self.params.get("KISANaviSelect")
    self.road_spdlimit_offset: int = self.params.get("CruiseSetwithRoadLimitSpeedOffset")
    self.ekisaspeedlimit: int = 0
    self.ekisasafetydist: float = 0
    self.ekisasafetysign: str = ""
    self.ekisaturninfo: str = ""
    self.ekisadisttoturn: float = 0
    self.ekisaconalive: bool = False
    self.ekisaroadlimitspeed: int = 0
    self.ekisalinklength: int = 0
    self.ekisacurrentlinkangle: int = 0
    self.ekisanextlinkangle: int = 0
    self.ekisaroadname: str = ""
    self.ekisaishighway: bool = False
    self.ekisaistunnel: bool = False
    self.ewazealertid: int = 0
    self.ewazealertdistance: int = 0
    self.ewazeroadspeedlimit: int = 0
    self.ewazecurrentspeed: int = 0
    self.ewazeroadname: str = ""
    self.ewazenavsign: int = 0
    self.ewazenavdistance: int = 0
    self.ewazealerttype: str = ""
    self.ewazealertextend: bool = False
    self.ewazealertdistanceraw: str = ""
    self.ospeedLimit: float = 0
    self.ospeedLimitAhead: float = 0
    self.ospeedLimitAheadDistance: float = 0
    self.oturnSpeedLimit: float = 0
    self.oturnSpeedLimitEndDistance: float = 0
    self.oturnSpeedLimitSign: int = 0
    self.ocurrentRoadName: str = ""
    self.oref: str = ""

    # Callbacks
    self._offroad_transition_callbacks: list[Callable[[], None]] = []
    self._engaged_transition_callbacks: list[Callable[[], None]] = []

    self.update_params()

  def add_offroad_transition_callback(self, callback: Callable[[], None]):
    self._offroad_transition_callbacks.append(callback)

  def add_engaged_transition_callback(self, callback: Callable[[], None]):
    self._engaged_transition_callbacks.append(callback)

  @property
  def engaged(self) -> bool:
    return self.started and self.sm["selfdriveState"].enabled

  def is_onroad(self) -> bool:
    return self.started

  def is_offroad(self) -> bool:
    return not self.started

  def update(self) -> None:
    self.sm.update(0)
    self._update_state()
    self._update_status()
    if time.monotonic() - self._param_update_time > 5.0:
      self.update_params()
    device.update()

  def _update_state(self) -> None:
    # Handle panda states updates
    if self.sm.updated["pandaStates"]:
      panda_states = self.sm["pandaStates"]

      if len(panda_states) > 0:
        # Get panda type from first panda
        self.panda_type = panda_states[0].pandaType
        # Check ignition status across all pandas
        if self.panda_type != log.PandaState.PandaType.unknown:
          self.ignition = any(state.ignitionLine or state.ignitionCan for state in panda_states)
    elif self.sm.frame - self.sm.recv_frame["pandaStates"] > 5 * rl.get_fps():
      self.panda_type = log.PandaState.PandaType.unknown

    # Handle wide road camera state updates
    if self.sm.updated["wideRoadCameraState"]:
      cam_state = self.sm["wideRoadCameraState"]
      self.light_sensor = max(100.0 - cam_state.exposureValPercent, 0.0)
    elif not self.sm.alive["wideRoadCameraState"] or not self.sm.valid["wideRoadCameraState"]:
      self.light_sensor = -1

    # Update started state
    self.started = self.sm["deviceState"].started and self.ignition

    # Update recording audio state
    self.recording_audio = self.params.get_bool("RecordAudio") and self.started

    self.is_metric = self.params.get_bool("IsMetric")

    # Kisa states update
    if self.sm.updated["controlsState"]:
      controls_state = self.sm["controlsState"]
      self.lateralControlMethod = controls_state.lateralControlMethod
      if self.lateralControlMethod == 0:
        self.output_scale = controls_state.lateralControlState.pidState.output
      elif self.lateralControlMethod == 1:
        self.output_scale = controls_state.lateralControlState.indiState.output
      elif self.lateralControlMethod == 2:
        self.output_scale = controls_state.lateralControlState.lqrState.output
      elif self.lateralControlMethod == 3:
        self.output_scale = controls_state.lateralControlState.torqueState.output
      self.alertTextMsg1 = controls_state.alertTextMsg1  # debug1
      self.alertTextMsg2 = controls_state.alertTextMsg2  # debug2
      self.alertTextMsg3 = controls_state.alertTextMsg3  # debug3
      self.limitSpeedCamera = controls_state.limitSpeedCamera
      self.limitSpeedCameraDist = controls_state.limitSpeedCameraDist
      self.mapSign = controls_state.mapSign
      self.steerRatio = controls_state.steerRatio
      self.dynamic_tr_mode = controls_state.dynamicTRMode
      self.dynamic_tr_value = controls_state.dynamicTRValue
      self.accel = controls_state.accel
      self.ctrl_speed = controls_state.safetySpeed
      self.desired_angle_steers = controls_state.steeringAngleDesiredDeg
      self.gap_by_speed_on = controls_state.gapBySpeedOn
      self.exp_mode_temp = controls_state.expModeTemp
      self.btn_pressing = controls_state.btnPressing
      self.standStill = controls_state.standStill
      self.standstillElapsedTime = controls_state.standStillTimer

    if self.sm.updated["carState"]:
      car_state = self.sm["carState"]
      self.brakePress = car_state.brakePressed
      self.gasPress = car_state.gasPressed
      self.brakeLights = car_state.brakeLights
      self.getGearShifter = car_state.gearShifter
      self.leftBlinker = car_state.leftBlinker
      self.rightBlinker = car_state.rightBlinker
      self.leftblindspot = car_state.leftBlindspot
      self.rightblindspot = car_state.rightBlindspot
      self.tpmsUnit = car_state.tpms.unit
      self.tpmsPressureFl = car_state.tpms.fl
      self.tpmsPressureFr = car_state.tpms.fr
      self.tpmsPressureRl = car_state.tpms.rl
      self.tpmsPressureRr = car_state.tpms.rr
      self.radarDRel = car_state.radarDRel
      self.radarVRel = car_state.radarVRel
      self.vSetDis = car_state.vSetDis
      self.cruiseAccStatus = car_state.cruiseAccStatus
      self.driverAcc = car_state.driverAcc
      self.angleSteers = car_state.steeringAngleDeg
      self.cruise_gap = car_state.cruiseGapSet
      self.autoHold = car_state.autoHold
      self.steer_warning = car_state.steerFaultTemporary
      self.a_req_value = car_state.aReqValue
      self.engine_rpm = car_state.engineRpm
      self.gear_step = car_state.gearStep
      self.charge_meter = car_state.chargeMeter
      self.pause_spdlimit = car_state.pauseSpdLimit

    if self.sm.updated["liveENaviData"]:
      live_enavi_data = self.sm["liveENaviData"]
      self.ekisaspeedlimit = live_enavi_data.speedLimit
      self.ekisasafetydist = live_enavi_data.safetyDistance
      self.ekisasafetysign = live_enavi_data.safetySign
      self.ekisaturninfo = live_enavi_data.turnInfo
      self.ekisadisttoturn = live_enavi_data.distanceToTurn
      self.ekisaconalive = live_enavi_data.connectionAlive
      self.ekisaroadlimitspeed = live_enavi_data.roadLimitSpeed
      self.ekisalinklength = live_enavi_data.linkLength
      self.ekisacurrentlinkangle = live_enavi_data.currentLinkAngle
      self.ekisanextlinkangle = live_enavi_data.nextLinkAngle
      self.ekisaroadname = live_enavi_data.roadName
      self.ekisaishighway = live_enavi_data.isHighway
      self.ekisaistunnel = live_enavi_data.isTunnel
      if self.navi_select == 2 or self.navi_select == 4:
        self.ewazealertid = live_enavi_data.wazeAlertId
        self.ewazealertdistance = live_enavi_data.wazeAlertDistance
        self.ewazeroadspeedlimit = live_enavi_data.wazeRoadSpeedLimit
        self.ewazecurrentspeed = live_enavi_data.wazeCurrentSpeed
        self.ewazeroadname = live_enavi_data.wazeRoadName
        self.ewazenavsign = live_enavi_data.wazeNavSign
        self.ewazenavdistance = live_enavi_data.wazeNavDistance
        self.ewazealerttype = live_enavi_data.wazeAlertType
        self.ewazealertextend = live_enavi_data.wazeAlertExtend
        self.ewazealertdistanceraw = live_enavi_data.wazeAlertDistanceRaw

    if self.sm.updated["liveMapData"]:
      live_map_data = self.sm["liveMapData"]
      self.ospeedLimit = live_map_data.speedLimit
      self.ospeedLimitAhead = live_map_data.speedLimitAhead
      self.ospeedLimitAheadDistance = live_map_data.speedLimitAheadDistance
      self.oturnSpeedLimit = live_map_data.turnSpeedLimit
      self.oturnSpeedLimitEndDistance = live_map_data.turnSpeedLimitEndDistance
      self.oturnSpeedLimitSign = live_map_data.turnSpeedLimitSign
      self.ocurrentRoadName = live_map_data.currentRoadName
      self.oref = live_map_data.ref

  def _update_status(self) -> None:
    if self.started and self.sm.updated["selfdriveState"]:
      ss = self.sm["selfdriveState"]
      state = ss.state

      if state in (log.SelfdriveState.OpenpilotState.preEnabled, log.SelfdriveState.OpenpilotState.overriding):
        self.status = UIStatus.OVERRIDE
      else:
        self.status = UIStatus.ENGAGED if ss.enabled else UIStatus.DISENGAGED

    # Check for engagement state changes
    if self.engaged != self._engaged_prev:
      for callback in self._engaged_transition_callbacks:
        callback()
      self._engaged_prev = self.engaged

    # Handle onroad/offroad transition
    if self.started != self._started_prev or self.sm.frame == 1:
      if self.started:
        self.status = UIStatus.DISENGAGED
        self.started_frame = self.sm.frame
        self.started_time = time.monotonic()

      for callback in self._offroad_transition_callbacks:
        callback()

      self._started_prev = self.started

  def update_params(self) -> None:
    # For slower operations
    # Update longitudinal control state
    CP_bytes = self.params.get("CarParamsPersistent")
    if CP_bytes is not None:
      self.CP = messaging.log_from_bytes(CP_bytes, car.CarParams)
      if self.CP.alphaLongitudinalAvailable:
        self.has_longitudinal_control = self.params.get_bool("AlphaLongitudinalEnabled")
      else:
        self.has_longitudinal_control = self.CP.openpilotLongitudinalControl
    self._param_update_time = time.monotonic()


class Device:
  def __init__(self):
    self._ignition = False
    self._interaction_time: float = -1
    self._interactive_timeout_callbacks: list[Callable] = []
    self._prev_timed_out = False
    self._awake = False

    self._offroad_brightness: int = BACKLIGHT_OFFROAD
    self._last_brightness: int = 0
    self._brightness_filter = FirstOrderFilter(BACKLIGHT_OFFROAD, 10.00, 1 / gui_app.target_fps)
    self._brightness_thread: threading.Thread | None = None

  def reset_interactive_timeout(self, timeout: int = -1) -> None:
    if timeout == -1:
      timeout = 10 if ui_state.ignition else 30
    self._interaction_time = time.monotonic() + timeout

  def add_interactive_timeout_callback(self, callback: Callable):
    self._interactive_timeout_callbacks.append(callback)

  def update(self):
    # do initial reset
    if self._interaction_time <= 0:
      self.reset_interactive_timeout()

    self._update_brightness()
    self._update_wakefulness()

  def set_offroad_brightness(self, brightness: int):
    # TODO: not yet used, should be used in prime widget for QR code, etc.
    self._offroad_brightness = min(max(brightness, 0), 100)

  def _update_brightness(self):
    clipped_brightness = self._offroad_brightness

    if ui_state.started and ui_state.light_sensor >= 0:
      clipped_brightness = ui_state.light_sensor

      # CIE 1931 - https://www.photonstophotos.net/GeneralTopics/Exposure/Psychometric_Lightness_and_Gamma.htm
      if clipped_brightness <= 8:
        clipped_brightness = clipped_brightness / 903.3
      else:
        clipped_brightness = ((clipped_brightness + 16.0) / 116.0) ** 3.0

      clipped_brightness = float(np.clip(100 * clipped_brightness, 10, 100))

    brightness = round(self._brightness_filter.update(clipped_brightness))
    if not self._awake:
      brightness = 0

    if brightness != self._last_brightness:
      if self._brightness_thread is None or not self._brightness_thread.is_alive():
        self._brightness_thread = threading.Thread(target=HARDWARE.set_screen_brightness, args=(brightness,))
        self._brightness_thread.start()
        self._last_brightness = brightness

  def _update_wakefulness(self):
    # Handle interactive timeout
    ignition_just_turned_off = not ui_state.ignition and self._ignition
    self._ignition = ui_state.ignition

    if ignition_just_turned_off or any(ev.left_down for ev in gui_app.mouse_events):
      self.reset_interactive_timeout()

    interaction_timeout = time.monotonic() > self._interaction_time
    if interaction_timeout and not self._prev_timed_out:
      for callback in self._interactive_timeout_callbacks:
        callback()
    self._prev_timed_out = interaction_timeout

    self._set_awake(ui_state.ignition or not interaction_timeout)

  def _set_awake(self, on: bool):
    if on != self._awake:
      self._awake = on
      cloudlog.debug(f"setting display power {int(on)}")
      HARDWARE.set_display_power(on)


# Global instance
ui_state = UIState()
device = Device()
