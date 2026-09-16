from __future__ import annotations

import sys


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    import flask
    import ctranslate2
    import faster_whisper

    print(f"Flask: {getattr(flask, '__version__', 'installed')}")
    print(f"CTranslate2: {getattr(ctranslate2, '__version__', 'installed')}")
    print(f"Faster-Whisper: {getattr(faster_whisper, '__version__', 'installed')}")
    try:
        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        print(f"CUDA check: unavailable ({exc})")
    else:
        print(f"CUDA devices detected: {count}")
    print("Smoke test passed. Model weights are downloaded automatically on first use.")


if __name__ == "__main__":
    main()
