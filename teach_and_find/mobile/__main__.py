"""Run the local mobile console with a synthetic robot unless explicitly configured."""

import argparse
from dataclasses import replace

from teach_and_find.config import Settings
from teach_and_find.mobile.api import create_app


def main():
    import uvicorn

    cfg = Settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=cfg.mobile.host)
    parser.add_argument("--port", type=int, default=cfg.mobile.port)
    parser.add_argument("--robot", choices=["mock", "relay"], default="mock")
    parser.add_argument("--relay-host")
    parser.add_argument("--relay-port", type=int, default=cfg.edge_relay.port)
    parser.add_argument("--allow-motion", action="store_true")
    parser.add_argument("--data-dir", default=cfg.assistant.data_dir)
    parser.add_argument("--ssl-certfile")
    parser.add_argument("--ssl-keyfile")
    args = parser.parse_args()
    if args.robot == "relay" and not args.relay_host:
        parser.error("--robot relay requires an explicitly selected --relay-host")
    cfg = replace(
        cfg,
        mobile=replace(
            cfg.mobile, robot_mode=args.robot, allow_physical_motion=args.allow_motion
        ),
        assistant=replace(cfg.assistant, data_dir=args.data_dir),
        edge_relay=replace(
            cfg.edge_relay,
            host=args.relay_host or cfg.edge_relay.host,
            port=args.relay_port,
        ),
    )
    app = create_app(cfg)
    print(
        f"PuppyPi console: {'synthetic preview' if args.robot == 'mock' else 'selected relay'}",
        flush=True,
    )
    print(
        f"Pairing code (enter on your device): {app.state.sessions.token}", flush=True
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
        access_log=False,
    )


if __name__ == "__main__":
    main()
