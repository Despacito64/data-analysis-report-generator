export type SessionSummary = {
  session_id: string;
  data_source: string;
  dataset_hash: string;
  row_count: number;
  model_name: string;
  demo_question: string | null;
};

export type RunStatus = {
  run_id: string;
  status: string;
  progress: string[];
  result_status: string | null;
  answer_text: string | null;
  error: string | null;
  report_ready: boolean;
  summary: string | null;
  table_rows: { category: string; amount: number }[] | null;
  highlights: string[] | null;
};

const SESSION_KEY = "da_session_id";

export function getSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function setSessionId(id: string): void {
  localStorage.setItem(SESSION_KEY, id);
}

function sessionHeaders(): HeadersInit {
  const sid = getSessionId();
  return sid ? { "X-Session-Id": sid } : {};
}

export async function fetchModelName(): Promise<string> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as { model: string };
  return data.model;
}

export async function loadDemoSession(): Promise<SessionSummary> {
  const res = await fetch("/api/session/demo", {
    method: "POST",
    headers: sessionHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as SessionSummary;
  setSessionId(data.session_id);
  return data;
}

export async function uploadDataset(
  file: File,
  sheetName: string,
): Promise<SessionSummary> {
  const body = new FormData();
  body.append("file", file);
  body.append("sheet_name", sheetName);
  const res = await fetch("/api/session/upload", {
    method: "POST",
    headers: sessionHeaders(),
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Upload failed (${res.status})`);
  }
  const data = (await res.json()) as SessionSummary;
  setSessionId(data.session_id);
  return data;
}

export async function startRun(
  sessionId: string,
  question: string,
): Promise<{ run_id: string }> {
  const res = await fetch(`/api/session/${sessionId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ run_id: string }>;
}

export async function fetchRun(runId: string): Promise<RunStatus> {
  const res = await fetch(`/api/runs/${runId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<RunStatus>;
}
