"""Build an offline Windows application with a pinned, private Python runtime."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.build_demo_release import (  # noqa: E402
    LAUNCHERS, build_payloads, canonical, digest, snapshot, zip_bytes,
)
from tools.release_support import validate_external_directory  # noqa: E402

APP_GUIDES = ("START_HERE.txt", "MANAGER_DEMO.md", "KNOWN_LIMITATIONS.md")
RECIPE_FILES = (
    "tools/build_windows_app.py", "tools/build_demo_release.py", "tools/bundled_python.py",
    "tools/windows_runtime_lock.json", "tools/release_support.py",
    "tools/package_milestone6_extension.py",
)


def verify_build_recipe(files: dict[str, bytes]) -> None:
    """Require executed text recipes to match the captured source, allowing Git CRLF."""
    for name in RECIPE_FILES:
        expected = files.get(name)
        if expected is None or (ROOT / name).read_bytes().replace(b"\r\n", b"\n") != (
            expected.replace(b"\r\n", b"\n")
        ):
            raise ValueError("BUILD_RECIPE_DOES_NOT_MATCH_SOURCE_COMMIT")


def build_application_payloads(
    files: dict[str, bytes], commit: str, tree: str, timestamp: int,
    python_archive: Path, timezone_wheel: Path,
) -> tuple[dict[str, bytes], dict[str, object]]:
    from tools.bundled_python import bundled_runtime

    artifacts, metadata = build_payloads(files, commit, tree, timestamp)
    demo_name = next(name for name in artifacts if name.endswith("-windows-demo.zip"))
    with zipfile.ZipFile(io.BytesIO(artifacts.pop(demo_name))) as archive:
        runtime = {name: archive.read(name) for name in archive.namelist()}
    private_runtime, runtime_metadata = bundled_runtime(python_archive, timezone_wheel)
    if set(runtime) & set(private_runtime):
        raise ValueError("BUNDLED_RUNTIME_MEMBER_COLLISION")
    runtime.update(private_runtime)
    metadata.update({
        "runtime_tier": "WINDOWS_X64_BUNDLED_CPYTHON_3_12",
        "codex_fallback": "NONE",
        "windows_timezone_prerequisite": "BUNDLED",
        "bundled_runtime": runtime_metadata,
        "supported_environment": "Windows 10/11 x64, PowerShell 5.1, local browser",
        "workflow_scope": "SYNTHETIC_ONLY_LOCALHOST",
        "application_features": ["sales_credit", "doi", "campaigns", "replies", "writing_history"],
    })
    for name in APP_GUIDES:
        runtime[name] = files[f"docs/windows-app/{name}"]
    for name in LAUNCHERS:
        original = runtime[name]
        if original.count(b" -DevelopmentRuntime") != 1:
            raise ValueError("PORTABLE_LAUNCHER_TEMPLATE_INVALID")
        runtime[name] = original.replace(b" -DevelopmentRuntime", b"")
        if name == "START.cmd":
            runtime[name] = runtime[name].replace(
                b'if not "%SSA_NONINTERACTIVE%"=="1" pause',
                b'if not "%SSA_RESULT%"=="0" if not "%SSA_NONINTERACTIVE%"=="1" pause',
            )
    runtime["release-build.json"] = canonical(metadata)
    runtime.pop("release-payload.json")
    runtime["release-payload.json"] = canonical({
        "schema": "synthetic-sales-assist-release-payload/v1",
        "source_commit": commit,
        "files": {name: digest(raw) for name, raw in sorted(runtime.items())},
        "excluded_self": "release-payload.json",
    })
    version = metadata["application_version"]
    artifacts[f"sales-assist-{version}-windows-x64.zip"] = zip_bytes(runtime, timestamp)
    return artifacts, metadata


def build(
    commit: str, output: Path, python_archive: Path, timezone_wheel: Path,
) -> dict[str, object]:
    output = validate_external_directory(output, ROOT)
    if output.exists():
        raise ValueError("NEW_RELEASE_DIRECTORY_REQUIRED")
    files, tree, timestamp = snapshot(commit)
    verify_build_recipe(files)
    artifacts, metadata = build_application_payloads(
        files, commit, tree, timestamp, python_archive, timezone_wheel,
    )
    output.mkdir(parents=True)
    for name, raw in artifacts.items():
        (output / name).write_bytes(raw)
    result = {**metadata, "artifacts": {
        name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in artifacts.items()
    }}
    (output / "build-manifest.json").write_bytes(canonical(result))
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(raw)}  {name}\n" for name, raw in sorted(artifacts.items())),
        encoding="ascii",
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--timezone-wheel", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build(
        arguments.commit, arguments.output_dir, arguments.python_archive, arguments.timezone_wheel,
    ), sort_keys=True))
