# Optional bundled Windows runtime files

`run_windows.bat` is fully self-bootstrapping and does **not** require system Python.

For a completely self-contained reinstall bundle, these two official files may be placed here:

- `python-3.12.10-embed-amd64.zip` from Python.org
- `get-pip.py` from bootstrap.pypa.io

If they are not present, the launcher downloads them automatically on first run.
