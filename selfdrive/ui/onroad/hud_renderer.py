import pyray as rl
from dataclasses import dataclass
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.exp_button import ExpButton
from openpilot.selfdrive.ui.ui_state import ui_state, UIStatus
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

# kisa
from openpilot.selfdrive.ui.onroad.kisa_button import KisaButton
import math

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

    self._kisa_button: KisaButton = KisaButton(UI_CONFIG.button_size, UI_CONFIG.wheel_icon_size)
    self.img_width = 200
    self.img_speed_cam = gui_app.texture("addon/img/img_speed_cam.png", self.img_width, self.img_width)
    self.img_police_car = gui_app.texture("addon/img/img_police_car.png", self.img_width, self.img_width)

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

    self._draw_blinkers(rect)
    self._draw_speed_limit_sign(rect)

    button_x = rect.x + rect.width - UI_CONFIG.border_size - UI_CONFIG.button_size
    button_y = rect.y + UI_CONFIG.border_size
    self._exp_button.render(rl.Rectangle(button_x, button_y, UI_CONFIG.button_size, UI_CONFIG.button_size))

    self._kisa_button.render(rl.Rectangle(button_x, button_y + 960 - UI_CONFIG.button_size, UI_CONFIG.button_size, UI_CONFIG.button_size))

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
    s = ui_state

    # speed text
    speed_text = str(round(self.speed))
    act_accel = s.a_req_value if (not s.has_longitudinal_control) else s.accel

    def clamp(v, lo, hi):
      return lo if v < lo else (hi if v > hi else v)

    gas_opacity = clamp(act_accel * 255, 0, 255)
    brake_opacity = clamp(abs(act_accel * 175), 0, 255)

    if s.brakePress:
      speed_color = rl.Color(255, 0, 0, 255)
    elif s.brakeLights and speed_text == "0":
      speed_color = rl.Color(201, 34, 49, 100)
    elif s.gasPress:
      speed_color = rl.Color(0, 240, 0, 255)
    elif (act_accel < 0 and act_accel > -5.0):
      r = clamp(255 - int(abs(act_accel * 8)), 0, 255)
      g = clamp(255 - int(brake_opacity), 0, 255)
      b = clamp(255 - int(brake_opacity), 0, 255)
      speed_color = rl.Color(r, g, b, 255)
    elif (act_accel > 0 and act_accel < 3.0):
      r = clamp(255 - int(gas_opacity), 0, 255)
      g = clamp(255 - int(act_accel * 10), 0, 255)
      b = clamp(255 - int(gas_opacity), 0, 255)
      speed_color = rl.Color(r, g, b, 255)
    else:
      speed_color = COLORS.white

    set_speed_width = UI_CONFIG.set_speed_width_metric if ui_state.is_metric else UI_CONFIG.set_speed_width_imperial
    x = rect.x + 50 + (UI_CONFIG.set_speed_width_imperial - set_speed_width) // 2
    y = rect.y + 1020 - 230
    speed_pos = rl.Vector2(x, y)
    rl.draw_text_ex(self._font_bold, speed_text, speed_pos, FONT_SIZES.current_speed + 10, 0, speed_color)

    if s.brakeLights:
      brake_x = x + 5
      brake_y = y + 195
      brake_rect = rl.Rectangle(brake_x, brake_y, set_speed_width, 25)
      rl.draw_rectangle_rounded(brake_rect, 1.0, 32, rl.Color(255, 0, 0, 180))
      text_size = rl.measure_text_ex(self._font_bold, "BRAKE LIGHT", 20, 0)
      text_x = brake_rect.x + (brake_rect.width - text_size.x*1.2) / 2
      text_y = brake_rect.y + (brake_rect.height - text_size.y*1.2) / 2
      rl.draw_text_ex(self._font_bold, "BRAKE LIGHT", rl.Vector2(text_x, text_y), 20, 0, COLORS.white_translucent)

    # unit_text = "KPH" if ui_state.is_metric else "MPH"
    # unit_text_size = measure_text_cached(self._font_medium, unit_text, FONT_SIZES.speed_unit)
    # unit_pos = rl.Vector2(rect.x + rect.width / 2 - unit_text_size.x / 2, 290 - unit_text_size.y / 2)
    # rl.draw_text_ex(self._font_medium, unit_text, unit_pos, FONT_SIZES.speed_unit, 0, COLORS.white_translucent)

  def _draw_blinkers(self, rect: rl.Rectangle) -> None:
    """Draw KisaPilot-style blinkers."""
    if not ui_state.leftBlinker and not ui_state.rightBlinker:
      return

    t = rl.get_time()
    center_x = rect.x + rect.width // 2
    center_y = rect.y + 200
    size, thickness, freq, sway_amp = 100, 40, 6, 20
    sway = sway_amp * math.sin(t * freq)
    count, spacing = 5, 90
    base_color = rl.Color(230, 165, 0, 230)
    overlap = 0.25

    def draw_chevron(x, y, direction="right", alpha=255):
      delta = size * overlap
      if direction == "right":
        points = [(x - size + delta, y - size + delta), (x, y), (x - size + delta, y + size - delta)]
      else:
        points = [(x + size - delta, y - size + delta), (x, y), (x + size - delta, y + size - delta)]
      color = rl.Color(base_color.r, base_color.g, base_color.b, alpha)
      for i in range(2):
        rl.draw_line_ex(points[i], points[i+1], thickness, color)
        rl.draw_circle(int(points[i][0]), int(points[i][1]), thickness/2, color)
        rl.draw_circle(int(points[i+1][0]), int(points[i+1][1]), thickness/2, color)

    def draw_sequence(x, y, direction="right"):
      for i in range(count):
        offset = i * spacing
        alpha = int(((math.sin(t * freq - (count - 1 - i) * 0.5) + 1) / 2) * base_color.a)
        pos_x = x - offset if direction == "right" else x + offset
        draw_chevron(pos_x, y, direction, alpha)

    if ui_state.leftBlinker:
      draw_sequence(center_x - 700 + sway, center_y, "left")
    if ui_state.rightBlinker:
      draw_sequence(center_x + 700 - sway, center_y, "right")

  def _draw_speed_limit_sign(self, rect: rl.Rectangle) -> None:
    """Draw KisaPilot-style speed limit sign."""
    s_center_x = rect.x + UI_CONFIG.border_size + 340
    s_center_y = rect.y + 1020 - 335
    d_center_y = s_center_y - 160

    diameters = (210, 180, 202)
    rects = {
      "inner": rl.Rectangle(s_center_x - diameters[1]//2, s_center_y - diameters[1]//2, diameters[1], diameters[1]),
      "main":  rl.Rectangle(s_center_x - diameters[0]//2, s_center_y - diameters[0]//2, diameters[0], diameters[0]),
      "outer": rl.Rectangle(s_center_x - diameters[2]//2, s_center_y - diameters[2]//2, diameters[2], diameters[2]),
      "dist":  rl.Rectangle(s_center_x - 110, d_center_y - 35, 220, 70),
    }

    sl_opacity = 3 if ui_state.sl_decel_off else (2 if ui_state.pause_spdlimit else 1)
    # limit_spd, dist = ui_state.limitSpeedCamera, ui_state.limitSpeedCameraDist
    limit_spd, dist = 30, 300

    if limit_spd <= 21 and (dist == 0 or ui_state.navi_select not in [2, 4]):
      return

    alpha = lambda v: int(255 / sl_opacity * v)

    visual_offset = 1.2

    if ui_state.speedlimit_signtype:
      rl.draw_rectangle_rounded(rects["inner"], 0.2, 8, rl.Color(255, 255, 255, alpha(1)))
      rl.draw_rectangle_rounded_lines_ex(rects["main"], 0.2, 8, 12, rl.Color(0, 0, 0, alpha(1)))
      rl.draw_rectangle_rounded_lines_ex(rects["outer"], 0.2, 8, 10, rl.Color(255, 255, 255, alpha(1)))
      cx, cy = rects["outer"].x + rects["outer"].width / 2, rects["outer"].y
      rl.draw_text_ex(self._font_bold, "SPEED", rl.Vector2(cx - 70, cy + 10), 42, 0, rl.BLACK)
      rl.draw_text_ex(self._font_bold, "LIMIT", rl.Vector2(cx - 60, cy + 48), 42, 0, rl.BLACK)
      font_size = 110 if limit_spd < 100 else 90
      text = str(int(limit_spd))
      text_size = rl.measure_text_ex(self._font_bold, text, font_size, 0)
      text_x = rects["outer"].x + (rects["outer"].width - text_size.x*visual_offset) / 2
      text_y = rects["outer"].y + (rects["outer"].height - text_size.y*visual_offset) / 2
      rl.draw_text_ex(self._font_bold, text, rl.Vector2(text_x-4, text_y+40), font_size, 0, rl.BLACK)
    else:
      cx, cy = int(rects["inner"].x + rects["inner"].width / 2), int(rects["inner"].y + rects["inner"].height / 2)
      rl.draw_circle(cx, cy, int(diameters[0] / 2), rl.RED)
      rl.draw_circle(cx, cy, int(diameters[1] / 2), rl.WHITE)
      text = str(int(limit_spd))
      font_size = 110 if limit_spd < 100 else 90
      text_size = rl.measure_text_ex(self._font_bold, text, font_size, 0)
      text_x = rects["inner"].x + (rects["inner"].width - text_size.x*visual_offset) / 2
      text_y = rects["inner"].y + (rects["inner"].height - text_size.y*visual_offset) / 2
      rl.draw_text_ex(self._font_bold, text, rl.Vector2(text_x, text_y), font_size, 0, rl.BLACK)

    alert_images = {1: self.img_speed_cam, 2: self.img_police_car}
    if ui_state.ewazealertid in alert_images:
      img = alert_images[ui_state.ewazealertid]
      icon_x = s_center_x - self.img_width // 2 + 210
      icon_y = s_center_y - self.img_width // 2
      icon_rect = rl.Rectangle(icon_x, icon_y, self.img_width, self.img_width)
      source_rect = rl.Rectangle(0, 0, img.width, img.height)
      rl.draw_texture_pro(img, source_rect, icon_rect, rl.Vector2(0, 0), 0, rl.WHITE)

    if dist == 0:
      return

    opacity = max(0, min(255, int(((600 - dist) * 0.425) / sl_opacity))) if dist <= 600 else 0
    rl.draw_rectangle_rounded(rects["dist"], 0.35, 32, rl.Color(255, 0, 0, opacity))
    rl.draw_rectangle_rounded_lines_ex(rects["dist"], 0.35, 32, 6, COLORS.white_translucent)

    if ui_state.is_metric:
      dist_text = (
        f"{dist:.0f}m" if dist < 1000 else
        f"{dist/1000:.2f}km" if dist < 10000 else
        f"{dist/1000:.1f}km"
      )
    else:
      if getattr(ui_state, "ewazealertextend", False):
        dist_text = "Limit"
      else:
        dist_ft = dist * 3.28084
        dist_text = f"{dist_ft:.0f}ft" if dist_ft < 1000 else f"{dist * 0.000621:.2f}mi"

    font_size = 55
    text_size = rl.measure_text_ex(self._font_bold, dist_text, font_size, 0)
    text_x = rects["dist"].x + (rects["dist"].width - text_size.x*visual_offset) / 2
    text_y = rects["dist"].y + (rects["dist"].height - text_size.y*visual_offset) / 2
    rl.draw_text_ex(self._font_bold, dist_text, rl.Vector2(text_x, text_y), font_size, 0, rl.WHITE)


