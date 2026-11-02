import { useEffect, useRef, useState } from "preact/hooks";
import { post } from "./api";
import { t } from "./i18n";
import type { State } from "./types";
import { latestFrameReader } from "./latestFrame";

// Preserve the existing one-second browser liveness contract for image transfer.
const LIVE_TIMEOUT_MS = 1000;
type CameraImage = { url: string; id: string; capturedAt: string | null };

export function useRobot(
  paired: boolean,
  onError: (message: string) => void,
  onExpired: () => void,
) {
  const [state, setState] = useState<State | null>(null);
  const [online, setOnline] = useState(false);
  const [armed, setArmed] = useState(false);
  const [image, setImage] = useState<CameraImage | null>(null);
  const [paintedImage, setPaintedImage] = useState<CameraImage | null>(null);
  const images = useRef(new Map<string, CameraImage>());
  const reader = useRef<ReturnType<typeof latestFrameReader> | null>(null);
  const [moving, setMoving] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const latest = useRef<State | null>(null);
  const displayed = useRef("");
  const epoch = useRef("");
  const pendingArm = useRef(false);
  const sequence = useRef(0);
  const direction = useRef([0, 0]);
  const readyImage = useRef(false);
  const send = (message: unknown) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(message));
  };
  const clear = () => {
    epoch.current = "";
    pendingArm.current = false;
    direction.current = [0, 0];
    setArmed(false);
    setMoving(false);
  };
  const stop = () => {
    clear();
    // One ordered channel prevents a delayed duplicate stop from revoking a
    // newly armed session. The host lease expires if the live channel stalls.
    if (socket.current?.readyState === WebSocket.OPEN) send({ type: "stop" });
    else if (paired)
      void post("/stop").catch(() =>
        onError(t("Connection lost: the stop request could not be confirmed.")),
      );
  };
  const drive = () => {
    if (!epoch.current) return;
    if (!displayed.current || !readyImage.current || !latest.current?.camera.fresh) {
      stop();
      return;
    }
    send({
      type: "drive",
      epoch: epoch.current,
      sequence: ++sequence.current,
      challenge: latest.current.control.challenge,
      frame_id: displayed.current,
      forward: direction.current[0],
      turn: direction.current[1],
    });
  };
  const hold = (forward: number, turn: number) => {
    if (!epoch.current) return;
    direction.current = [forward, turn];
    setMoving(!!(forward || turn));
    drive();
  };
  const arm = () => {
    if (!latest.current?.control.ready || !displayed.current || !readyImage.current) return;
    pendingArm.current = true;
    send({ type: "arm", challenge: latest.current.control.challenge, frame_id: displayed.current });
  };

  useEffect(() => {
    if (!paired) return;
    let disposed = false;
    let reconnect: ReturnType<typeof setTimeout>;
    let lastStatus = Date.now();
    function connect() {
      lastStatus = Date.now();
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`,
      );
      socket.current = ws;
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "status") {
          lastStatus = Date.now();
          latest.current = message;
          setState(message);
          setOnline(true);
          if (!message.control.owned && epoch.current) clear();
        } else if (message.type === "armed") {
          if (!pendingArm.current || document.hidden) {
            send({ type: "stop" });
            return;
          }
          epoch.current = message.epoch;
          sequence.current = 0;
          pendingArm.current = false;
          setArmed(true);
        } else if (message.type === "error") {
          clear();
          onError(message.message);
        }
      };
      ws.onclose = (event) => {
        clear();
        setOnline(false);
        displayed.current = "";
        readyImage.current = false;
        if (event.code === 1008 && !disposed) {
          onExpired();
          return;
        }
        if (!disposed) reconnect = setTimeout(connect, 1500);
      };
    }
    connect();
    const heartbeat = setInterval(() => {
      if (Date.now() - lastStatus > LIVE_TIMEOUT_MS && socket.current?.readyState === WebSocket.OPEN) {
        clear();
        setOnline(false);
        socket.current.close();
      } else drive();
    }, 120);
    const blur = () => {
      if (epoch.current || pendingArm.current) stop();
    };
    const visibility = () => {
      if (document.hidden) blur();
    };
    window.addEventListener("blur", blur);
    window.addEventListener("pagehide", blur);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      disposed = true;
      clearTimeout(reconnect);
      clearInterval(heartbeat);
      window.removeEventListener("blur", blur);
      window.removeEventListener("pagehide", blur);
      document.removeEventListener("visibilitychange", visibility);
      clear();
      socket.current?.close();
    };
  }, [paired]);

  const frameId = online && state?.camera.available ? state.camera.frame_id : null;
  useEffect(() => {
    if (!paired || !online) return;
    const stream = latestFrameReader(
      async (id, signal) => {
        const response = await fetch("/api/frame.jpg?id=" + encodeURIComponent(id), { signal });
        if (!response.ok || response.headers.get("X-Frame-Id") !== id)
          throw new Error("Camera frame unavailable or mismatched");
        return { blob: await response.blob(), capturedAt: response.headers.get("X-Captured-At") };
      },
      (frame) => {
        // Keep the painted URL alive until its replacement actually decodes.
        for (const [id, old] of images.current) {
          if (id !== displayed.current) {
            URL.revokeObjectURL(old.url);
            images.current.delete(id);
          }
        }
        const next = { url: URL.createObjectURL(frame.blob), id: frame.id, capturedAt: frame.capturedAt };
        images.current.set(next.id, next);
        setImage(next);
      },
      () => {
        displayed.current = "";
        readyImage.current = false;
        setPaintedImage(null);
        if (epoch.current || pendingArm.current) stop();
      },
      LIVE_TIMEOUT_MS,
    );
    reader.current = stream;
    return () => {
      stream.close();
      reader.current = null;
      displayed.current = "";
      readyImage.current = false;
      setPaintedImage(null);
      setImage(null);
      for (const old of images.current.values()) URL.revokeObjectURL(old.url);
      images.current.clear();
    };
  }, [paired, online]);
  useEffect(() => {
    if (frameId) reader.current?.offer(frameId);
  }, [frameId, paired, online]);

  return {
    state,
    online,
    armed,
    moving,
    image,
    paintedImage,
    imageReady: paintedImage !== null && readyImage.current,
    displayed,
    arm,
    stop,
    hold,
    imageLoaded: (id: string) => {
      const loaded = images.current.get(id);
      if (!loaded) return;
      displayed.current = id;
      readyImage.current = true;
      setPaintedImage(loaded);
      for (const [otherId, old] of images.current) {
        if (otherId !== id) {
          URL.revokeObjectURL(old.url);
          images.current.delete(otherId);
        }
      }
    },
    imageFailed: () => {
      displayed.current = "";
      readyImage.current = false;
      setPaintedImage(null);
      if (epoch.current || pendingArm.current) stop();
    },
  };
}
export type Robot = ReturnType<typeof useRobot>;
