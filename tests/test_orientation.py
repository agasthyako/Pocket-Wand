import math

import pytest

from pocketwand.orientation import Quaternion, from_device_angles, recentre_offset


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def same_rotation(q1, q2, tol=1e-6):
    # q and -q are the same rotation
    return close(tuple(q1), tuple(q2), tol) or close(tuple(q1), tuple(-q2), tol)


def test_identity_when_phone_flat_facing_north():
    assert same_rotation(from_device_angles(0, 0, 0), Quaternion.identity())


@pytest.mark.parametrize(
    "alpha,beta,gamma",
    [(30, 0, 0), (0, 45, 0), (0, 0, -60), (120, 30, -20), (350, -70, 85)],
)
def test_euler_round_trips_device_angles(alpha, beta, gamma):
    yaw, pitch, roll = from_device_angles(alpha, beta, gamma).euler()
    assert yaw == pytest.approx(alpha if alpha <= 180 else alpha - 360)
    assert pitch == pytest.approx(beta)
    assert roll == pytest.approx(gamma)


def test_rotating_vector_matches_right_hand_rule():
    # 90 degrees about Z (alpha) turns the phone's top (+Y) to point west (-X)
    q = from_device_angles(90, 0, 0)
    assert close(q.rotate((0, 1, 0)), (-1, 0, 0))


def test_recentre_makes_current_heading_forward():
    raw = from_device_angles(73, 20, 10)
    offset = recentre_offset(raw)
    yaw, pitch, roll = (offset * raw).euler()
    assert yaw == pytest.approx(0, abs=1e-6)
    # recentring only removes heading; tilt stays true to gravity
    assert pitch == pytest.approx(20)
    assert roll == pytest.approx(10)


def test_recentre_with_phone_upright_uses_back_of_phone():
    # phone standing up (top pointing at the sky), screen facing the user, turned 40 degrees
    raw = from_device_angles(40, 90, 0)
    forward = (recentre_offset(raw) * raw).rotate((0, 0, -1))
    assert close(forward, (0, 1, 0), 1e-6)
