"""Set up and supervise an authenticated temporary phone tunnel to the simulator."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from teach_and_find.config import Settings

CFG = Settings().phone
ACTIVE = ROOT / CFG.run_dir / "active.json"


def save(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2))
    temporary.replace(path)


def process_stamp(pid):
    try:
        value = Path(f"/proc/{pid}/stat").read_text()
        fields = value[value.rfind(")") + 2 :].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


def owned_alive(service):
    return (
        service.get("start_ticks") is not None
        and process_stamp(service["pid"]) == service["start_ticks"]
    )


def stop_services(services):
    # Birth-time checks prevent a reused PID from targeting an unrelated process.
    for service in reversed(list(services.values())):
        if owned_alive(service):
            try:
                os.killpg(service["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + CFG.shutdown_timeout_s
    while time.monotonic() < deadline and any(
        owned_alive(s) for s in services.values()
    ):
        time.sleep(0.1)
    for service in services.values():
        if owned_alive(service):
            try:
                os.killpg(service["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass


def cloudflared():
    installed = shutil.which("cloudflared")
    if installed:
        return installed
    system, arch = platform.system(), platform.machine()
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(arch)
    if system != "Linux" or not architecture:
        raise RuntimeError(
            "Automatic cloudflared setup supports Linux amd64/arm64; install the official binary for this OS."
        )
    with urllib.request.urlopen(
        "https://api.github.com/repos/cloudflare/cloudflared/releases/latest",
        timeout=30,
    ) as response:
        release = json.load(response)
    asset = next(
        a for a in release["assets"] if a["name"] == f"cloudflared-linux-{architecture}"
    )
    digest = asset.get("digest", "")
    if not digest.startswith("sha256:"):
        raise RuntimeError(
            "Official asset SHA256 unavailable; refusing unverified executable."
        )
    target = ROOT / "runs/tools" / (asset["name"] + "-" + release["tag_name"])
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(
            asset["browser_download_url"], timeout=60
        ) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest.removeprefix("sha256:"):
            raise RuntimeError("cloudflared asset digest mismatch.")
        target.write_bytes(data)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest.removeprefix(
        "sha256:"
    ):
        raise RuntimeError("Existing downloaded cloudflared digest mismatch.")
    target.chmod(0o700)
    return str(target)


def setup():
    for name in ("uv", "node", "npm"):
        if not shutil.which(name):
            raise RuntimeError(
                f"Required tool missing: {name}. Install the official tool before setup."
            )
    version = tuple(
        map(
            int,
            subprocess.check_output(["node", "-p", "process.versions.node"], text=True)
            .strip()
            .split("."),
        )
    )
    if version < (22, 12, 0):
        raise RuntimeError("Node 22.12+ is required.")
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv-dev")}
    subprocess.run(
        ["uv", "sync", "--locked", "--extra", "dev", "--extra", "app"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    stamp = ROOT / "runs/tools/phone-web-lock.sha256"
    digest = hashlib.sha256((ROOT / "web/package-lock.json").read_bytes()).hexdigest()
    if (
        not (ROOT / "web/node_modules").is_dir()
        or not stamp.exists()
        or stamp.read_text() != digest
    ):
        subprocess.run(["npm", "--prefix", "web", "ci"], cwd=ROOT, check=True)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(digest)
    subprocess.run(["npm", "--prefix", "web", "run", "build"], cwd=ROOT, check=True)
    print("cloudflared:", cloudflared(), flush=True)


def load_active():
    return json.loads(ACTIVE.read_text()) if ACTIVE.exists() else None


def show(state):
    print(
        f"Mode: {'local AI workers + simulator' if state['ai'] else 'remote control only; AI OFF; simulator; no ROS'}"
    )
    print("URL:", state.get("public_url", "starting"))
    print("Pairing code:", Path(state["token_file"]).read_text())
    print("Logs:", state["run"])
    print("Stop: make phone-stop", flush=True)


def serve(args, directory):
    import httpx

    directory = Path(directory)
    token_file = directory / "pairing-code"
    token_file.write_text(secrets.token_urlsafe(9))
    token_file.chmod(0o600)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "CUDA_VISIBLE_DEVICES": "-1",
        "PUPPYPI_OPERATOR_TOKEN": token_file.read_text(),
        "TEACH_FIND_DATA_DIR": str(Path(args.data_dir).resolve()),
        "PUPPYPI_PHONE_PORT": str(args.port),
        "PUPPYPI_MEMORY_ENABLED": "0",
        "PUPPYPI_VISION_ENABLED": "1" if args.ai else "0",
        "PUPPYPI_SEARCH_ENABLED": "1" if args.ai else "0",
        "PUPPYPI_TRACKING_ENABLED": "1" if args.ai else "0",
        "PUPPYPI_TRACKING_DEVICE": "cpu",
        "PUPPYPI_SEARCH_HOST": f"http://127.0.0.1:{args.port}",
        "PUPPYPI_SEARCH_SCENARIO": CFG.scenario,
        "PUPPYPI_SEARCH_SIM_SEED": str(CFG.scene_seed),
        "PUPPYPI_SEARCH_APPEARANCE_SEED": str(CFG.appearance_seed),
    }
    if args.measure:
        env["PUPPYPI_PHONE_TRACE"] = str(directory / "trace.json")
    else:
        env.pop("PUPPYPI_PHONE_TRACE", None)
    if args.ai:
        sources = ROOT / "runs/interactive-tracking-research-2026-11-02"
        env["PUPPYPI_TRACKING_SOURCES"] = os.getenv(
            "PUPPYPI_TRACKING_SOURCES",
            str(sources if sources.is_dir() else ROOT / ".upstream/tracking"),
        )
        env["PUPPYPI_SEARCH_QUALITY_QUALIFIED"] = "1"
        env["PUPPYPI_SEARCH_QUALIFICATION"] = str(
            ROOT / "docs/research/2026-11-02-geometry-fix/qualification-v4-repeat.json"
        )
    else:
        env["PUPPYPI_SEARCH_QUALITY_QUALIFIED"] = "0"
    state = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ai": args.ai,
        "run": str(directory),
        "root": str(ROOT),
        "token_file": str(token_file),
        "local_url": env["PUPPYPI_SEARCH_HOST"],
        "services": {},
        "status": "starting",
        "supervisor": {"pid": os.getpid(), "start_ticks": process_stamp(os.getpid())},
        "scope": "pinhole kinematic simulator; no ROS or physical robot; paid worker OFF",
    }
    inventory = {}
    for relative in (
        "web/src/useRobot.ts", "web/src/latestFrame.ts", "web/src/main.tsx",
        "teach_and_find/config.py", "teach_and_find/mobile/runtime.py",
        "teach_and_find/mobile/api.py", "teach_and_find/sim/search_device.py",
        "teach_and_find/sim/world3d.py", "scripts/phone_app_server.py",
        "scripts/phone_session.py", "web/scripts/benchmark-phone.mjs",
        "teach_and_find/phone_benchmark.py",
    ):
        data = (ROOT / relative).read_bytes()
        inventory[relative] = hashlib.sha256(data).hexdigest()
        target = directory / "source-snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    state["source_sha256"] = inventory
    state["runtime"] = {"frame_poll_s": Settings().mobile.frame_poll_s,
                        "max_frame_age_s": Settings().mobile.max_frame_age_s,
                        "command_lease_s": Settings().mobile.command_lease_s}

    def publish():
        save(directory / "session.json", state)
        save(ACTIVE, state)

    stopped = False

    def stop_signal(*_):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop_signal)
    processes, logs = {}, []

    def spawn(name, command, child_env):
        log = (directory / (name + ".log")).open("w")
        logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes[name] = process
        state["services"][name] = {
            "pid": process.pid,
            "start_ticks": process_stamp(process.pid),
            "log": str(directory / (name + ".log")),
        }
        publish()

    try:
        spawn(
            "app",
            [str(ROOT / ".venv-dev/bin/python"), "scripts/phone_app_server.py"],
            env,
        )
        with httpx.Client(timeout=2) as client:
            deadline = time.monotonic() + CFG.health_timeout_s
            while True:
                if stopped or processes["app"].poll() is not None:
                    raise RuntimeError("App startup stopped; inspect app.log.")
                try:
                    if (
                        client.get(state["local_url"] + "/api/health").status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("App health deadline exceeded.")
                time.sleep(0.2)
            if args.ai:
                for name, venv in [
                    ("search", ".venv-vision"),
                    ("vision", ".venv-vision"),
                    ("tracking", ".venv-tracking"),
                ]:
                    child = dict(env)
                    for key in (
                        "PUPPYPI_SEARCH_SCENARIO",
                        "PUPPYPI_SEARCH_SIM_SEED",
                        "PUPPYPI_SEARCH_APPEARANCE_SEED",
                    ):
                        child.pop(key, None)
                    spawn(
                        name,
                        [
                            str(ROOT / venv / "bin/python"),
                            "-m",
                            f"teach_and_find.{name}_worker",
                        ],
                        child,
                    )
                client.post(
                    state["local_url"] + "/api/session",
                    json={"token": token_file.read_text()},
                ).raise_for_status()
                deadline = time.monotonic() + CFG.startup_timeout_s
                while True:
                    if stopped or any(p.poll() is not None for p in processes.values()):
                        raise RuntimeError("A required AI worker failed; inspect its log.")
                    workers = [client.get(state["local_url"] + "/api/" + name).json().get("worker") for name in ("search", "vision", "tracking")]
                    if all(worker and worker.get("alive") and worker.get("status") == "ready" for worker in workers):
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Required AI worker readiness deadline exceeded.")
                    time.sleep(.3)
            tunnel_env = dict(env)
            for key in (
                "TUNNEL_TOKEN",
                "TUNNEL_TOKEN_FILE",
                "TUNNEL_CRED_FILE",
                "TUNNEL_ORIGIN_CERT",
                "TUNNEL_CONFIG",
            ):
                tunnel_env.pop(key, None)
            spawn(
                "tunnel",
                [
                    cloudflared(),
                    "tunnel",
                    "--config",
                    "/dev/null",
                    "--no-autoupdate",
                    "--protocol",
                    CFG.tunnel_protocol,
                    "--edge-ip-version",
                    CFG.tunnel_ip_version,
                    "--url",
                    state["local_url"],
                ],
                tunnel_env,
            )
            deadline = time.monotonic() + CFG.startup_timeout_s
            while True:
                if stopped or any(p.poll() is not None for p in processes.values()):
                    raise RuntimeError(
                        "A required process exited; inspect session logs."
                    )
                match = re.search(
                    r"https://[a-z0-9-]+\.trycloudflare\.com",
                    (directory / "tunnel.log").read_text(),
                )
                if match:
                    state["public_url"] = match.group()
                    try:
                        if (
                            client.get(state["public_url"] + "/api/health").status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Public tunnel health deadline exceeded.")
                time.sleep(0.5)
            state["status"] = "ready"
            publish()
            show(state)
            while not stopped:
                if any(p.poll() is not None for p in processes.values()):
                    raise RuntimeError(
                        "A required process exited; session is stopping, no automatic substitute."
                    )
                time.sleep(0.5)
    except Exception as error:
        state["error"] = str(error)
        raise
    finally:
        stop_services(state["services"])
        for process in processes.values():
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        for log in logs:
            log.close()
        state["status"] = "failed" if state.get("error") else "stopped"
        publish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "start", "status", "stop", "serve"])
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Start actual local research workers; never paid inference.",
    )
    parser.add_argument("--background", action="store_true")
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Save evaluator-only simulator timing trace at shutdown.",
    )
    parser.add_argument("--port", type=int, default=CFG.port)
    parser.add_argument("--data-dir", default=str(ROOT / CFG.data_dir))
    parser.add_argument("--run")
    args = parser.parse_args()
    if args.action == "setup":
        setup()
        return
    state = load_active()
    if args.action == "stop":
        if args.run:
            state = json.loads((Path(args.run) / "session.json").read_text())
        if state and owned_alive(state["supervisor"]):
            os.kill(state["supervisor"]["pid"], signal.SIGTERM)
            deadline = time.monotonic() + CFG.shutdown_timeout_s + 5
            while owned_alive(state["supervisor"]) and time.monotonic() < deadline:
                time.sleep(0.1)
            if owned_alive(state["supervisor"]):
                stop_services(state["services"])
                raise RuntimeError(
                    "Supervisor did not exit; owned child processes stopped."
                )
        elif state:
            stop_services(state["services"])
        print("Phone session stopped; other services untouched.")
        return
    if args.action == "status":
        if not state or not owned_alive(state["supervisor"]):
            print("No active phone session.")
            return
        show(state)
        return
    if args.action == "serve":
        serve(args, args.run)
        return
    if state and owned_alive(state["supervisor"]):
        if state["ai"] != args.ai:
            raise RuntimeError(
                "A different phone mode is active. Run make phone-stop before changing mode."
            )
        show(state)
        return
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError as error:
            raise RuntimeError(
                f"Port {args.port} is already in use; no unrelated process will be stopped."
            ) from error
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    directory = (
        ROOT / CFG.run_dir / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    )
    directory.mkdir(parents=True)
    if not args.background:
        serve(args, directory)
        return
    command = [
        str(ROOT / ".venv-dev/bin/python"),
        str(Path(__file__).resolve()),
        "serve",
        "--run",
        str(directory),
        "--port",
        str(args.port),
        "--data-dir",
        str(Path(args.data_dir).resolve()),
    ]
    for flag, on in [("--ai", args.ai), ("--measure", args.measure)]:
        if on:
            command.append(flag)
    with (directory / "supervisor.log").open("w") as log:
        supervisor = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + CFG.startup_timeout_s * (2 if args.ai else 1) + CFG.health_timeout_s + 5
    while time.monotonic() < deadline:
        if supervisor.poll() is not None:
            raise RuntimeError(
                f"Session startup failed. Inspect {directory / 'supervisor.log'}"
            )
        session = directory / "session.json"
        if session.exists():
            state = json.loads(session.read_text())
            if state["status"] == "ready":
                show(state)
                return
        time.sleep(0.3)
    supervisor.terminate()
    raise RuntimeError("Supervisor startup deadline exceeded.")


if __name__ == "__main__":
    main()
