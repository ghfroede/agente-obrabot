from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> int:
    with TemporaryDirectory(prefix="obrabot-audit-") as tmp_dir:
        requirements_path = Path(tmp_dir) / "requirements.txt"
        export_cmd = [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--format",
            "requirements.txt",
            "--no-hashes",
            "--output-file",
            str(requirements_path),
        ]
        audit_cmd = ["uvx", "pip-audit", "-r", str(requirements_path), "--strict"]

        export_result = subprocess.run(export_cmd, check=False)
        if export_result.returncode != 0:
            return export_result.returncode

        audit_result = subprocess.run(audit_cmd, check=False)
        return audit_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
