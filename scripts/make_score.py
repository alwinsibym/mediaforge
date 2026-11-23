"""Compose the background score for the promo video: an original, synthesised piece.

    python scripts/make_score.py [output.wav]

It is made entirely from sine and noise sources in numpy, so there is nothing to license.
96 beats per minute, 110 beats (about 69 seconds), in C major: a warm pad, a soft sub bass, glassy
bell notes with a ping-pong echo, and a quiet heartbeat kick with a light rim and hat. The beat
numbers of the video's scenes are in SCENES below, so the picture and the music change together.
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

C9 = [48, 55, 59, 62, 64]
AM9 = [45, 52, 55, 59, 60]
F9 = [41, 48, 52, 57, 60]
G69 = [43, 50, 52, 57, 59]
CHORDS = [(0, C9), (8, AM9), (16, F9), (24, G69), (32, C9), (40, AM9), (48, F9), (56, G69),
          (64, C9), (72, AM9), (80, F9), (88, G69), (98, C9)]
FINAL = 98  # the closing chord and the last flourish

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


def pad_note(midi, seconds, attack=1.5, release=1.8):
    t = np.arange(int((seconds + release) * SR)) / SR
    f = hz(midi)
    tone = np.zeros_like(t)
    for cents, weight in ((-5, 0.5), (0, 1.0), (5, 0.5)):
        ff = f * 2 ** (cents / 1200)
        tone += weight * (np.sin(2 * np.pi * ff * t) + 0.35 * np.sin(2 * np.pi * 2 * ff * t)
                          + 0.12 * np.sin(2 * np.pi * 3 * ff * t))
    env = np.minimum(t / attack, 1.0) ** 2
    env *= np.where(t > seconds, np.clip(1 - (t - seconds) / release, 0, 1) ** 2, 1.0)
    return lowpass(tone * env, 1400) * 0.05


def bass_note(midi, seconds):
    t = np.arange(int((seconds + 0.4) * SR)) / SR
    env = np.minimum(t / 0.06, 1.0) * np.exp(-t / 2.2)
    env *= np.where(t > seconds, np.clip(1 - (t - seconds) / 0.4, 0, 1), 1.0)
    return (np.sin(2 * np.pi * hz(midi) * t) + 0.15 * np.sin(4 * np.pi * hz(midi) * t)) * env * 0.26


def bell(midi, vel=1.0, seconds=3.0):
    t = np.arange(int(seconds * SR)) / SR
    f = hz(midi)
    index = 2.2 * np.exp(-t / 0.35)
    tone = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * 3.5 * t))
    tone += 0.28 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / 0.5)
    env = np.minimum(t / 0.004, 1.0) * np.exp(-t / 0.9)
    return tone * env * 0.1 * vel


def kick(vel=1.0):
    t = np.arange(int(0.5 * SR)) / SR
    freq = 46 + 70 * np.exp(-t / 0.035)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t / 0.15) * np.minimum(t / 0.003, 1.0) * 0.55 * vel


def rim(vel=1.0):
    t = np.arange(int(0.12 * SR)) / SR
    noise = signal.sosfilt(signal.butter(2, [1500, 3200], "band", fs=SR, output="sos"), rng.standard_normal(len(t)))
    return noise * np.exp(-t / 0.025) * 0.16 * vel


def hat(vel=1.0):
    t = np.arange(int(0.07 * SR)) / SR
    return highpass(rng.standard_normal(len(t)), 7500) * np.exp(-t / 0.014) * 0.05 * vel


def riser(seconds):
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    step = 2048
    for s in range(0, n, step):
        cutoff = 400 * (1 + 20 * (s / n) ** 2)
        out[s:s + step] = lowpass(noise[s:s + step], min(cutoff, 14000), 1)
    return out * (t ** 2.2) * 0.22


def reverb_ir(seconds=3.4):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1)
    ir *= np.exp(-t / (seconds / 6.9))[:, None]  # about 60 dB down at the end
    ir[:, 0], ir[:, 1] = lowpass(highpass(ir[:, 0], 180), 5500), lowpass(highpass(ir[:, 1], 180), 5500)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    return ir / np.sqrt(np.sum(ir ** 2))


def echo(track, delay, feedback, mix):
    d = int(delay * SR)
    out = track.copy()
    for k in range(1, 6):
        shifted = np.zeros_like(track)
        shifted[k * d:] = track[: len(track) - k * d][:, ::-1] * (feedback ** k)  # swap sides
        out += shifted * mix
    return out


def arpeggio_notes(chord, b):
    """Which bell notes play in beat `b`, as (offset in beats, midi, velocity)."""
    top = [chord[2] + 24, chord[3] + 24, chord[4] + 24, chord[1] + 24, chord[3] + 12]
    notes = []
    if b < 4 or b >= 94:  # the riser and the closing chord are left clear
        return notes
    dense = 16 <= b < 72 or 80 <= b < 94
    sparse = not dense
    for half in (0, 1):
        n = (b * 2 + half)
        if sparse and half == 1:
            continue
        pick = top[(n * 3 + n // 4) % len(top)]
        vel = (0.55 if dense else 0.42) * (1.0 if half == 0 else 0.7)
        notes.append((half * 0.5, pick, vel))
    return notes


def compose():
    pads, bells, drums = buf(), buf(), buf()

    # Pad and bass follow the chords.
    for i, (start_beat, chord) in enumerate(CHORDS):
        end_beat = CHORDS[i + 1][0] if i + 1 < len(CHORDS) else TOTAL_BEATS
        seconds = (end_beat - start_beat) * BEAT
        big = start_beat == FINAL
        for k, midi in enumerate(chord):
            put(pads, pad_note(midi, seconds, attack=0.9 if big else 1.5) * (1.5 if big else 1.0),
                start_beat * BEAT, pan=(k - 2) * 0.18)
        if start_beat >= 8:
            put(pads, bass_note(chord[0] - 12 + 12, 4 * BEAT), start_beat * BEAT)
            if end_beat - start_beat >= 8:
                put(pads, bass_note(chord[0], 3 * BEAT), (start_beat + 4) * BEAT)

    # Bells: a few long notes in the opening, then a light arpeggio, plus a bell on each title.
    chord_at = lambda b: max((c for c in CHORDS if c[0] <= b), key=lambda c: c[0])[1]  # noqa: E731
    for b in range(TOTAL_BEATS):
        chord = chord_at(b)
        for offset, midi, vel in arpeggio_notes(chord, b):
            put(bells, bell(midi, vel), (b + offset) * BEAT, pan=0.35 if int(b * 2 + offset * 2) % 2 else -0.35)
    for beat, midi in ((0, 79), (2.5, 76), (5, 84)):  # the logo
        put(bells, bell(midi, 0.9, 4.0), beat * BEAT, pan=0.15)
    for k, name in enumerate(("what", "pipe", "tweaks", "spatial", "local", "get")):
        put(bells, bell(83 if k % 2 == 0 else 79, 1.0, 3.5), SCENES[name] * BEAT, pan=-0.1)  # one clear note per headline
    for k, midi in enumerate((72, 76, 79, 83, 88)):  # the closing flourish
        put(bells, bell(midi, 0.95, 4.5), (FINAL + k * 0.5) * BEAT, pan=(k - 2) * 0.2)
    bells = echo(bells, BEAT * 0.75, 0.38, 0.55)

    # The beat: quiet and soft, building a little, easing off, and dropping away at the end.
    for b in range(8, 94):
        full = 16 <= b < 72 or 80 <= b < 94
        if not full:
            if b % 2 == 0:
                put(drums, kick(0.7), b * BEAT)
            continue
        if b % 2 == 0 and full:
            put(drums, kick(0.85 if b % 4 == 0 else 0.7), b * BEAT)
        if b % 4 in (1, 3) and full:
            put(drums, rim(0.8), b * BEAT, pan=0.1)
        if full:
            put(drums, hat(0.7), (b + 0.5) * BEAT, pan=-0.15)
            if b % 2 == 1:
                put(drums, hat(0.5), b * BEAT, pan=0.15)
    put(drums, kick(1.15), FINAL * BEAT)
    put(drums, riser(4 * BEAT), 94 * BEAT)

    # Space around the pad and the bells.
    ir = reverb_ir()
    wet = np.stack([signal.fftconvolve(pads[:, c] + bells[:, c] * 0.8, ir[:, c])[: len(pads)]
                    for c in range(2)], axis=1)
    mix = pads * 0.9 + bells * 0.85 + wet * 0.55 + drums

    mix = mix[: int(LENGTH * SR)]
    fade = int(3.0 * SR)
    mix[-fade:] *= (np.linspace(1, 0, fade) ** 1.6)[:, None]
    mix[: int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))[:, None]
    mix = highpass(mix.T, 28, 2).T
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)  # soft clip, so no sharp peaks
    return mix / max(np.abs(mix).max(), 1e-9) * 0.9


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "score.wav")
    audio = compose()
    wavfile.write(out, SR, (audio * 32767).astype(np.int16))
    print(f"wrote {out}: {len(audio) / SR:.1f} s")
