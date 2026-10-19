"""Shared test setup.

On CPUs without AVX2 the bundled ``livekit.local_inference`` native module dies
with an illegal-instruction fault at import time, which cannot be caught and
kills the interpreter before any test runs. The agent package installs a
placeholder module in that case (see ``agent/native_compat.py``); import it here
so the shim is registered before anything pulls in ``livekit.agents``.
"""

from __future__ import annotations

from agent.native_compat import install_compat_shim

install_compat_shim()
