"""Tech demo: a 3D phone on screen that copies the real phone's rotation 1:1."""

from __future__ import annotations

import math

import pygame
import qrcode

from . import Room

W, H = 960, 720
BG = (14, 17, 22)
FG = (232, 237, 243)
DIM = (138, 150, 166)
BODY = (120, 130, 145)
SCREEN = (40, 110, 160)
SCREEN_HOT = (247, 37, 133)
LIGHT = (0.3, -0.5, 0.8)

# Phone half-sizes in phone frame: X across the screen, Y along the phone, Z out of the screen.
HX, HY, HZ = 0.38, 0.78, 0.05
CAMERA = (0.0, -3.2, 1.9)
FOCAL = 760


def run(tunnel: bool = True) -> None:
    room = Room(tunnel=tunnel)
    pygame.init()
    pygame.display.set_caption("PocketWand demo")
    screen = pygame.display.set_mode((W, H))
    font = pygame.font.SysFont("menlo,consolas,monospace", 18)
    big = pygame.font.SysFont("helvetica,arial,sans", 28)
    qr = _qr_surface(room.join_url, 10)
    clock = pygame.time.Clock()
    view = _camera_basis(CAMERA, (0.0, 0.0, 0.0))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q)):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                room.controller(0).recenter()

        c = room.controller(0)
        screen.fill(BG)
        if c.connected:
            _draw_phone(screen, view, c.orientation.matrix(), c.button)
            yaw, pitch, roll = c.euler
            lines = [
                f"slot {c.slot}   button {'DOWN' if c.button else 'up'}",
                f"yaw {yaw:7.1f}   pitch {pitch:7.1f}   roll {roll:7.1f}",
                f"{clock.get_fps():.0f} fps   R: recentre   Q: quit",
            ]
            for i, text in enumerate(lines):
                screen.blit(font.render(text, True, DIM), (20, 20 + i * 24))
        else:
            title = big.render("Scan with your phone camera", True, FG)
            screen.blit(title, title.get_rect(center=(W // 2, 70)))
            screen.blit(qr, qr.get_rect(center=(W // 2, H // 2)))
            url = font.render(room.join_url, True, DIM)
            screen.blit(url, url.get_rect(center=(W // 2, H - 60)))

        pygame.display.flip()
        clock.tick(120)

    pygame.quit()
    room.close()


def _draw_phone(screen, view, rot, hot: bool) -> None:
    corners = [(sx * HX, sy * HY, sz * HZ) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    world = [_mat_vec(rot, p) for p in corners]
    cam = [_to_camera(view, p) for p in world]

    def idx(sx, sy, sz):
        return ((sx > 0) << 2) | ((sy > 0) << 1) | (sz > 0)

    # Each face: (corner indices wound counter-clockwise from outside, phone-frame normal)
    faces = [
        ([idx(-1, -1, 1), idx(1, -1, 1), idx(1, 1, 1), idx(-1, 1, 1)], (0, 0, 1)),
        ([idx(-1, 1, -1), idx(1, 1, -1), idx(1, -1, -1), idx(-1, -1, -1)], (0, 0, -1)),
        ([idx(1, -1, -1), idx(1, 1, -1), idx(1, 1, 1), idx(1, -1, 1)], (1, 0, 0)),
        ([idx(-1, -1, 1), idx(-1, 1, 1), idx(-1, 1, -1), idx(-1, -1, -1)], (-1, 0, 0)),
        ([idx(-1, 1, 1), idx(1, 1, 1), idx(1, 1, -1), idx(-1, 1, -1)], (0, 1, 0)),
        ([idx(-1, -1, -1), idx(1, -1, -1), idx(1, -1, 1), idx(-1, -1, 1)], (0, -1, 0)),
    ]

    drawn = []
    for quad, normal in faces:
        n = _mat_vec(rot, normal)
        centre = [sum(world[i][k] for i in quad) / 4 for k in range(3)]
        to_cam = [CAMERA[k] - centre[k] for k in range(3)]
        if _dot(n, to_cam) <= 0:
            continue  # facing away
        depth = sum(cam[i][2] for i in quad) / 4
        drawn.append((depth, quad, n, normal))

    for depth, quad, n, normal in sorted(drawn, reverse=True):
        shade = 0.35 + 0.65 * max(0.0, _dot(n, _normalise(LIGHT)))
        pts = [_project(cam[i]) for i in quad]
        pygame.draw.polygon(screen, _scale(BODY, shade), pts)
        if normal == (0, 0, 1):
            _draw_display(screen, view, rot, SCREEN_HOT if hot else SCREEN, shade)


def _draw_display(screen, view, rot, colour, shade) -> None:
    """The glass on the front, plus a notch so you can tell the top from the bottom."""
    z = HZ + 0.001
    glass = [(-HX * 0.88, -HY * 0.92, z), (HX * 0.88, -HY * 0.92, z), (HX * 0.88, HY * 0.86, z), (-HX * 0.88, HY * 0.86, z)]
    pygame.draw.polygon(screen, _scale(colour, shade), [_project(_to_camera(view, _mat_vec(rot, p))) for p in glass])
    notch = [(-0.1, HY * 0.9, z), (0.1, HY * 0.9, z), (0.1, HY * 0.95, z), (-0.1, HY * 0.95, z)]
    pygame.draw.polygon(screen, (20, 20, 20), [_project(_to_camera(view, _mat_vec(rot, p))) for p in notch])


def _qr_surface(data: str, cell: int) -> pygame.Surface:
    qr = qrcode.QRCode(border=4)  # the full 4-module quiet zone; iOS Camera ignores codes with less
    qr.add_data(data)
    matrix = qr.get_matrix()
    size = len(matrix) * cell
    surf = pygame.Surface((size, size))
    surf.fill((255, 255, 255))
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                surf.fill((0, 0, 0), (x * cell, y * cell, cell, cell))
    return surf


def _camera_basis(eye, target):
    forward = _normalise([target[k] - eye[k] for k in range(3)])
    right = _normalise(_cross(forward, (0.0, 0.0, 1.0)))
    up = _cross(right, forward)
    return right, up, forward


def _to_camera(view, p):
    right, up, forward = view
    rel = [p[k] - CAMERA[k] for k in range(3)]
    return (_dot(rel, right), _dot(rel, up), _dot(rel, forward))


def _project(p):
    x, y, z = p
    z = max(z, 0.01)
    return (W / 2 + FOCAL * x / z, H / 2 - FOCAL * y / z)


def _mat_vec(m, v):
    return tuple(m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] for r in range(3))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normalise(v):
    length = math.sqrt(_dot(v, v))
    return tuple(x / length for x in v)


def _scale(colour, k):
    return tuple(min(255, int(c * k)) for c in colour)
