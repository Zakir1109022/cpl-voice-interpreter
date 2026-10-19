"""CPU compatibility for the native ``livekit.local_inference`` module.

Importing ``livekit.agents`` pulls in ``livekit.local_inference``, whose bundled
binary requires AVX2. On a CPU without AVX2 the import dies with an
illegal-instruction fault (0xC000001D) before any log line is printed, which
looks like the process silently doing nothing.

When native local inference cannot be loaded, this module registers a
placeholder in ``sys.modules`` first so imports succeed; anything that would
actually run the native VAD/EOT models then raises a readable error instead of
killing the process. Set ``INTERPRETER_STUB_LOCAL_INFERENCE=1`` to force the
placeholder on an AVX2-capable CPU (useful for reproducing the fallback).
"""

from __future__ import annotations

import ctypes
import os
import sys
import types

__all__ = ["install_compat_shim", "native_inference_available"]

_MODULE = "livekit.local_inference"
_ENV_FORCE = "INTERPRETER_STUB_LOCAL_INFERENCE"
_TRUTHY = ("1", "true", "yes", "on")
_PF_AVX2 = 39  # PF_AVX2_INSTRUCTIONS_AVAILABLE


class _Unavailable:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "livekit.local_inference native models are unavailable on this CPU (no AVX2); "
            "run the agent on an AVX2-capable machine"
        )


def native_inference_available() -> bool:
    """Return whether the native local-inference module can load on this CPU."""
    if (os.getenv(_ENV_FORCE) or "").strip().lower() in _TRUTHY:
        return False
    if not sys.platform.startswith("win"):
        return True
    try:
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(_PF_AVX2))
    except Exception:
        return False


def install_compat_shim() -> bool:
    """Install the placeholder module when native local inference cannot load."""
    if _MODULE in sys.modules:
        return False
    if native_inference_available():
        return False

    stub = types.ModuleType(_MODULE)
    stub.VAD = _Unavailable
    stub.EOT = _Unavailable
    stub.VAD_WINDOW_SAMPLES = 512
    stub.EOT_MAX_SAMPLES = 512
    stub.init_vad = lambda *args, **kwargs: None
    stub.init_eot = lambda *args, **kwargs: None
    sys.modules[_MODULE] = stub
    return True
