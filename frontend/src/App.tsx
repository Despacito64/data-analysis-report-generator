import { useCallback, useEffect, useRef, useState } from "react";

const SUGGESTIONS = [
  "What are total sales by category?",
  "What is the total profit for each segment?",
  "What are the top 5 sub-categories by sales?",
  "Which region contributes the largest share of sales?",
  "How did total sales change from 2016 to 2017?",
];
import {
  fetchModelName,
  fetchRun,
  loadDemoSession,
  startRun,
  uploadDataset,
  type RunStatus,
  type SessionSummary,
} from "./api";

type ChatTurn = { question: string; run: RunStatus };

export function App() {
  const [modelName, setModelName] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(true);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [pickedName, setPickedName] = useState<string | null>(null);
  const [sheetName, setSheetName] = useState("");
  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<RunStatus | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const excelPicked = (pickedName ?? "").toLowerCase().endsWith(".xlsx");

  useEffect(() => {
    fetchModelName()
      .then(setModelName)
      .catch(() => setModelName(null));
  }, []);

  const activateDemo = useCallback(async () => {
    setError(null);
    const s = await loadDemoSession();
    setSession(s);
    setHistory([]);
    setRun(null);
  }, []);

  useEffect(() => {
    if (!demoMode) return;
    activateDemo().catch((e: Error) => setError(String(e)));
  }, [demoMode, activateDemo]);

  async function onDemoToggle(on: boolean) {
    setDemoMode(on);
    setPickedName(null);
    setSheetName("");
  }

  async function onFileSelected(file: File | null) {
    if (!file || demoMode) return;
    setPickedName(file.name);
    setError(null);
    try {
      const s = await uploadDataset(file, sheetName);
      setSession(s);
      setHistory([]);
      setRun(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    if (!run || run.status === "complete" || run.status === "failed") return;
    const id = setInterval(async () => {
      try {
        const next = await fetchRun(run.run_id);
        setRun(next);
        if (next.status === "complete" || next.status === "failed") {
          setRunning(false);
        }
      } catch (e) {
        setError(String(e));
        setRunning(false);
      }
    }, 500);
    return () => clearInterval(id);
  }, [run]);

  async function onRun(text?: string) {
    const asked = (text ?? question).trim();
    if (!session || !asked || running) return;
    setError(null);
    setRunning(true);
    setRun(null);
    try {
      setPendingQuestion(asked);
      setQuestion("");
      const { run_id } = await startRun(session.session_id, asked);
      const first = await fetchRun(run_id);
      setRun(first);
      if (first.status === "complete" || first.status === "failed") setRunning(false);
    } catch (e) {
      setError(String(e));
      setRunning(false);
    }
  }

  useEffect(() => {
    if (!run || run.status !== "complete" || !pendingQuestion) return;
    setHistory((items) => {
      if (items.some((item) => item.run.run_id === run.run_id)) return items;
      return [...items, { question: pendingQuestion, run }];
    });
  }, [run, pendingQuestion]);

  const bottomRef = useRef<HTMLDivElement>(null);
  const empty = history.length === 0 && !running;
  const canRun = Boolean(session) && question.trim().length > 0 && !running;
  const blockReason =
    !session && demoMode
      ? "Loading the sample dataset…"
      : !session && !demoMode
        ? "Choose a file to replace the sample."
        : null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [history, run, running]);

  return (
    <div className="app">
      <aside className="sidebar">
        <p className="brand">Data analysis agent</p>
        <h2>Dataset</h2>
        <div className="source-toggle" role="group" aria-label="Data source">
          <button
            type="button"
            className={demoMode ? "seg on" : "seg"}
            disabled={running}
            onClick={() => onDemoToggle(true)}
          >
            Sample file
          </button>
          <button
            type="button"
            className={!demoMode ? "seg on" : "seg"}
            disabled={running}
            onClick={() => onDemoToggle(false)}
          >
            Your file
          </button>
        </div>
        {!demoMode && (
          <label className="upload-btn">
            Choose CSV or Excel
            <input
              type="file"
              accept=".csv,.xlsx"
              disabled={running}
              onChange={(e) => onFileSelected(e.target.files?.[0] ?? null)}
            />
          </label>
        )}
        {!demoMode && excelPicked && (
          <label className="field">
            Worksheet
            <input
              type="text"
              value={sheetName}
              disabled={running}
              placeholder="First sheet if blank"
              onChange={(e) => setSheetName(e.target.value)}
            />
            <span>Name such as Orders, or 0 for the first sheet.</span>
          </label>
        )}
        <div className="stat" aria-live="polite">
          {session ? (
            <>
              <p className="stat-title">{session.data_source}</p>
              <p>{session.row_count.toLocaleString()} rows</p>
            </>
          ) : (
            <p>{demoMode ? "Loading sample…" : "No file loaded yet"}</p>
          )}
        </div>
        <p className="hint">
          Follow-ups keep the metric and grouping. Each reply is calculated again.
        </p>
      </aside>

      <section className={empty ? "thread-col is-empty" : "thread-col"}>
        <header className="thread-bar">
          <span>Thread</span>
          <span>{modelName ?? "Local model"}</span>
        </header>
        <div className="viewport">
          <div className="thread-inner">
            {empty && <h1 className="welcome">What should we look at?</h1>}
            {history.map((turn) => (
              <article key={turn.run.run_id}>
                <p className="msg-user">{turn.question}</p>
                <div className="msg-assistant">
                  {(() => {
                    const toolDump = /^Tool results:/i.test(turn.run.answer_text ?? "");
                    const lead =
                      turn.run.answer_text && !toolDump
                        ? turn.run.answer_text
                        : turn.run.summary;
                    const generic =
                      !lead ||
                      /^\d+ supported finding/i.test(lead) ||
                      lead === "No supported numeric findings.";
                    return lead && !generic ? <p className="lead">{lead}</p> : null;
                  })()}
                  {turn.run.table_rows && turn.run.table_rows.length > 0 && (
                    <table>
                      <thead>
                        <tr>
                          <th>Category</th>
                          <th>Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {turn.run.table_rows.map((row) => (
                          <tr key={row.category}>
                            <td>{row.category}</td>
                            <td className="num">
                              {row.amount.toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2,
                              })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {turn.run.highlights && turn.run.highlights.length > 0 && (
                    <ul>
                      {turn.run.highlights.map((h) => (
                        <li key={h}>{h}</li>
                      ))}
                    </ul>
                  )}
                  {!turn.run.summary &&
                    !turn.run.table_rows?.length &&
                    !turn.run.highlights?.length &&
                    turn.run.answer_text &&
                    !/^\d+ supported finding/i.test(turn.run.answer_text) && (
                    <p>{turn.run.answer_text}</p>
                  )}
                  {turn.run.answer_text &&
                    turn.run.summary &&
                    turn.run.answer_text !== turn.run.summary &&
                    /^Tool results:/i.test(turn.run.answer_text) && (
                    <details>
                      <summary>Technical wording</summary>
                      <pre>{turn.run.answer_text}</pre>
                    </details>
                  )}
                  {turn.run.report_ready && (
                    <p className="report-line">
                      <a href={`/api/runs/${turn.run.run_id}/report.html`} target="_blank" rel="noreferrer">
                        Open the HTML report
                      </a>
                      <span>Numbers in this reply come from this turn only.</span>
                    </p>
                  )}
                </div>
              </article>
            ))}
            {running && pendingQuestion && <p className="msg-user">{pendingQuestion}</p>}
            {run && run.status !== "complete" && (
              <div className="msg-assistant">
                <p className="muted">
                  {run.status}
                  {run.result_status ? ` · ${run.result_status}` : ""}
                </p>
                {run.progress.length > 0 && (
                  <ol className="steps">
                    {run.progress.map((line, i) => (
                      <li key={`${i}-${line}`}>{line}</li>
                    ))}
                  </ol>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="composer-dock">
          {error && <p className="fail">{error}</p>}
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void onRun();
            }}
          >
            <textarea
              value={question}
              rows={1}
              placeholder="Send a message…"
              aria-label="Question"
              disabled={running}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void onRun();
                }
              }}
            />
            <button type="submit" className="send" disabled={!canRun} aria-label="Send">
              ↑
            </button>
          </form>
          {empty && (
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button
                  key={text}
                  type="button"
                  className="suggest-item"
                  disabled={!session || running}
                  onClick={() => void onRun(text)}
                >
                  {text}
                </button>
              ))}
            </div>
          )}
          {blockReason && <p className="note">{blockReason}</p>}
        </div>
      </section>
    </div>
  );
}