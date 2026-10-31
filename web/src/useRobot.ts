import { useEffect, useRef, useState } from "preact/hooks";
import { post } from "./api";
import { t } from "./i18n";
import type { State } from "./types";

export function useRobot(
  paired: boolean,
  onError: (message: string) => void,
  onExpired: () => void,
) {
  const [state, setState] = useState<State | null>(null);
  const [online, setOnline] = useState(false);
  const [armed, setArmed] = useState(false);
  const [image, setImage] = useState<{ url: string; id: string } | null>(null);
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
      if (Date.now() - lastStatus > 1000 && socket.current?.readyState === WebSocket.OPEN) {
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
    if (!paired || !frameId) {
      displayed.current = "";
      readyImage.current = false;
      return;
    }
    const abort = new AbortController();
    let url = "";
    void fetch("/api/frame.jpg?id=" + encodeURIComponent(frameId), { signal: abort.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Camera unavailable");
        return response.blob();
      })
      .then((blob) => {
        if (!abort.signal.aborted) {
          url = URL.createObjectURL(blob);
          setImage({ url, id: frameId });
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          displayed.current = "";
          readyImage.current = false;
        }
      });
    return () => {
      abort.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [paired, frameId]);

  return {
    state,
    online,
    armed,
    moving,
    image,
    displayed,
    arm,
    stop,
    hold,
    imageLoaded: (id: string) => {
      displayed.current = id;
      readyImage.current = true;
    },
    imageFailed: () => {
      displayed.current = "";
      readyImage.current = false;
      if (epoch.current) stop();
    },
  };
}
export type Robot = ReturnType<typeof useRobot>;
