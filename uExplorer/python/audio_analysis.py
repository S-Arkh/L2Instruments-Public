"""Bounded audio visualization helpers, independent of Qt and package parsing."""
import cmath
import io
import math
import struct
import wave


def pcm_samples(data, width, channels=1, floating=False):
    if width not in (1, 2, 3, 4) or not 1 <= channels <= 32:
        raise ValueError('Unsupported PCM sample layout')
    stride = width * channels
    result = []
    for offset in range(0, len(data)-stride+1, stride):
        sample = data[offset:offset+width]  # First channel; avoid stereo phase cancellation.
        value = (struct.unpack('<f', sample)[0] if floating else
                 (sample[0]-128)/128 if width == 1 else
                 int.from_bytes(sample, 'little', signed=True)/(1 << (8*width-1)))
        result.append(max(-1., min(1., value)) if math.isfinite(value) else 0.)
    return result


def spectrum(samples, size=1024):
    if size < 2 or size > 4096 or size & (size-1):
        raise ValueError('FFT size must be a power of two in 2..4096')
    samples = samples[-size:]
    samples = [0.] * (size-len(samples)) + samples
    values = [complex(v*(0.5-0.5*math.cos(2*math.pi*i/(size-1))))
              for i, v in enumerate(samples)]
    j = 0
    for i in range(1, size):
        bit = size >> 1
        while j & bit:
            j ^= bit; bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    length = 2
    while length <= size:
        step = cmath.exp(-2j*math.pi/length)
        for start in range(0, size, length):
            weight = 1.
            for i in range(length//2):
                a = values[start+i]; b = values[start+i+length//2]*weight
                values[start+i] = a+b; values[start+i+length//2] = a-b
                weight *= step
        length *= 2
    return [max(-80., min(0., 20*math.log10(max(abs(v)*4/size, 1e-4))))
            for v in values[:size//2+1]]


def waveform(audio, columns=512):
    """PCM WAV overview, computed off the UI thread; other codecs stay playable."""
    if len(audio) > 64*1024*1024:
        raise ValueError('Audio preview exceeds 64 MiB')
    with wave.open(io.BytesIO(audio), 'rb') as source:
        frames = source.getnframes()
        if not frames or source.getcomptype() != 'NONE':
            return []
        width, channels = source.getsampwidth(), source.getnchannels()
        if frames * width * channels > 64*1024*1024:
            raise ValueError('PCM overview exceeds 64 MiB')
        result = []
        # Each frame belongs to exactly one column, retaining short transients.
        position = 0
        for column in range(min(columns, frames)):
            end = (column+1)*frames//min(columns, frames)
            low, high = 1., -1.
            while position < end:
                n = min(4096, end-position)
                data = source.readframes(n)
                if len(data) != n*width*channels:
                    raise ValueError('Truncated PCM frames')
                values = pcm_samples(data, width, channels)
                low = min(low, min(values)); high = max(high, max(values)); position += n
            result.append((low, high))
        return result
