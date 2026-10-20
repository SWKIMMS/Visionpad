import time

import cv2
import numpy as np

from .aruco import ArucoPadTracker
from .filters import EMAFilter2D
from .gesture import PinchGestureDetector
from .hand import HandTracker
from .mapper import PadCoordinateMapper


class VisionPadTracker:

    def __init__(self, config):
        self.config = config

        self.aruco = ArucoPadTracker(
            config["aruco"]
        )

        self.hand = HandTracker(
            config["hand"]
        )

        self.mapper = PadCoordinateMapper(
            config["pad"],
            config["calibration"]
        )

        self.gesture = PinchGestureDetector(
            config["gesture"]
        )

        self.filter = EMAFilter2D(
            config.get(
                "smoothing",
                {}
            ).get(
                "alpha",
                0.35
            )
        )

        self.require_no_hand = bool(
            config.get(
                "calibration",
                {}
            ).get(
                "require_no_hand_for_update",
                True
            )
        )

        self.last_active_hand = None
        self.frame_count = 0
        self.last_time = time.monotonic()
        self.fps = 0.0


    def close(self):
        self.hand.close()


    def reset_calibration(self):
        self.mapper.reset()
        self.filter.reset()
        self.gesture.reset()
        self.last_active_hand = None


    def _select_active_hand(
        self,
        hands,
        timestamp
    ):
        candidates = []

        for hand in hands:
            mapped = self.mapper.map_camera_point(
                hand["index_tip"],
                timestamp
            )

            if mapped is None:
                continue

            if not mapped["inside"]:
                continue

            dx = (
                mapped["dot_x"]
                - (self.mapper.dot_width - 1) / 2.0
            )

            dy = (
                mapped["dot_y"]
                - (self.mapper.dot_height - 1) / 2.0
            )

            distance_to_center = (
                dx * dx + dy * dy
            )

            candidates.append(
                (
                    distance_to_center,
                    hand,
                    mapped
                )
            )

        if not candidates:
            return None, None

        candidates.sort(
            key=lambda item: item[0]
        )

        _, hand, mapped = candidates[0]

        return hand, mapped


    def _update_fps(self, now):
        delta = now - self.last_time
        self.last_time = now

        if delta <= 0:
            return

        instant_fps = 1.0 / delta

        if self.fps <= 0:
            self.fps = instant_fps
        else:
            self.fps = (
                self.fps * 0.9
                + instant_fps * 0.1
            )


    def process_frame(
        self,
        frame,
        draw=True
    ):
        now = time.monotonic()
        self.frame_count += 1
        self._update_fps(now)

        display = frame.copy()

        marker_result = self.aruco.detect(
            display,
            draw=draw
        )

        hands = self.hand.process(
            display,
            draw=draw
        )

        can_update_calibration = (
            marker_result["all_required"]
            and (
                not self.require_no_hand
                or len(hands) == 0
            )
        )

        calibration_updated = False

        if can_update_calibration:
            calibration_updated = (
                self.mapper.update(
                    marker_result["quad"],
                    now
                )
            )

        tracking_quality = (
            self.mapper.status(now)
        )

        active_hand = None
        mapped = None

        if tracking_quality != "lost":
            active_hand, mapped = (
                self._select_active_hand(
                    hands,
                    now
                )
            )

        hand_detected = (
            active_hand is not None
            and mapped is not None
        )

        gesture_result = None
        smooth_point = None

        if hand_detected:
            current_hand_label = (
                active_hand["handedness"]
            )

            if (
                self.last_active_hand is not None
                and current_hand_label
                    != self.last_active_hand
            ):
                self.filter.reset()
                self.gesture.reset()

            self.last_active_hand = (
                current_hand_label
            )

            smooth_point = self.filter.update(
                (
                    mapped["dot_x"],
                    mapped["dot_y"]
                )
            )

            gesture_result = (
                self.gesture.update(
                    active_hand
                )
            )

        else:
            self.filter.reset()
            self.last_active_hand = None
            gesture_result = (
                self.gesture.hand_lost()
            )

        pad_data = None

        if smooth_point is not None:
            smooth_x = max(
                0.0,
                min(
                    self.mapper.dot_width - 1,
                    float(smooth_point[0])
                )
            )

            smooth_y = max(
                0.0,
                min(
                    self.mapper.dot_height - 1,
                    float(smooth_point[1])
                )
            )

            pad_data = {
                "x": smooth_x,
                "y": smooth_y,
                "dot_x": int(
                    round(smooth_x)
                ),
                "dot_y": int(
                    round(smooth_y)
                )
            }

        camera_point = None

        if active_hand is not None:
            camera_point = {
                "x": float(
                    active_hand[
                        "index_tip"
                    ][0]
                ),
                "y": float(
                    active_hand[
                        "index_tip"
                    ][1]
                )
            }

        data = {
            "type": "tracking",
            "frame_count": self.frame_count,
            "marker_count": marker_result[
                "marker_count"
            ],
            "marker_ids": marker_result[
                "ids"
            ],
            "pad_detected": (
                tracking_quality != "lost"
            ),
            "calibration_updated": (
                calibration_updated
            ),
            "tracking_quality": tracking_quality,
            "hand_detected": hand_detected,
            "handedness": (
                active_hand[
                    "handedness"
                ]
                if active_hand
                else None
            ),
            "camera": camera_point,
            "pad": pad_data,
            "gesture": (
                gesture_result[
                    "state"
                ]
                if gesture_result
                else "hover"
            ),
            "gesture_event": (
                gesture_result[
                    "event"
                ]
                if gesture_result
                else None
            ),
            "pinch_ratio": (
                gesture_result[
                    "pinch_ratio"
                ]
                if gesture_result
                else None
            ),
            "fps": float(self.fps)
        }

        if draw:
            self._draw_debug_text(
                display,
                data
            )

        pad_view = self.make_pad_view(
            frame,
            data
        )

        return data, display, pad_view


    def make_pad_view(self, frame, data):
        warped = self.mapper.warp(
            frame
        )

        if warped is None:
            warped = np.zeros(
                (
                    self.mapper.canonical_height,
                    self.mapper.canonical_width,
                    3
                ),
                dtype=np.uint8
            )

        dot_width = self.mapper.dot_width
        dot_height = self.mapper.dot_height

        for x in range(dot_width):
            px = int(round(
                x
                / max(1, dot_width - 1)
                * (self.mapper.canonical_width - 1)
            ))

            if x % 5 == 0:
                cv2.line(
                    warped,
                    (px, 0),
                    (
                        px,
                        self.mapper.canonical_height - 1
                    ),
                    (55, 55, 55),
                    1
                )

        for y in range(dot_height):
            py = int(round(
                y
                / max(1, dot_height - 1)
                * (self.mapper.canonical_height - 1)
            ))

            if y % 5 == 0:
                cv2.line(
                    warped,
                    (0, py),
                    (
                        self.mapper.canonical_width - 1,
                        py
                    ),
                    (55, 55, 55),
                    1
                )

        if data["pad"] is not None:
            px = int(round(
                data["pad"]["x"]
                / max(1, dot_width - 1)
                * (self.mapper.canonical_width - 1)
            ))

            py = int(round(
                data["pad"]["y"]
                / max(1, dot_height - 1)
                * (self.mapper.canonical_height - 1)
            ))

            color = (
                (0, 0, 255)
                if data["gesture"]
                    == "pressed"
                else (0, 255, 255)
            )

            cv2.circle(
                warped,
                (px, py),
                9,
                color,
                -1,
                cv2.LINE_AA
            )

            label = (
                f"({data['pad']['x']:.1f}, "
                f"{data['pad']['y']:.1f}) "
                f"{data['gesture_event']}"
            )

            cv2.putText(
                warped,
                label,
                (
                    min(
                        px + 12,
                        self.mapper.canonical_width - 250
                    ),
                    max(25, py - 12)
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA
            )

        return warped


    def _draw_debug_text(
        self,
        frame,
        data
    ):
        lines = [
            f"Markers: {data['marker_count']} {data['marker_ids']}",
            f"Pad: {data['tracking_quality']}",
            f"Hand: {data['hand_detected']} {data['handedness']}",
            f"Gesture: {data['gesture']} / {data['gesture_event']}",
            f"Pinch: {data['pinch_ratio']}",
            f"FPS: {data['fps']:.1f}"
        ]

        if data["pad"] is not None:
            lines.append(
                f"Pad XY: "
                f"{data['pad']['x']:.2f}, "
                f"{data['pad']['y']:.2f}"
            )

            lines.append(
                f"Dot XY: "
                f"{data['pad']['dot_x']}, "
                f"{data['pad']['dot_y']}"
            )

        y = 28

        for line in lines:
            cv2.putText(
                frame,
                line,
                (15, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

            y += 27
