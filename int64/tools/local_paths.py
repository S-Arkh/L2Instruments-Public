"""External inputs, configurable without editing source files.

Relative environment paths are resolved against the caller's working directory.
Defaults live in ignored local directories inside this repository.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configured(name, default):
    return Path(os.environ.get(name) or default).expanduser().resolve()


SYSTEM = configured('L2_COMPILER_SYSTEM', ROOT / 'compiler/System')
CLIENT_SYSTEM = configured('L2_CLIENT_SYSTEM', ROOT.parent / 'local/client/System')
CLIENT = configured('L2_CLIENT_CORE', CLIENT_SYSTEM / 'Core.dll')
PACKAGES = configured('L2_CLIENT_PACKAGES', CLIENT_SYSTEM)
INTERFACE_CLASSES = configured('L2_INTERFACE_CLASSES', ROOT.parent / 'local/interface/Classes')
RUNTIME_SDK = configured('L2_RUNTIME_SDK', ROOT / 'sdk/runtime2226')
CLEAR_HF_SYSTEM = configured('L2_CLEAR_HF_SYSTEM', ROOT.parent / 'local/clear-hf/System')
