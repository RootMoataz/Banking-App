"""Build bank-api.zip for AWS Lambda (Python 3.12, x86_64) from the repository root.

Usage: python deploy/build_lambda.py
The zip holds the app, its Linux wheels and the handler. Secrets are never packaged: the Lambda reads
MONGODB_URI, MONGODB_DB, JWT_SECRET, CORS_ALLOWED_ORIGINS, ADMIN_EMAIL and ADMIN_PASSWORD from its environment.
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "lambda"
OUT = ROOT / "build" / "bank-api.zip"
REQUIREMENTS = ["fastapi>=0.115,<1", "pydantic[email]>=2.10,<3", "pymongo>=4.9,<5",
                "python-dotenv>=1,<2", "PyJWT>=2.8,<3", "mangum>=0.19,<1"]


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(BUILD),
                    "--platform", "manylinux2014_x86_64", "--python-version", "3.12",
                    "--implementation", "cp", "--only-binary=:all:", *REQUIREMENTS], check=True)
    (BUILD / "app").mkdir()
    for source in (ROOT / "app").glob("*.py"):
        shutil.copy(source, BUILD / "app" / source.name)
    shutil.copy(ROOT / "deploy" / "lambda_handler.py", BUILD / "lambda_handler.py")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(BUILD))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB); handler: lambda_handler.handler")


if __name__ == "__main__":
    main()
