from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.list_view import toggle_item, button_item, numeric_item
from openpilot.system.ui.widgets.scroller import Scroller
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.application import gui_app
from openpilot.common.filter_simple import FirstOrderFilter
import os
import pyray as rl

BUTTON_HEIGHT = 90
BUTTON_PADDING = 10
HIGHLIGHT_COLOR = (34, 139, 34, 241)
DEFAULT_COLOR = (128, 128, 128, 255)
TEXT_COLOR = (255, 255, 255, 255)
TEXT_SIZE = 60
CORNER_RADIUS = 10

TOGGLES = [
  {"n": "0", "param": "PutPrebuiltOn", "title": "Use Smart Prebuilt", "description": "Create a Prebuilt file and speed up booting. When this function is turned on, the booting speed is accelerated using the cache, and if you press the update button in the menu after modifying the code, or if you rebooted with the 'gi' command in the command window, remove it automatically and compile it."},
  {"n": "1", "param": "UFCModeEnabled", "title": "User-Friendly Control (UFC) Mode", "description": "OP activates with Main Cruise Switch, AutoRES while driving, Seperate Lat/Long and etc"},
  {"n": "2", "param": "LFAButtonEngagement", "title": "Enable LFA Button Engagement", "can_type": "CANFD", "description": "Use LFA Button to engage Openpilot Lateral"},
  {"n": "3", "param": "KisaEnableLogger", "title": "Enable Driving Log Record", "description": "Record the driving log locally for data analysis. Only loggers are activated and not uploaded to the server."},
  {"n": "4", "param": "KisaBlindSpotDetect", "title": "Display BSM Status", "description": "If a car is detected in the rear, it will be displayed on the screen."},
  {"n": "5", "param": "KisaVariableCruise", "title": "Cruise Button Spamming(VC)", "description": "Use the cruise button while using SCC to assist in acceleration and deceleration."},
  {"n": "6", "param": "KisaAutoResume", "title": "Use Auto Resume at Stop", "description": "It uses the automatic departure function when stopping while using SCC."},
  {"n": "7", "param": "CruiseGapAdjust", "title": "Change Cruise Gap at Stop", "description": "For a quick start when stopping, the cruise gap will be changed to 1 step, and after departure, it will return to the original cruise gap according to certain conditions."},
  {"n": "8", "param": "AutoEnable", "title": "Use Auto Engagement", "description": "If the cruise button status is standby (CRUISE indication only and speed is not specified) in the Disengagement state, activate the automatic Engagement."},
  {"n": "9", "param": "CruiseAutoRes", "title": "Use Auto RES while Driving", "description": "If the brake is applied while using the SCC and the standby mode is changed (CANCEL is not applicable), set it back to the previous speed when the brake pedal is released/accelerated pedal is operated. It operates when the cruise speed is set and the vehicle speed is more than 30 km/h or the car in front is recognized."},
  {"n": "10", "param": "StandstillResumeAlt", "title": "Standstill Resume Alternative", "can_type": "CAN", "description": "Turn this on, if auto resume doesn't work at standstill. some cars only(ex. GENESIS). before enable, try to adjust RES message counts above.(reboot required)"},
  {"n": "11", "param": "DepartChimeAtResume", "title": "Depart Chime at Resume", "description": "Use Chime for Resume. This can notify for you to get start while not using SCC."},
  {"n": "12", "param": "CruiseGapBySpdOn", "title": "Cruise Gap Change by Speed", "description": "Cruise Gap is changeable by vehicle speed."},
  {"n": "13", "param": "KISAEarlyStop", "title": "Early Slowdown with Gap", "description": "This feature may help your vehicle to stop early using Cruise Gap with value 4 when your car start to stop from model."},
  {"n": "14", "param": "KisaTurnSteeringDisable", "title": "Stop Steer Assist on Turn Signals", "description": "When driving below the lane change speed, the automatic steering is temporarily paused while the turn signals on."},
]

BUTTONS = [
  {"n": "0", "title": "Delete All Driving Logs", "text": "RUN", "callback": lambda: gui_app.set_modal_overlay(
    ConfirmDialog("Delete all saved driving logs. Do you want to proceed?", "OK"),
    callback=lambda result: os.system("rm -rf /data/media/0/realdata/*") if result == DialogResult.CONFIRM else None),
    "description": "This removes all driving logs under /data/media/0/realdata/."},
]

NUMERICS = [
  {"n": "0", "title": "CameraOffset[0.04]", "param": "CameraOffsetAdj", "min_value": -1.0, "max_value": 1.0, "step": 0.01, "decimals": 2, "value_type": "FLOAT", "description": "Adjust camera offset."},
  {"n": "1", "title": "LaneChange Speed", "param": "KisaLaneChangeSpeed", "min_value": 0, "max_value": 100, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {0: "OFF"}, "description": "On/Off lane change(push (-) btn till Off value) and set the lane changeable speed. This value can be kph or mph."},
  {"n": "2", "title": "Auto Engage Speed", "param": "AutoEnableSpeed", "min_value": -1, "max_value": 30, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"-1": "atDGear", "0": "atDepart"}, "description": "Set the automatic engage speed."},
  {"n": "3", "title": "RES Count at Standstill", "param": "RESCountatStandstill", "min_value": 1, "max_value": 50, "step": 1, "decimals": 0, "value_type": "INT", "description": "Comma Default: 25, this value cannot be acceptable at some cars. So adjust the number if you want to. It generates RES CAN messages when leadcar is moving. If departure is failed, increase the number. In opposite, if CAN error occurs, decrease the number."},
  {"n": "4", "title": "AutoRES Option", "param": "AutoResOption", "min_value": 0, "max_value": 2, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "CruiseSet", "1": "MaxSpeedSet", "2": "AUTO(LeadCar)"}, "description": "Sets the auto RES option. 1. Adjust the temporary cruise speed, 2. Adjust the set speed itself according to the presence or absence of a preceding car. 3. Adjust the cruise speed if there is a preceding car, and adjust the set speed if there is no preceding car. Please note that the automatic RES may not work well depending on the conditions."},
  {"n": "5", "title": "AutoRES Condition", "param": "AutoResCondition", "min_value": 0, "max_value": 1, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "RelBrake", "1": "OnGas"}, "description": "Sets the automatic RES condition. When the brake is released/operated when the accelerator pedal is operated."},
  {"n": "6", "title": "AutoRES Allow(sec)", "param": "AutoResLimitTime", "min_value": 0, "max_value": 60, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "NoLimit"}, "description": "Adjust the automatic RES allowance time. Automatic RES operates only within the set time after the cruise is released."},
  {"n": "7", "title": "AutoRES Delay(sec)", "param": "AutoRESDelay", "min_value": 0, "max_value": 20, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "No Delay"}, "description": "Give delay time to trigger for AutoRES while driving."},
  {"n": "8", "title": "LaneChange Delay", "param": "KisaAutoLaneChangeDelay", "min_value": 0, "max_value": 5, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "Nudge", "1": "RightNow", "2": "0.5sec", "3": "1sec", "4": "1.5sec", "5": "2secs"}, "description": "Set the delay time after turn signal operation before lane change."},
  {"n": "9", "title": "SafetyCam SignType", "param": "KisaSpeedLimitSignType", "min_value": 0, "max_value": 1, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "Circle", "1": "Rectangle"}, "description": "Select SafetyCam SignType (Circle/Rectangle)"},
  {"n": "10", "title": "Lateral Plan Mode", "param": "UseLegacyLaneModel", "min_value": 0, "max_value": 2, "step": 1, "decimals": 0, "value_type": "INT", "special_texts": {"0": "Model", "1": "MPC", "2": "Mix"}, "description": "1.Model(latest model path), 2.MPC(mpc path from post processing of model), 3.Mix(Model(high curvature), MPC(low curvature), interpolation value)"},
]


class KisaPilotLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    self._toggles, self._buttons, self._numeric = [], [], []
    self._param_mapping = []
    self._meta_mapping = {}

    self.can_type = str(self._params.get("KisaCANType", return_default=True)).strip().upper()
    self.scc_type = str(self._params.get("KisaSCCType", return_default=True)).strip().upper()

    # Toggle widgets
    for meta in TOGGLES:
      key = meta["param"]
      initial = self._params.get_bool(key)
      w = toggle_item(meta["title"], description=meta.get("description", ""), initial_state=initial,
        callback=lambda state, k=key: self._params.put_bool(k, state))
      self._toggles.append(w)
      self._param_mapping.append((key, w))
      self._meta_mapping[w] = meta

    # Button widgets
    for meta in BUTTONS:
      btn = button_item(meta["title"], meta["text"], description=meta.get("description", ""), callback=meta["callback"])
      self._buttons.append(btn)

    # Numeric widgets
    for meta in NUMERICS:
      key = meta["param"]
      val_type = meta.get("value_type", "INT")
      step = meta.get("step", 1)
      min_v = meta.get("min_value")
      max_v = meta.get("max_value")
      decimals = meta.get("decimals", 0)
      w = numeric_item(meta["title"], param_key=key, description=meta.get("description", ""), value_type=val_type, min_value=min_v, max_value=max_v, step=step, decimals=decimals, special_texts=meta.get("special_texts"))
      self._numeric.append(w)
      self._param_mapping.append((key, w))

    self._menu_titles = ["Lane", "Cruise", "Tuning", "Safety", "Advance"]
    self._menu_items = [
      # Lane
      [
        self._toggles[4],  # KisaBlindSpotDetect : bool
        self._numeric[1],  # KisaLaneChangeSpeed : int
        self._numeric[8],  # KisaAutoLaneChangeDelay : int
        self._toggles[14], # KisaTurnSteeringDisable : bool
      ],

      # Cruise
      [
        self._toggles[5],  # KisaVariableCruise : bool
        self._toggles[6],  # KisaAutoResume : bool
        self._numeric[3],  # RESCountatStandstill : int
        self._toggles[10], # StandstillResumeAlt : bool
        self._toggles[11], # DepartChimeAtResume : bool
        self._toggles[9],  # CruiseAutoRes : bool
        self._numeric[4],  # AutoResOption : int
        self._numeric[5],  # AutoResCondition : int
        self._numeric[6],  # AutoResLimitTime : int
        self._numeric[7],  # AutoRESDelay : int
        self._toggles[7],  # CruiseGapAdjust : bool
        self._toggles[13], # KISAEarlyStop : bool
        self._toggles[12], # CruiseGapBySpdOn : bool
      ],

      # Tuning
      [
        self._numeric[0], # CameraOffsetAdj : float
      ],

      # Safety
      [
        self._numeric[9], # KisaSpeedLimitSignType : int
      ],

      # Advance
      [
        self._toggles[0],  # PutPrebuiltOn : bool
        self._toggles[1],  # UFCModeEnabled : bool
        self._toggles[2],  # LFAButtonEngagement : bool
        self._toggles[3],  # KisaEnableLogger : bool
        self._buttons[0],  # Delete All Driving Logs
        self._toggles[8],  # AutoEnable : bool
        self._numeric[2],  # AutoEnableSpeed : int
        self._numeric[10], # UseLegacyLaneModel : int
      ],
    ]
    self._current_menu = 0

    self._scroller = Scroller(self._menu_items[self._current_menu], line_separator=True, spacing=0)
    self._press_offset_filter = FirstOrderFilter(0.0, 0.3, 1 / gui_app.target_fps)

    ui_state.add_offroad_transition_callback(self._update_items)

  def _set_menu(self, menu_index):
    self._current_menu = menu_index
    self._scroller._items = self._menu_items[menu_index]
    for item in self._scroller._items:
      item.set_touch_valid_callback(self._scroller.scroll_panel.is_touch_valid)
      item.show_event()
    self._scroller.scroll_panel.set_offset(0.0)
    self._update_items()

  def _handle_mouse_release(self, mouse_pos):
    total_width = self._rect.width
    button_width = (total_width - BUTTON_PADDING * (len(self._menu_titles) + 1)) / len(self._menu_titles)
    x = self._rect.x + BUTTON_PADDING
    y = self._rect.y + BUTTON_PADDING

    for idx, title in enumerate(self._menu_titles):
      btn_rect = rl.Rectangle(int(x), int(y), int(button_width), BUTTON_HEIGHT)
      if rl.check_collision_point_rec(mouse_pos, btn_rect):
        self._set_menu(idx)
        return True
      x += button_width + BUTTON_PADDING
    return False

  def _render(self, rect):
    self._rect = rect

    total_width = rect.width
    button_width = (total_width - BUTTON_PADDING * (len(self._menu_titles) + 1)) / len(self._menu_titles)
    x = rect.x + BUTTON_PADDING
    y = rect.y + BUTTON_PADDING

    for idx, title in enumerate(self._menu_titles):
      btn_rect = rl.Rectangle(int(x), int(y), int(button_width), BUTTON_HEIGHT)

      is_pressed = rl.is_mouse_button_down(rl.MOUSE_LEFT_BUTTON) and rl.check_collision_point_rec(rl.get_mouse_position(), btn_rect)
      target_offset = 5 if is_pressed else 0
      self._press_offset_filter.update(target_offset)
      btn_rect.y += self._press_offset_filter.x

      shadow_offset = 2 if is_pressed else 4
      shadow_alpha = 180 if is_pressed else 120
      shadow_rect = rl.Rectangle(btn_rect.x + shadow_offset, btn_rect.y + shadow_offset, btn_rect.width, btn_rect.height)
      rl.draw_rectangle_rounded(shadow_rect, CORNER_RADIUS, 8, (0, 0, 0, shadow_alpha))

      base_color = HIGHLIGHT_COLOR if idx == self._current_menu else DEFAULT_COLOR
      if is_pressed:
          base_color = (max(base_color[0]-80,0), max(base_color[1]-80,0), max(base_color[2]-80,0), base_color[3])
      rl.draw_rectangle_rounded(btn_rect, CORNER_RADIUS, 8, base_color)

      text_width = rl.measure_text(title, TEXT_SIZE)
      text_x = int(x + (button_width - text_width) / 2)
      text_y = int(btn_rect.y + (BUTTON_HEIGHT - TEXT_SIZE) / 2)
      rl.draw_text(title, text_x, text_y, TEXT_SIZE, TEXT_COLOR)

      x += button_width + BUTTON_PADDING

    scroll_rect = rl.Rectangle(rect.x, rect.y + BUTTON_HEIGHT + BUTTON_PADDING * 2, rect.width, rect.height - (BUTTON_HEIGHT + BUTTON_PADDING * 2))
    self._scroller.render(scroll_rect)

  def show_event(self):
    self._scroller.show_event()
    self._update_items()

  def _update_items(self):
    ui_state.update_params()
    for key, item in self._param_mapping:
      if hasattr(item, "action_item"):
        action = item.action_item
        if getattr(action, "value_type", None) == "BOOL":
          action.set_state(self._params.get_bool(key))
    for menu_items in self._menu_items:
      for item in menu_items:
        meta = self._meta_mapping.get(item, {})

        visible_condition_can = not meta.get("can_type") or meta["can_type"] == self.can_type
        visible_condition_scc = not meta.get("scc_type") or meta["scc_type"] == self.scc_type

        item.set_visible(visible_condition_can and visible_condition_scc)