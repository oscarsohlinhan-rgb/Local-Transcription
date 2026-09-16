from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_HANDLES = []


def register_nvidia_dll_directories() -> list[str]:
    """Register pip-installed NVIDIA DLL directories before CTranslate2 loads.

    On Windows, CUDA pip wheels install DLLs under site-packages/nvidia/*/bin.
    Python 3.8+ no longer searches arbitrary PATH entries for extension-module
    dependencies as broadly as older versions, so explicitly registering these
    folders avoids cublas64_12.dll / cudnn64_9.dll load failures.
    """
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return []

    roots = []
    for candidate in [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia",
        Path(__file__).resolve().parent / ".runtime" / "python" / "Lib" / "site-packages" / "nvidia",
    ]:
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)

    added: list[str] = []
    seen: set[str] = set()
    wanted = {"cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll"}

    for root in roots:
        for dll in wanted:
            for match in root.rglob(dll):
                folder = str(match.parent.resolve())
                if folder in seen:
                    continue
                try:
                    handle = os.add_dll_directory(folder)
                except OSError:
                    continue
                _DLL_HANDLES.append(handle)
                seen.add(folder)
                added.append(folder)
    return added


def main() -> None:
    added = register_nvidia_dll_directories()
    if added:
        print("Registered NVIDIA runtime DLL folders:")
        for folder in added:
            print(f"  - {folder}")

    from webapp import main as web_main

    web_main()


if __name__ == "__main__":
    main()
