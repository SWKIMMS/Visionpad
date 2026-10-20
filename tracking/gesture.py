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


class ThumbFoldGestureDetector:
    """2D thumb bend + palm proximity; no depth or index-tip pinch distance."""
    def __init__(self, config):
        self.stable_frames = max(1, int(config.get('stable_frames', 3)))
        cfg = config.get('thumb_fold', {})
        self.press_angle = float(cfg.get('press_angle_deg', 150))
        self.release_angle = float(cfg.get('release_angle_deg', 165))
        self.press_distance = float(cfg.get('press_palm_ratio', 0.65))
        self.release_distance = float(cfg.get('release_palm_ratio', 0.85))
        if not 0 < self.press_angle < self.release_angle <= 180:
            raise ValueError('Thumb angles must satisfy 0 < press < release <= 180')
        if not 0 < self.press_distance < self.release_distance:
            raise ValueError('Thumb distances must satisfy 0 < press < release')
        self.reset()

    def reset(self):
        self.state = 'hover'
        self.armed = False
        self.press_count = self.release_count = 0

    @staticmethod
    def angle(a, b, c):
        u = (a[0]-b[0], a[1]-b[1])
        v = (c[0]-b[0], c[1]-b[1])
        size = math.hypot(*u) * math.hypot(*v)
        if size <= 1e-6:
            raise ValueError('Degenerate thumb joints')
        return math.degrees(math.acos(max(-1, min(1, (u[0]*v[0]+u[1]*v[1])/size))))

    def result(self, event, angle=None, distance=None):
        return dict(state=self.state, event=event, pinch_ratio=None,
                    gesture_mode='thumb_fold', thumb_angle_deg=angle,
                    thumb_palm_ratio=distance, armed=self.armed)

    def hand_lost(self):
        event = 'release' if self.state == 'pressed' else None
        self.reset()
        return self.result(event)

    def update(self, hand):
        try:
            p = [(float(v[0]), float(v[1])) for v in hand['landmarks']]
            if len(p) != 21 or not all(math.isfinite(x) and math.isfinite(y) for x,y in p):
                raise ValueError('Invalid landmarks')
            scale = math.dist(p[5], p[17])
            if scale <= 1e-6: raise ValueError('Degenerate palm')
            center = tuple(sum(p[i][axis] for i in (0,5,9,13,17))/5 for axis in (0,1))
            distance = math.dist(p[4], center)/scale
            angle = min(self.angle(p[1],p[2],p[3]),self.angle(p[2],p[3],p[4]))
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            return self.hand_lost()
        folded = angle <= self.press_angle and distance <= self.press_distance
        opened = angle >= self.release_angle or distance >= self.release_distance
        event = 'drag' if self.state == 'pressed' else 'move'
        if not self.armed:
            self.release_count = self.release_count+1 if opened else 0
            if self.release_count >= self.stable_frames:
                self.armed = True
                self.release_count = 0
        elif self.state == 'hover':
            self.press_count = self.press_count+1 if folded else 0
            if self.press_count >= self.stable_frames:
                self.state, event = 'pressed', 'press'
                self.press_count = 0
        else:
            self.release_count = self.release_count+1 if opened else 0
            if self.release_count >= self.stable_frames:
                self.state, event = 'hover', 'release'
                self.release_count = 0
        return self.result(event, angle, distance)


def create_gesture_detector(config):
    mode = config.get('mode', 'thumb_fold')
    if mode == 'thumb_fold': return ThumbFoldGestureDetector(config)
    if mode == 'pinch': return PinchGestureDetector(config)
    raise ValueError(f'Unknown gesture mode: {mode}')
