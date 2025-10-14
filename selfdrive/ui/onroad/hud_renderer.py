import pyray as rl
from dataclasses import dataclass
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.exp_button import ExpButton
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

# Constants
SET_SPEED_NA = 255
KM_TO_MILE = 0.621371
CRUISE_DISABLED_CHAR = '–'


@dataclass(frozen=True)
class UIConfig:
  header_height: int = 300
  border_size: int = 30
  button_size: int = 192
  set_speed_width_metric: int = 200
  set_speed_width_imperial: int = 172
  set_speed_height: int = 204
  wheel_icon_size: int = 144


@dataclass(frozen=True)
class FontSizes:
  current_speed: int = 176
  speed_unit: int = 66
  max_speed: int = 40
  set_speed: int = 90


@dataclass(frozen=True)
class Colors:
  white: rl.Color = rl.WHITE
  disengaged: rl.Color = rl.Color(145, 155, 149, 255)
  override: rl.Color = rl.Color(145, 155, 149, 255)  # Added
  engaged: rl.Color = rl.Color(128, 216, 166, 255)
  disengaged_bg: rl.Color = rl.Color(0, 0, 0, 153)
  override_bg: rl.Color = rl.Color(145, 155, 149, 204)
  engaged_bg: rl.Color = rl.Color(128, 216, 166, 204)
  grey: rl.Color = rl.Color(166, 166, 166, 255)
  dark_grey: rl.Color = rl.Color(114, 114, 114, 255)
  black_translucent: rl.Color = rl.Color(0, 0, 0, 166)
  white_translucent: rl.Color = rl.Color(255, 255, 255, 200)
  border_translucent: rl.Color = rl.Color(255, 255, 255, 75)
  header_gradient_start: rl.Color = rl.Color(0, 0, 0, 114)
  header_gradient_end: rl.Color = rl.BLANK
  # kisa
  green_translucent: rl.Color = rl.Color(0, 200, 0, 100)
  blue_translucent: rl.Color = rl.Color(0, 140, 255, 120)
  ochre_translucent: rl.Color = rl.Color(204, 153, 0, 128)
  orange_translucent: rl.Color = rl.Color(204, 120, 0, 128)


UI_CONFIG = UIConfig()
FONT_SIZES = FontSizes()
COLORS = Colors()


class HudRenderer(Widget):
  def __init__(self):
    super().__init__()
    """Initialize the HUD renderer."""
    self.is_cruise_set: bool = False
    self.is_cruise_available: bool = True
    self.set_speed: float = SET_SPEED_NA
    self.speed: float = 0.0
    self.v_ego_cluster_seen: bool = False

    self._font_semi_bold: rl.Font = gui_app.font(FontWeight.SEMI_BOLD)
    self._font_bold: rl.Font = gui_app.font(FontWeight.BOLD)
    self._font_medium: rl.Font = gui_app.font(FontWeight.MEDIUM)

    self._exp_button: ExpButton = ExpButton(UI_CONFIG.button_size, UI_CONFIG.wheel_icon_size)

  def _update_state(self) -> None:
    """Update HUD state based on car state and controls state."""
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self.is_cruise_set = False
      self.set_speed = SET_SPEED_NA
      self.speed = 0.0
      return

    controls_state = sm['controlsState']
    car_state = sm['carState']

    v_cruise_cluster = car_state.vCruiseCluster
    self.set_speed = (
      controls_state.vCruiseDEPRECATED if v_cruise_cluster == 0.0 else v_cruise_cluster
    )
    self.is_cruise_set = 0 < self.set_speed < SET_SPEED_NA
    self.is_cruise_available = self.set_speed != -1

    if self.is_cruise_set and not ui_state.is_metric:
      self.set_speed *= KM_TO_MILE

    v_ego_cluster = car_state.vEgoCluster
    self.v_ego_cluster_seen = self.v_ego_cluster_seen or v_ego_cluster != 0.0
    v_ego = v_ego_cluster if self.v_ego_cluster_seen else car_state.vEgo
    speed_conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    self.speed = max(0.0, v_ego * speed_conversion)

  def _render(self, rect: rl.Rectangle) -> None:
    """Render HUD elements to the screen."""
    # Draw the header background
    rl.draw_rectangle_gradient_v(
      int(rect.x),
      int(rect.y),
      int(rect.width),
      UI_CONFIG.header_height,
      COLORS.header_gradient_start,
      COLORS.header_gradient_end,
    )

    if self.is_cruise_available:
      self._draw_set_speed(rect)

    self._draw_current_speed(rect)

    button_x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size
    button_y = rect.y + 1020 - UI_CONFIG.border_size - UI_CONFIG.button_size
    self._exp_button.render(rl.Rectangle(button_x, button_y, UI_CONFIG.button_size, UI_CONFIG.button_size))

  def user_interacting(self) -> bool:
    return self._exp_button.is_pressed

  def _draw_set_speed(self, rect: rl.Rectangle) -> None:
    """Draw the MAX speed indicator box."""
    set_speed_width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    x = rect.x + 60 + (UI_CONFIG.set_speed_width_imperial - set_speed_width) // 2
    y = rect.y - 45 + 1020 - UI_CONFIG.set_speed_height - 185

    set_speed_rect = rl.Rectangle(x, y, set_speed_width, UI_CONFIG.set_speed_height + 2)

    if ui_state.exp_mode_temp:
      pen_color = COLORS.engaged
    else:
      pen_color = COLORS.white_translucent

    if ui_state.limitSpeedCamera > 18 and self.speed > ui_state.ctrl_speed+1.5:
      bg_brush = COLORS.ochre_translucent
    elif ui_state.limitSpeedCamera > 18:
      bg_brush = COLORS.green_translucent
    elif ui_state.cruiseAccStatus:
      bg_brush = COLORS.blue_translucent
    else:
      bg_brush = COLORS.black_translucent

    # Draw rounded rect background + border
    rl.draw_rectangle_rounded(set_speed_rect, 0.35, 32, bg_brush)
    rl.draw_rectangle_rounded_lines_ex(set_speed_rect, 0.35, 32, 6, pen_color)

    # mid line
    line_y = y + UI_CONFIG.set_speed_height // 2 - 7
    start = rl.Vector2(x + 35, line_y)
    end = rl.Vector2(x + set_speed_width - 35, line_y)
    try:
      rl.draw_line(start, end, 6)
    except Exception:
      rl.draw_rectangle_rounded(rl.Rectangle(start.x, start.y - 3, end.x - start.x, 6), 0.1, 3, COLORS.white)

    if ui_state.ekisaroadlimitspeed > 21:
      setSpeedStr = str(int(ui_state.ekisaroadlimitspeed + ui_state.road_spdlimit_offset))
    elif ui_state.ewazeroadspeedlimit > 19:
      setSpeedStr = str(int(ui_state.ewazeroadspeedlimit))
    elif ui_state.ospeedLimit > 19:
      setSpeedStr = str(int(ui_state.ospeedLimit))
    else:
      setSpeedStr = str(round(self.set_speed)) if 0 < self.set_speed < 254 else CRUISE_DISABLED_CHAR

    ctrl_speed = ui_state.ctrl_speed
    top_text = str(int(ctrl_speed)) if ctrl_speed > 1 else setSpeedStr

    # Draw top big text
    top_font_size = 80
    top_text_w = measure_text_cached(self._font_semi_bold, top_text, top_font_size).x
    rl.draw_text_ex(self._font_semi_bold, top_text, rl.Vector2(x + (set_speed_width - top_text_w) / 2, y), top_font_size, 0, COLORS.white)

    # bottom set speed indicator
    if not ui_state.op_long_enabled:
      bottom_text = str(int(ui_state.vSetDis)) if ui_state.cruiseAccStatus else CRUISE_DISABLED_CHAR
    else:
      bottom_text = setSpeedStr if ui_state.cruiseAccStatus else CRUISE_DISABLED_CHAR

    bottom_font_size = FONT_SIZES.set_speed + 5
    bottom_text_w = measure_text_cached(self._font_bold, bottom_text, bottom_font_size).x
    rl.draw_text_ex(self._font_bold, bottom_text, rl.Vector2(x + (set_speed_width - bottom_text_w) / 2, y + 90), bottom_font_size, 0, COLORS.white)

    # btn spamming indicator
    if ui_state.btn_pressing > 0:
      rl.draw_rectangle_rounded(rl.Rectangle((x + 22) - 8, (y + UI_CONFIG.set_speed_height // 2 + 7) - 8, 16, 16), 0.5, 8, COLORS.white)

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    """Draw the current vehicle speed and unit."""
    speed_text = str(round(self.speed))
    speed_text_size = measure_text_cached(self._font_bold, speed_text, FONT_SIZES.current_speed + 10)

    set_speed_width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    x = rect.x + 50 + (UI_CONFIG.set_speed_width_imperial - set_speed_width) // 2
    y = rect.y + 1020 - 230
    speed_pos = rl.Vector2(x, y)
    rl.draw_text_ex(self._font_bold, speed_text, speed_pos, FONT_SIZES.current_speed + 10, 0, COLORS.white)

    # unit_text = "KPH" if ui_state.is_metric else "MPH"
    # unit_text_size = measure_text_cached(self._font_medium, unit_text, FONT_SIZES.speed_unit)
    # unit_pos = rl.Vector2(rect.x + rect.width / 2 - unit_text_size.x / 2, 290 - unit_text_size.y / 2)
    # rl.draw_text_ex(self._font_medium, unit_text, unit_pos, FONT_SIZES.speed_unit, 0, COLORS.white_translucent)
