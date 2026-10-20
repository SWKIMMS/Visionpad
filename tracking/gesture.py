import math


class PinchGestureDetector:

    def __init__(self, config):
        self.press_ratio = float(
            config.get(
                "press_ratio",
                0.35
            )
        )

        self.release_ratio = float(
            config.get(
                "release_ratio",
                0.55
            )
        )

        self.stable_frames = max(
            1,
            int(
                config.get(
                    "stable_frames",
                    3
                )
            )
        )

        self.reset()


    def reset(self):
        self.state = "hover"
        self.press_count = 0
        self.release_count = 0


    def _distance(self, a, b):
        return math.hypot(
            float(a[0]) - float(b[0]),
            float(a[1]) - float(b[1])
        )


    def pinch_ratio(self, hand):
        pinch_distance = self._distance(
            hand["thumb_tip"],
            hand["index_tip"]
        )

        hand_scale = self._distance(
            hand["index_mcp"],
            hand["pinky_mcp"]
        )

        if hand_scale <= 1e-6:
            return 999.0

        return float(
            pinch_distance / hand_scale
        )


    def update(self, hand):
        ratio = self.pinch_ratio(
            hand
        )

        event = "move"

        if self.state == "hover":
            self.release_count = 0

            if ratio <= self.press_ratio:
                self.press_count += 1
            else:
                self.press_count = 0

            if (
                self.press_count
                >= self.stable_frames
            ):
                self.state = "pressed"
                self.press_count = 0
                event = "press"

        else:
            self.press_count = 0

            if ratio >= self.release_ratio:
                self.release_count += 1
            else:
                self.release_count = 0

            if (
                self.release_count
                >= self.stable_frames
            ):
                self.state = "hover"
                self.release_count = 0
                event = "release"
            else:
                event = "drag"

        return {
            "state": self.state,
            "event": event,
            "pinch_ratio": ratio
        }


    def hand_lost(self):
        event = None

        if self.state == "pressed":
            event = "release"

        self.reset()

        return {
            "state": "hover",
            "event": event,
            "pinch_ratio": None
        }
