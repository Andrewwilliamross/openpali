#!/usr/bin/env python3
"""Run only repository-scoped, validated Docker Compose operations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "openpali-one-shot"
ALLOWED_COMMANDS = {
    "build",
    "config",
    "create",
    "down",
    "logs",
    "pause",
    "ps",
    "pull",
    "restart",
    "rm",
    "start",
    "stop",
    "unpause",
    "up",
    "version",
    "wait",
}
PATH_FLAGS = {"-f", "--file", "--project-directory"}
VALUE_FLAGS = PATH_FLAGS | {"-p", "--project-name", "--profile", "--parallel", "--progress", "--ansi"}
BOOLEAN_FLAGS = {"--compatibility", "--dry-run"}
BLOCKED_TARGETS = {"/var/run/docker.sock", "/run/docker.sock"}
PROJECT_RE = re.compile(r"^openpali-[a-z0-9][a-z0-9-]{0,39}$")
SENSITIVE_ENV_RE = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|API_KEY|ACCESS_KEY)", re.IGNORECASE)
BLOCKED_RUNTIME_FLAGS = {
    "-e",
    "--env",
    "--env-file",
    "-u",
    "--user",
    "-v",
    "--volume",
    "-p",
    "-P",
    "--publish",
    "--name",
    "--device",
    "--cap-add",
    "--privileged",
    "--pid",
    "--ipc",
    "--network",
    "--build-arg",
    "--ssh",
    "--secret",
    "--allow",
    "--builder",
    "--context",
    "--host",
    "-H",
}
FORBIDDEN_SOURCE_KEYS = {"env_file", "include", "extends"}
ALLOWED_REGISTRIES = {"docker.io", "ghcr.io"}
SENSITIVE_FILENAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519"}


def fail(message: str) -> int:
    print(f"OpenPali Docker wrapper: {message}", file=sys.stderr)
    return 2


def within_repository(raw: str, label: str, *, allow_task: bool = False) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve(strict=False)
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository: {raw}") from exc
    if relative.parts and relative.parts[0] in {".git", ".claude"}:
        raise ValueError(f"{label} enters protected {relative.parts[0]}/")
    if not allow_task and (resolved == TASK or TASK in resolved.parents):
        raise ValueError(f"{label} enters immutable openpali-one-shot/")
    if any(part in SENSITIVE_FILENAMES or (part.startswith(".env.") and part != ".env.example") for part in relative.parts):
        raise ValueError(f"{label} references a sensitive local file")
    return resolved


def validate_content_root(path: Path, label: str) -> None:
    if path.is_file():
        return
    if not path.is_dir():
        raise ValueError(f"{label} is missing: {path}")
    pruned = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
    for directory, directories, files in os.walk(path, followlinks=False):
        directories[:] = [name for name in directories if name not in pruned]
        for name in [*directories, *files]:
            if name in SENSITIVE_FILENAMES or (name.startswith(".env.") and name != ".env.example"):
                raise ValueError(f"{label} contains a sensitive local file: {Path(directory) / name}")
            candidate = Path(directory) / name
            if candidate.is_symlink():
                within_repository(str(candidate.resolve(strict=False)), f"{label} symlink")


def validate_project_name(value: str) -> None:
    if not PROJECT_RE.fullmatch(value):
        raise ValueError("Compose project names must match openpali-[a-z0-9-]+")


def validate_compose_source(path: Path) -> None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: cannot safely parse Compose YAML: {exc}") from exc

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if str(key) in FORBIDDEN_SOURCE_KEYS:
                    raise ValueError(f"{path}: {key} indirection is forbidden")
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)


def parse_args(arguments: list[str]) -> tuple[list[Path], str, bool, bool]:
    files: list[Path] = []
    command = ""
    validate_only = False
    project_supplied = False
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == "--validate-only":
            validate_only = True
            index += 1
            continue
        if value == "--env-file" or value.startswith("--env-file="):
            raise ValueError("explicit env files are forbidden; use committed local-only defaults")
        if value.startswith("--project-name="):
            validate_project_name(value.split("=", 1)[1])
            project_supplied = True
            index += 1
            continue
        if value.startswith("--file=") or value.startswith("--project-directory="):
            flag, raw_path = value.split("=", 1)
            resolved = within_repository(raw_path, flag)
            if flag == "--file":
                files.append(resolved)
            index += 1
            continue
        if value in VALUE_FLAGS:
            if index + 1 >= len(arguments):
                raise ValueError(f"{value} requires a value")
            if value in PATH_FLAGS:
                resolved = within_repository(arguments[index + 1], value)
                if value in {"-f", "--file"}:
                    files.append(resolved)
            if value in {"-p", "--project-name"}:
                validate_project_name(arguments[index + 1])
                project_supplied = True
            index += 2
            continue
        if value in BOOLEAN_FLAGS:
            index += 1
            continue
        if value.startswith("-"):
            raise ValueError(f"unsupported Compose global flag: {value}")
        command = value
        break

    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"Compose subcommand is not allowed: {command or '<missing>'}")
    if not files:
        for candidate in (
            ROOT / "compose.yaml",
            ROOT / "compose.yml",
            ROOT / "docker-compose.yaml",
            ROOT / "docker-compose.yml",
            ROOT / "infra" / "compose.yaml",
            ROOT / "infra" / "compose.yml",
        ):
            if candidate.is_file():
                files.append(candidate.resolve())
                break
    if not files and command != "version":
        raise ValueError("no repository Compose file was selected or discovered")
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Compose file is missing or symlinked: {path}")
        validate_compose_source(path)
    return files, command, validate_only, project_supplied


def docker_environment(isolated_home: Path) -> dict[str, str]:
    allowed = {"PATH", "TMPDIR", "LANG", "LC_ALL"}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    docker_config = isolated_home / ".docker"
    docker_config.mkdir(parents=True, exist_ok=True)
    environment.update({
        "HOME": str(isolated_home),
        "DOCKER_CONFIG": str(docker_config),
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "USER": "openpali",
        "LOGNAME": "openpali",
    })
    environment["COMPOSE_DISABLE_ENV_FILE"] = "1"
    return environment


def compose_command() -> list[str]:
    candidates = [
        "/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose",
        "/usr/libexec/docker/cli-plugins/docker-compose",
        "/usr/local/lib/docker/cli-plugins/docker-compose",
        shutil.which("docker-compose"),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).resolve()
        if (path == ROOT or ROOT in path.parents or path == Path.home() or Path.home() in path.parents):
            continue
        if path.is_file() and os.access(path, os.X_OK):
            return [str(path)]
    raise ValueError("a standalone trusted Docker Compose v2 plugin binary was not found")


def validate_runtime_arguments(arguments: list[str], command: str) -> None:
    command_index = arguments.index(command)
    for value in arguments[command_index + 1 :]:
        flag = value.split("=", 1)[0]
        compact_escape = command in {"run", "exec"} and flag.startswith(("-e", "-u", "-v", "-p"))
        if flag in BLOCKED_RUNTIME_FLAGS or compact_escape:
            raise ValueError(f"runtime flag is forbidden: {flag}")


def validate_mount(service: str, mount: Any, declared_volumes: set[str]) -> None:
    if not isinstance(mount, dict):
        raise ValueError(f"{service}: Compose emitted a non-object mount")
    target = str(mount.get("target") or "")
    source = str(mount.get("source") or "")
    if mount.get("type") not in {"bind", "volume", "tmpfs"}:
        raise ValueError(f"{service}: unsupported mount type {mount.get('type')!r}")
    if target in BLOCKED_TARGETS or source.endswith("docker.sock") or target.endswith("docker.sock"):
        raise ValueError(f"{service}: Docker socket mounts are forbidden")
    if mount.get("type") == "volume" and source not in declared_volumes:
        raise ValueError(f"{service}: named volume is not declared in this project: {source}")
    if mount.get("type") != "bind":
        return
    resolved = within_repository(source, f"{service} bind mount")
    if resolved == ROOT:
        raise ValueError(f"{service}: mounting the repository root is forbidden; mount a scoped product directory")
    validate_content_root(resolved, f"{service} bind mount")


def validate_resource_collection(config: dict[str, Any], collection: str, project: str) -> set[str]:
    raw_collection = config.get(collection) or {}
    if not isinstance(raw_collection, dict):
        raise ValueError(f"Compose {collection} must be an object")
    names: set[str] = set()
    for key, raw in raw_collection.items():
        names.add(str(key))
        if not isinstance(raw, dict):
            raw = {}
        if raw.get("external") is True:
            raise ValueError(f"{collection}.{key}: external resources are forbidden")
        if raw.get("driver_opts") or (collection == "networks" and raw.get("attachable") is True):
            raise ValueError(f"{collection}.{key}: driver options/attachable resources are forbidden")
        if collection == "volumes" and raw.get("driver") not in {None, ""}:
            raise ValueError(f"{collection}.{key}: explicit volume drivers are forbidden")
        if collection in {"secrets", "configs"} and raw.get("environment"):
            raise ValueError(f"{collection}.{key}: host-environment providers are forbidden")
        actual_name = str(raw.get("name") or "")
        if actual_name and not actual_name.startswith((f"{project}_", f"{project}-")):
            raise ValueError(f"{collection}.{key}: resource name is outside project scope")
        if raw.get("file"):
            path = within_repository(str(raw["file"]), f"{collection}.{key}")
            validate_content_root(path, f"{collection}.{key}")
    return names


def validate_image(service: str, raw: dict[str, Any]) -> None:
    image = str(raw.get("image") or "")
    if raw.get("build"):
        if image and (not image.startswith("openpali-") or "/" in image or image.endswith(":latest")):
            raise ValueError(f"{service}: locally built image tags must be explicit unqualified openpali-* names")
        return
    if not image or "@sha256:" not in image:
        raise ValueError(f"{service}: third-party images must be pinned by sha256 digest")
    first = image.split("/", 1)[0]
    registry = first if "/" in image and ("." in first or ":" in first or first == "localhost") else "docker.io"
    if registry not in ALLOWED_REGISTRIES:
        raise ValueError(f"{service}: image registry is not allowed: {registry}")


def validate_config(config: dict[str, Any], project: str = "openpali-local") -> None:
    declared_volumes = validate_resource_collection(config, "volumes", project)
    declared_networks = validate_resource_collection(config, "networks", project)
    declared_secrets = validate_resource_collection(config, "secrets", project)
    if declared_secrets:
        raise ValueError("Compose secrets are forbidden in the one-shot; use explicit local-only fixture credentials")
    validate_resource_collection(config, "configs", project)
    networks = config.get("networks") or {}
    non_internal = {
        str(name) for name, raw in networks.items()
        if not isinstance(raw, dict) or raw.get("internal") is not True
    }
    services = config.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("Compose config has no services")
    for name, raw in services.items():
        if not isinstance(raw, dict):
            raise ValueError(f"{name}: malformed service config")
        if raw.get("privileged") is True:
            raise ValueError(f"{name}: privileged containers are forbidden")
        if raw.get("use_api_socket") is True:
            raise ValueError(f"{name}: Docker engine API socket injection is forbidden")
        for field in ("pid", "ipc", "cgroup", "userns_mode", "uts"):
            if str(raw.get(field) or "").lower() == "host":
                raise ValueError(f"{name}: host {field} is forbidden")
        if raw.get("network_mode"):
            raise ValueError(f"{name}: network_mode bypasses project network policy")
        if raw.get("devices") or raw.get("device_cgroup_rules") or raw.get("gpus"):
            raise ValueError(f"{name}: host devices are forbidden in the default local profile")
        if raw.get("cap_add"):
            raise ValueError(f"{name}: added Linux capabilities are forbidden")
        if any(raw.get(field) for field in (
            "credential_spec", "volumes_from", "develop", "extra_hosts",
            "external_links", "provider", "blkio_config", "cgroup_parent",
            "container_name", "runtime", "storage_opt", "models",
        )):
            raise ValueError(f"{name}: host/container indirection is forbidden")
        logging = raw.get("logging") or {}
        if isinstance(logging, dict) and logging.get("driver") not in {None, "", "json-file", "local"}:
            raise ValueError(f"{name}: external logging drivers are forbidden")
        for port in raw.get("ports") or []:
            if isinstance(port, dict) and port.get("published") and str(port.get("host_ip") or "") not in {"127.0.0.1", "::1"}:
                raise ValueError(f"{name}: published ports must bind loopback explicitly")
        environment = raw.get("environment") or {}
        if not isinstance(environment, dict):
            raise ValueError(f"{name}: environment must render as an explicit mapping")
        for key, value in environment.items():
            if SENSITIVE_ENV_RE.search(str(key)) and not str(value or "").startswith("openpali-local-"):
                raise ValueError(f"{name}: sensitive environment value must be an explicit local-only fixture credential: {key}")
        for mount in raw.get("volumes") or []:
            validate_mount(str(name), mount, declared_volumes)
        attached = raw.get("networks")
        attached_names = set(attached) if isinstance(attached, (dict, list)) else {"default"}
        if not attached_names.issubset(declared_networks):
            raise ValueError(f"{name}: service uses an undeclared network")
        labels = raw.get("labels") or {}
        is_proxy = isinstance(labels, dict) and str(labels.get("org.openpali.egress-proxy") or "").lower() == "true"
        if attached_names.intersection(non_internal) and not is_proxy:
            raise ValueError(f"{name}: only the labeled egress proxy may use a non-internal network")
        if is_proxy and any(mount.get("type") == "bind" for mount in raw.get("volumes") or [] if isinstance(mount, dict)):
            raise ValueError(f"{name}: the egress proxy may not receive host bind mounts")
        validate_image(str(name), raw)
        build = raw.get("build")
        if isinstance(build, dict) and build.get("context"):
            context = within_repository(str(build["context"]), f"{name} build context")
            if context == ROOT:
                raise ValueError(f"{name}: repository-root Docker build context is forbidden")
            validate_content_root(context, f"{name} build context")
            if any(build.get(key) for key in (
                "ssh", "secrets", "additional_contexts", "entitlements",
                "privileged", "cache_from", "cache_to", "output", "outputs",
            )) or str(build.get("network") or "").lower() not in {"", "none", "default"}:
                raise ValueError(f"{name}: privileged or external build inputs are forbidden")
            for key, value in (build.get("args") or {}).items():
                if SENSITIVE_ENV_RE.search(str(key)) and not str(value or "").startswith("openpali-local-"):
                    raise ValueError(f"{name}: sensitive build arg must be an explicit local-only fixture credential: {key}")
            if build.get("dockerfile"):
                dockerfile = Path(str(build["dockerfile"]))
                if not dockerfile.is_absolute():
                    dockerfile = context / dockerfile
                within_repository(str(dockerfile), f"{name} Dockerfile")
    if non_internal:
        proxies = [
            name for name, raw in services.items()
            if isinstance(raw, dict)
            and isinstance(raw.get("labels"), dict)
            and str(raw["labels"].get("org.openpali.egress-proxy") or "").lower() == "true"
        ]
        if len(proxies) != 1:
            raise ValueError("exactly one pinned, bind-free egress proxy must own non-internal networks")


def main() -> int:
    arguments = sys.argv[1:]
    try:
        _files, command, validate_only, project_supplied = parse_args(arguments)
        validate_runtime_arguments(arguments, command)
        compose = compose_command()
    except ValueError as exc:
        return fail(str(exc))

    config_arguments = [value for value in arguments if value != "--validate-only"]
    command_index = next(
        (index for index, value in enumerate(config_arguments) if value == command), len(config_arguments)
    )
    project = "openpali-local"
    for index, value in enumerate(config_arguments):
        if value in {"-p", "--project-name"} and index + 1 < len(config_arguments):
            project = config_arguments[index + 1]
        elif value.startswith("--project-name="):
            project = value.split("=", 1)[1]
    if not project_supplied and command != "version":
        config_arguments[command_index:command_index] = ["-p", "openpali-local"]
        command_index += 2
    global_arguments = config_arguments[:command_index]
    with tempfile.TemporaryDirectory(prefix="openpali-docker-home-") as temporary:
        environment = docker_environment(Path(temporary))
        if command == "version":
            if validate_only:
                print("DOCKER_COMPOSE_CONFIG: PASS")
                return 0
        else:
            rendered = subprocess.run(
                [*compose, *global_arguments, "config", "--format", "json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            if rendered.returncode:
                return fail(f"Compose config failed: {rendered.stderr.strip()}")
            try:
                validate_config(json.loads(rendered.stdout), project)
            except (json.JSONDecodeError, ValueError) as exc:
                return fail(f"unsafe Compose config: {exc}")
            if validate_only:
                print("DOCKER_COMPOSE_CONFIG: PASS")
                return 0

        completed = subprocess.run(
            [*compose, *config_arguments], cwd=ROOT, check=False, env=environment
        )
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
