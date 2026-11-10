#!/usr/bin/env python3
"""Buzz Morse code on a Mac trackpad's haptic actuator.

Uses the private MultitouchSupport framework, so it may break with any
macOS update.

Usage:
    python3 TapticMorse.py "hello world"
    echo "sos" | python3 TapticMorse.py
    python3 TapticMorse.py --wpm 12 --rate 60 --aid 6 "cq cq"
    python3 TapticMorse.py --list
"""
import argparse
import ctypes
import sys
import time
from ctypes import c_float, c_int32, c_long, c_uint32, c_void_p

MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '.': '.-.-.-', ',': '--..--', '?': '..--..', "'": '.----.', '!': '-.-.--',
    '/': '-..-.', '(': '-.--.', ')': '-.--.-', '&': '.-...', ':': '---...',
    ';': '-.-.-.', '=': '-...-', '+': '.-.-.', '-': '-....-', '_': '..--.-',
    '"': '.-..-.', '$': '...-..-', '@': '.--.-.',
}

MT_PATH = ('/System/Library/PrivateFrameworks/'
           'MultitouchSupport.framework/MultitouchSupport')
CF_PATH = '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'


def load():
    mt = ctypes.CDLL(MT_PATH)
    cf = ctypes.CDLL(CF_PATH)
    mt.MTDeviceCreateList.restype = c_void_p
    cf.CFArrayGetCount.restype = c_long
    cf.CFArrayGetCount.argtypes = [c_void_p]
    cf.CFArrayGetValueAtIndex.restype = c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
    mt.MTDeviceGetMTActuator.restype = c_void_p
    mt.MTDeviceGetMTActuator.argtypes = [c_void_p]
    mt.MTActuatorOpen.restype = c_int32
    mt.MTActuatorOpen.argtypes = [c_void_p]
    mt.MTActuatorClose.restype = c_int32
    mt.MTActuatorClose.argtypes = [c_void_p]
    mt.MTActuatorActuate.restype = c_int32
    mt.MTActuatorActuate.argtypes = [c_void_p, c_int32, c_uint32,
                                     c_float, c_float]
    return mt, cf


def actuators(mt, cf):
    """Return [(device_index, actuator_pointer)] for devices that have one."""
    devices = mt.MTDeviceCreateList()
    if not devices:
        return []
    found = []
    for i in range(cf.CFArrayGetCount(devices)):
        dev = cf.CFArrayGetValueAtIndex(devices, i)
        act = mt.MTDeviceGetMTActuator(dev) if dev else None
        if act:
            found.append((i, act))
    return found


def wait_until(t):
    """Sleep most of the way, then spin for accuracy."""
    remaining = t - time.perf_counter()
    if remaining > 0.003:
        time.sleep(remaining - 0.002)
    while time.perf_counter() < t:
        pass


def main():
    p = argparse.ArgumentParser(description='Buzz Morse code on the trackpad.')
    p.add_argument('text', nargs='*', help='text to send (default: stdin)')
    p.add_argument('--wpm', type=float, default=15,
                   help='speed in words per minute (default 15)')
    p.add_argument('--rate', type=float, default=80,
                   help='pulses per second inside a buzz (default 80)')
    p.add_argument('--gap', type=float, default=2.0,
                   help='stretch factor for all silences; 1.0 is standard '
                        'Morse spacing (default 2.0)')
    p.add_argument('--aid', type=int, default=6,
                   help='actuation ID: 1-6, 15 or 16 (default 6)')
    p.add_argument('--device', type=int, default=None,
                   help='device index from --list (default: first found)')
    p.add_argument('--list', action='store_true',
                   help='list devices that have an actuator, then exit')
    p.add_argument('--quiet', action='store_true',
                   help='do not print the code while sending')
    args = p.parse_args()

    mt, cf = load()
    acts = actuators(mt, cf)
    if args.list:
        for i, _ in acts:
            print(f'device {i}: has actuator')
        if not acts:
            print('no haptic actuator found')
        return 0
    if not acts:
        sys.exit('no haptic actuator found')

    if args.device is None:
        act = acts[0][1]
    else:
        match = [a for i, a in acts if i == args.device]
        if not match:
            sys.exit(f'device {args.device} has no actuator (try --list)')
        act = match[0]

    text = ' '.join(args.text) if args.text else sys.stdin.read()
    text = ' '.join(text.upper().split())
    if not text:
        sys.exit('nothing to send')

    unit = 1.2 / args.wpm          # standard PARIS timing
    period = 1.0 / args.rate
    rest = unit * args.gap * 3         # not standard, to make the buzzing legible
    err = mt.MTActuatorOpen(act)
    if err:
        sys.exit(f'MTActuatorOpen failed: 0x{err & 0xffffffff:08x}')

    def buzz(units):
        t = time.perf_counter()
        end = t + units * unit
        while True:
            mt.MTActuatorActuate(act, args.aid, 0, 0.0, 0.0)
            t += period
            # No pulse in the last period, so its ring-down stays in the mark.
            if t + period > end:
                break
            wait_until(t)
        wait_until(end)

    def show(s):
        if not args.quiet:
            sys.stdout.write(s)
            sys.stdout.flush()

    try:
        for word_i, word in enumerate(text.split(' ')):
            if word_i:
                show(' / ')
                time.sleep(4 * rest)       # 3 already waited: 7 total
            for ch in word:
                code = MORSE.get(ch)
                if code is None:
                    continue               # skip characters with no code
                for sym_i, sym in enumerate(code):
                    if sym_i:
                        time.sleep(rest)   # gap inside a letter
                    show(sym)
                    buzz(1 if sym == '.' else 4)
                show(' ')
                time.sleep(4 * rest)       # gap between letters
        show('\n')
    except KeyboardInterrupt:
        show('\n')
    finally:
        mt.MTActuatorClose(act)
    return 0


if __name__ == '__main__':
    sys.exit(main())
