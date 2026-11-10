"""Small math helpers shared by the score, the reactor and the preview port."""
import math


def clamp(x, a=0.0, b=1.0):
    return min(b, max(a, x))


def ease(x):
    """Smoothstep from 0 to 1."""
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, k):
    return a + (b - a) * k


def pulse(beats):
    """1.0 on every beat, decaying quickly until the next one."""
    return 0.0 if beats < 0 else math.exp(-(beats % 1.0) * 6)


def snap(f):
    """A robot-style hit: reaches the target within ~0.16 of a beat, then holds."""
    return ease(f / 0.16)


def seq(values, bl):
    """Staccato sequence: one value per count, snapping from the previous count's value."""
    c = min(len(values) - 1, math.floor(bl))
    f = bl - c
    prev = values[c - 1] if c > 0 else values[0]
    return lerp(prev, values[c], snap(f))


def bump(x, center, width):
    return max(0.0, 1 - abs(x - center) / width)
