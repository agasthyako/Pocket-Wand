"""Orientation maths.

World frame (after Recentre): +X right, +Y forward (towards the screen), +Z up.
Phone frame: +X right edge of the screen, +Y top of the phone, +Z out of the screen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Quaternion:
    w: float
    x: float
    y: float
    z: float

    @staticmethod
    def identity() -> Quaternion:
        return Quaternion(1.0, 0.0, 0.0, 0.0)

    @staticmethod
    def from_axis_angle(axis: tuple[float, float, float], degrees: float) -> Quaternion:
        half = math.radians(degrees) / 2
        s = math.sin(half)
        return Quaternion(math.cos(half), axis[0] * s, axis[1] * s, axis[2] * s)

    def __iter__(self):
        return iter((self.w, self.x, self.y, self.z))

    def __neg__(self) -> Quaternion:
        return Quaternion(-self.w, -self.x, -self.y, -self.z)

    def __mul__(self, o: Quaternion) -> Quaternion:
        return Quaternion(
            self.w * o.w - self.x * o.x - self.y * o.y - self.z * o.z,
            self.w * o.x + self.x * o.w + self.y * o.z - self.z * o.y,
            self.w * o.y - self.x * o.z + self.y * o.w + self.z * o.x,
            self.w * o.z + self.x * o.y - self.y * o.x + self.z * o.w,
        )

    def conjugate(self) -> Quaternion:
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def rotate(self, v: tuple[float, float, float]) -> tuple[float, float, float]:
        """Rotate a phone-frame vector into the world frame."""
        p = self * Quaternion(0.0, *v) * self.conjugate()
        return (p.x, p.y, p.z)

    def matrix(self) -> tuple[tuple[float, float, float], ...]:
        w, x, y, z = self
        return (
            (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
        )

    def euler(self) -> tuple[float, float, float]:
        """(yaw, pitch, roll) in degrees, applied yaw about Z, then pitch about X, then roll about Y.

        Yaw is heading (positive turns left), pitch tips the top of the phone up,
        roll twists the phone around its long edge.
        """
        r = self.matrix()
        pitch = math.asin(max(-1.0, min(1.0, r[2][1])))
        yaw = math.atan2(-r[0][1], r[1][1])
        roll = math.atan2(-r[2][0], r[2][2])
        return (math.degrees(yaw), math.degrees(pitch), math.degrees(roll))


_Z = (0.0, 0.0, 1.0)
_X = (1.0, 0.0, 0.0)
_Y = (0.0, 1.0, 0.0)


def from_device_angles(alpha: float, beta: float, gamma: float) -> Quaternion:
    """Convert browser DeviceOrientationEvent angles (degrees) to a quaternion.

    Per the W3C spec the rotation is Z(alpha) then X(beta) then Y(gamma), intrinsic.
    """
    return (
        Quaternion.from_axis_angle(_Z, alpha)
        * Quaternion.from_axis_angle(_X, beta)
        * Quaternion.from_axis_angle(_Y, gamma)
    )


def recentre_offset(raw: Quaternion) -> Quaternion:
    """The heading-only correction that makes the phone's current facing count as forward.

    Facing is the direction the top of the phone points; when the phone stands
    upright that direction is vertical, so the back of the phone is used instead.
    """
    top = raw.rotate((0.0, 1.0, 0.0))
    back = raw.rotate((0.0, 0.0, -1.0))
    fx, fy, _ = top if math.hypot(top[0], top[1]) > 0.5 else back
    heading = math.degrees(math.atan2(-fx, fy))
    return Quaternion.from_axis_angle(_Z, -heading)
