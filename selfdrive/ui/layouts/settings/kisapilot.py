from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets import Widget, DialogResult
from openpilot.system.ui.widgets.list_view import toggle_item, button_item, numeric_item
from openpilot.system.ui.widgets.scroller import Scroller
from openpilot.system.ui.widgets.confirm_dialog import ConfirmDialog
from openpilot.system.ui.lib.application import gui_app
import os

# Description constants
TOGGLES = [
  {
    "param": "PutPrebuiltOn",
    "title": "Use Smart Prebuilt",
    "description": (
      "Create a Prebuilt file and speed up booting. "
      "When this function is turned on, the booting speed is accelerated using the cache, "
      "and if you press the update button in the menu after modifying the code, "
      "or if you rebooted with the 'gi' command in the command window, remove it automatically and compile it."
    ),
    "initial": lambda params: params.get_bool("PutPrebuiltOn"),
  },
  {
    "param": "UFCModeEnabled",
    "title": "User-Friendly Control (UFC) Mode",
    "description": (
      "OP activates with Main Cruise Switch, AutoRES while driving, "
      "Separate Lat/Long and etc."
    ),
    "initial": lambda params: params.get_bool("UFCModeEnabled"),
  },
  {
    "param": "LFAButtonEngagement",
    "title": "Enable LFA Button Engagement",
    "description": (
      "Use LFA Button to engage Openpilot Lateral"
    ),
    "initial": lambda params: params.get_bool("LFAButtonEngagement"),
  },
  {
    "param": "KisaEnableLogger",
    "title": "Enable Driving Log Record",
    "description": (
      "Record the driving log locally for data analysis. "
      "Only loggers are activated and not uploaded to the server."
    ),
    "initial": lambda params: params.get_bool("KisaEnableLogger"),
  },
]

BUTTONS = [
  {
    "title": "Delete All Driving Logs",
    "text": "RUN",
    "description": (
      "This removes all driving logs under /data/media/0/realdata/."
    ),
    "callback": lambda: gui_app.set_modal_overlay(
      ConfirmDialog("Delete all saved driving logs. Do you want to proceed?", "OK"),
      callback=lambda result: os.system("rm -rf /data/media/0/realdata/*") if result == DialogResult.CONFIRM else None
    ),
  },
]

NUMERICS = [
  {
    "title": "CameraOffset[0.04]",
    "param": "CameraOffsetAdj",
    "description": "Adjust camera offset.",
    "min_value": -1.0,
    "max_value": 1.0,
    "step": 0.01,
    "decimals": 2,
    "value_type": "FLOAT",
  },
]

class KisaPilotLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    self._toggles = []
    self._param_mapping = []
    self._buttons = []
    self._numeric = []

    for meta in TOGGLES:
      key = meta["param"]
      w = toggle_item(
        meta["title"],
        description=meta.get("description", ""),
        initial_state=meta["initial"](self._params),
        callback=lambda state, k=key: self._params.put_bool(k, state),
      )
      self._toggles.append(w)
      self._param_mapping.append((key, w))

    for meta in BUTTONS:
      btn = button_item(
        meta["title"],
        meta["text"],
        description=meta.get("description", ""),
        callback=meta["callback"]
      )
      self._buttons.append(btn)

    for meta in NUMERICS:
      key = meta["param"]
      val_type = meta.get("value_type", "INT")
      step = meta.get("step", 1)
      min_v = meta.get("min_value")
      max_v = meta.get("max_value")
      decimals = meta.get("decimals", 0)
      w = numeric_item(
        meta["title"],
        param_key=key,
        description=meta.get("description", ""),
        value_type=val_type,
        min_value=min_v,
        max_value=max_v,
        step=step,
        decimals=decimals
      )
      self._numeric.append(w)
      self._param_mapping.append((key, w))

    self._items_ordered = [
      self._toggles[0],
      self._toggles[1],
      self._toggles[2],
      self._toggles[3],
      self._buttons[0],
      self._numeric[0],
    ]

    self._scroller = Scroller(self._items_ordered, line_separator=True, spacing=0)
    ui_state.add_offroad_transition_callback(self._update_items)

  def _render(self, rect):
    self._scroller.render(rect)

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
        elif hasattr(action, "read_cached"):
          pass
      item.set_visible(True)