import { useEffect, useState } from "react";
import { fetchStatus } from "./api.ts";
import { StatusView, type StatusState } from "./StatusView.tsx";

export function App() {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchStatus(controller.signal)
      .then((status) => setState({ kind: "ready", status }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setState({ kind: "error", message });
      });
    return () => controller.abort();
  }, []);

  return <StatusView state={state} />;
}
