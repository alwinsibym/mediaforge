"""Compose the background score for the promo video: an original, synthesised piece for felt piano.

    python scripts/make_score.py [output.wav]

Everything is made from sine and noise sources in numpy, so there is nothing to license.
96 beats per minute, 110 beats (about 69 seconds), in C major: a soft felt piano that plays a
slow pattern over a warm low pad, with no drums until the very end. The beat numbers of the
video's scenes are in SCENES below, so the picture and the music change together.
"""

import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
BPM = 96
BEAT = 60 / BPM
TOTAL_BEATS = 110
LENGTH = TOTAL_BEATS * BEAT  # 68.75 s

# Scene start beats, shared with scripts/make_promo.py.
SCENES = {"intro": 0, "what": 8, "pipe": 16, "demo": 28, "tweaks": 48, "spatial": 60,
          "local": 72, "phone": 80, "get": 90, "end": 98}

# Chord tones from the bottom up: root, fifth, seventh, ninth, third (C9, Am9, F9, G6/9).
C9 = [36, 43, 47, 50, 52]
AM9 = [33, 40, 43, 47, 48]
F9 = [29, 36, 40, 45, 48]
G69 = [31, 38, 40, 45, 47]
CHORDS = [(0, C9), (8, AM9), (16, F9), (24, G69), (32, C9), (40, AM9), (48, F9), (56, G69),
          (64, C9), (72, AM9), (80, F9), (88, G69), (98, C9)]
FINAL = 98  # the closing chord

rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def buf(seconds=LENGTH + 6):
    return np.zeros((int(seconds * SR), 2))


def put(track, sound, start, pan=0.0):
    """Mix a mono sound into a stereo track at `start` seconds. pan -1 (left) to 1 (right)."""
    i = int(start * SR)
    if i >= len(track):
        return
    n = min(len(sound), len(track) - i)
    left, right = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
    track[i:i + n, 0] += sound[:n] * left
    track[i:i + n, 1] += sound[:n] * right


def lowpass(x, cutoff, order=2):
    return signal.sosfilt(signal.butter(order, cutoff, "low", fs=SR, output="sos"), x)


def highpass(x, cutoff, order=2):
    return signal.sosfilt(signal.butter(order, cutoff, "high", fs=SR, output="sos"), x)


def piano(midi, vel=0.7, seconds=4.5):
    """A felt piano note: slightly stretched partials that fade at their own pace, two strings,
    and a soft thump from the hammer. Quiet notes are rounder, louder ones a little brighter."""
    t = np.arange(int(seconds * SR)) / SR
    f = hz(midi)
    tone = np.zeros_like(t)
    decay = 3.2 * (60 / max(midi, 30)) ** 0.7  # low notes ring longer
    for n in range(1, 11):
        fn = f * n * np.sqrt(1 + 0.00035 * n * n)
        if fn > 7000:
            break
        weight = (1 / n ** 1.25) * (vel ** (0.5 * (n - 1)) if n > 1 else 1.0)
        env = np.exp(-t / (decay / (1 + 0.55 * (n - 1))))
        for cents, share in ((-1.6, 0.5), (1.6, 0.5)):
            tone += share * weight * np.sin(2 * np.pi * fn * 2 ** (cents / 1200) * t + n) * env
    thump = lowpass(rng.standard_normal(len(t)), 700) * np.exp(-t / 0.018) * 0.5 * vel
    attack = np.minimum(t / 0.004, 1.0)
    out = lowpass((tone + thump * 0.25) * attack, 4800)
    out *= np.where(t > seconds - 0.8, np.clip((seconds - t) / 0.8, 0, 1), 1.0)
    return out * 0.22 * vel


def pad_note(midi, seconds, attack=2.0, release=2.2):
    t = np.arange(int((seconds + release) * SR)) / SR
    f = hz(midi)
    tone = np.zeros_like(t)
    for cents, weight in ((-6, 0.5), (0, 1.0), (6, 0.5)):
        ff = f * 2 ** (cents / 1200)
        tone += weight * (np.sin(2 * np.pi * ff * t) + 0.25 * np.sin(2 * np.pi * 2 * ff * t))
    env = np.minimum(t / attack, 1.0) ** 2
    env *= np.where(t > seconds, np.clip(1 - (t - seconds) / release, 0, 1) ** 2, 1.0)
    return lowpass(tone * env, 900) * 0.045


def sub_note(midi, seconds):
    t = np.arange(int((seconds + 0.6) * SR)) / SR
    env = np.minimum(t / 0.25, 1.0) * np.exp(-t / 3.0)
    env *= np.where(t > seconds, np.clip(1 - (t - seconds) / 0.6, 0, 1), 1.0)
    return np.sin(2 * np.pi * hz(midi) * t) * env * 0.2


def heart(vel=1.0):
    """A soft, low pulse, used only for the closing."""
    t = np.arange(int(0.6 * SR)) / SR
    freq = 44 + 50 * np.exp(-t / 0.05)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t / 0.2) * np.minimum(t / 0.006, 1.0) * 0.4 * vel


def reverb_ir(seconds=3.8):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1)
    ir *= np.exp(-t / (seconds / 6.9))[:, None]  # about 60 dB down at the end
    ir[:, 0], ir[:, 1] = lowpass(highpass(ir[:, 0], 160), 5000), lowpass(highpass(ir[:, 1], 160), 5000)
    ir[: int(0.015 * SR)] *= np.linspace(0, 1, int(0.015 * SR))[:, None]
    return ir / np.sqrt(np.sum(ir ** 2))


def echo(track, delay, feedback, mix):
    d = int(delay * SR)
    out = track.copy()
    for k in range(1, 5):
        shifted = np.zeros_like(track)
        shifted[k * d:] = track[: len(track) - k * d][:, ::-1] * (feedback ** k)  # swap sides
        out += shifted * mix
    return out


def chord_at(b):
    return max((c for c in CHORDS if c[0] <= b), key=lambda c: c[0])[1]


def compose():
    pads, keys = buf(), buf()

    # A low pad and a soft sub note under each chord.
    for i, (start, chord) in enumerate(CHORDS):
        end = CHORDS[i + 1][0] if i + 1 < len(CHORDS) else TOTAL_BEATS
        seconds = (end - start) * BEAT
        big = start == FINAL
        for k, midi in enumerate(chord[1:], start=1):
            put(pads, pad_note(midi + 12, seconds, attack=1.0 if big else 2.0) * (1.6 if big else 1.0),
                start * BEAT, pan=(k - 2) * 0.2)
        if start >= 8:
            put(pads, sub_note(chord[0], seconds), start * BEAT)

    # Piano. Each bar is a low note, then a slow rising and falling pattern in the middle register.
    pattern = [0, 2, 3, 2, 1, 3, 4, 3]  # indices into the chord, one per beat
    for b in range(TOTAL_BEATS):
        chord = chord_at(b)
        if b < 4 or b >= 94:
            continue
        dense = 16 <= b < 72 or 80 <= b < 94
        beat_in_bar = b % 8
        if beat_in_bar == 0:
            put(keys, piano(chord[0] + 12, 0.62, 5.5), b * BEAT, pan=-0.1)
        if dense:
            midi = chord[pattern[beat_in_bar]] + 24
            put(keys, piano(midi, 0.55 if beat_in_bar else 0.65, 4.0), b * BEAT, pan=0.25 * (1 if b % 2 else -1))
            if beat_in_bar in (2, 6):  # a quiet echo of the pattern, half a beat later
                put(keys, piano(chord[(pattern[beat_in_bar] + 2) % 5] + 36, 0.4, 3.0), (b + 0.5) * BEAT, pan=0.3)
        elif beat_in_bar in (2, 5):
            put(keys, piano(chord[(beat_in_bar // 2) % 5] + 24, 0.5, 4.0), b * BEAT, pan=0.15)

    # The opening: three slow, high notes for the logo.
    for beat, midi in ((0, 76), (2.5, 79), (5, 84)):
        put(keys, piano(midi, 0.7, 5.0), beat * BEAT, pan=0.1)
    # One clear high note as each headline arrives.
    for k, name in enumerate(("what", "pipe", "tweaks", "spatial", "local", "get")):
        put(keys, piano(88 if k % 2 == 0 else 84, 0.62, 4.0), SCENES[name] * BEAT, pan=-0.1)
    # The closing: a rolled chord, a soft low pulse and a final high note.
    for k, midi in enumerate((48, 55, 59, 64, 67, 71, 76)):
        put(keys, piano(midi, 0.7, 6.0), (FINAL + k * 0.35) * BEAT, pan=(k - 3) * 0.12)
    for k in range(0, 8, 2):
        put(pads, heart(0.7 if k else 1.0), (FINAL + k) * BEAT)
    put(keys, piano(88, 0.55, 6.0), (FINAL + 5) * BEAT, pan=0.2)

    keys = echo(keys, BEAT * 1.5, 0.3, 0.35)

    # Space around everything.
    ir = reverb_ir()
    wet = np.stack([signal.fftconvolve(pads[:, c] + keys[:, c], ir[:, c])[: len(pads)] for c in range(2)], axis=1)
    mix = pads * 0.9 + keys * 0.9 + wet * 0.6

    mix = mix[: int(LENGTH * SR)]
    fade = int(3.5 * SR)
    mix[-fade:] *= (np.linspace(1, 0, fade) ** 1.6)[:, None]
    mix[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))[:, None]
    mix = highpass(mix.T, 28, 2).T
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)  # soft clip, so no sharp peaks
    return mix / max(np.abs(mix).max(), 1e-9) * 0.9


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "score.wav")
    audio = compose()
    wavfile.write(out, SR, (audio * 32767).astype(np.int16))
    print(f"wrote {out}: {len(audio) / SR:.1f} s")
