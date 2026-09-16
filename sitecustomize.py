"""Windows runtime compatibility for local Faster-Whisper.

Python automatically imports sitecustomize during startup when this repository is
on sys.path. On Windows, NVIDIA's pip wheels keep CUDA/cuDNN DLLs under the
virtual environment's site-packages tree; CTranslate2 may not discover those
folders automatically. Register them with the Windows DLL loader and PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_DIR_HANDLES = []


def _register_windows_nvidia_dlls() -> None:
    if os.name != "nt":
        return

    roots = [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia",
        Path(sys.base_prefix) / "Lib" / "site-packages" / "nvidia",
    ]
    rel_dirs = [
        Path("cublas") / "bin",
        Path("cudnn") / "bin",
        Path("cuda_runtime") / "bin",
    ]

    seen: set[str] = set()
    for root in roots:
        for rel in rel_dirs:
            folder = root / rel
            if not folder.is_dir():
                continue
            key = str(folder.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)

            folder_str = str(folder.resolve())
            os.environ["PATH"] = folder_str + os.pathsep + os.environ.get("PATH", "")
            try:
                _DLL_DIR_HANDLES.append(os.add_dll_directory(folder_str))
            except (AttributeError, OSError):
                pass


_register_windows_nvidia_dlls()
