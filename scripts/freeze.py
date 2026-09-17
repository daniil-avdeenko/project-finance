"""Обновляет requirements.txt в UTF-8 с LF line endings."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    out = subprocess.check_output(
        [sys.executable, "-m", "pip", "freeze"],
        stderr=subprocess.DEVNULL,
    ).decode("utf-8")

    # Убираем возможные CR, оставляем только LF
    normalized = out.replace("\r\n", "\n").replace("\r", "\n")

    Path("requirements.txt").write_bytes(normalized.encode("utf-8"))
    print("requirements.txt updated (UTF-8, LF)")


if __name__ == "__main__":
    main()
