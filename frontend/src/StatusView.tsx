import type { AppStatus } from "./api.ts";

export type StatusState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; status: AppStatus };

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{value}</td>
    </tr>
  );
}

export function StatusView({ state }: { state: StatusState }) {
  return (
    <main className="shell">
      <header>
        <h1>Engineer Tests GTA</h1>
        <p className="muted">Local smoke page. Feature screens arrive in later phases.</p>
      </header>
      {state.kind === "loading" && <p role="status">Checking the local API…</p>}
      {state.kind === "error" && (
        <section role="alert" className="panel error">
          <h2>Backend unavailable</h2>
          <p>{state.message}</p>
          <p>
            Start it with <code>scripts\dev.ps1</code> or <code>scripts\run.ps1</code>.
          </p>
        </section>
      )}
      {state.kind === "ready" && (
        <section className="panel" aria-labelledby="status-heading">
          <h2 id="status-heading">
            Status{" "}
            <span className={`badge badge-${state.status.mode}`}>{state.status.mode} mode</span>
          </h2>
          <table>
            <tbody>
              <Row label="API" value={state.status.api} />
              <Row label="Version" value={state.status.version} />
              <Row label="YouTube API key" value={state.status.youtube_api_key} />
              <Row label="YouTube requests" value={state.status.youtube_requests} />
              <Row label="Database" value={state.status.database} />
              <Row label="Data folder" value={state.status.data_dir} />
              <Row label="Advanced analytics" value={state.status.advanced_analytics} />
              <Row label="AI" value={state.status.ai} />
              <Row label="Server time (UTC)" value={state.status.server_time_utc} />
            </tbody>
          </table>
          {state.status.data_dir_cloud_synced && (
            <p role="alert" className="warning">
              The data folder is inside a OneDrive-synced folder. Set GTA_LAB_DATA_DIR to a
              local, non-synced path.
            </p>
          )}
        </section>
      )}
    </main>
  );
}
