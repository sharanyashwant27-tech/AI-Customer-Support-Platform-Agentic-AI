import { FormEvent, useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

type Citation = {
  source: string;
  excerpt?: string;
  score?: number;
};

type ChatReply = {
  reply?: string;
  text?: string;
  intent?: string;
  confidence?: number;
  agents_used?: string[];
  handoff_required?: boolean;
  sentiment?: string;
  session_id: string;
  citations?: Citation[];
  recommendations?: string[];
  metadata?: Record<string, unknown>;
  language?: string;
  channel?: string;
};

type Ticket = {
  id: string;
  ticket_number: string;
  subject: string;
  status: string;
  priority: string;
};

type Order = {
  order_id: string;
  status: string;
  total: number;
  tracking_number?: string | null;
};

const SUGGESTIONS = [
  "My package hasn't arrived.",
  "Where is my order ORD-1001?",
  "What is your return policy?",
  "I want a refund for ORD-1002",
  "I want to speak to a human agent",
  "Necesito un reembolso para ORD-1001",
];

const CHANNELS = ["web", "email", "whatsapp", "voice", "slack", "teams"] as const;
const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "hi", label: "हिन्दी" },
  { code: "de", label: "Deutsch" },
];

export default function App() {
  const [message, setMessage] = useState("My package hasn't arrived.");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [history, setHistory] = useState<ChatReply[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<string>("checking");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [order, setOrder] = useState<Order | null>(null);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("web");
  const [language, setLanguage] = useState("en");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`, {
      headers: { Accept: "application/json" },
    })
      .then(async (r) => {
        const data = await r.json();
        setHealth(data.status || "ok");
      })
      .catch(() => setHealth("down"));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, loading]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!message.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const endpoint =
        channel === "web"
          ? `${API_BASE}/chat/message`
          : `${API_BASE}/channels/${channel}/message`;
      const body =
        channel === "web"
          ? {
              message,
              session_id: sessionId,
              channel,
              metadata: { language },
            }
          : {
              text: message,
              session_id: sessionId,
              language,
              customer_phone: channel === "whatsapp" ? "+15555550100" : undefined,
              customer_email: channel === "email" ? "customer@example.com" : undefined,
            };
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const raw = await res.json();
      const data: ChatReply = {
        ...raw,
        reply: raw.reply || raw.text,
        agents_used: raw.agents_used || raw.metadata?.agents_used,
      };
      setHistory((h) => [...h, data]);
      setSessionId(data.session_id);
      setMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function createTicket() {
    const res = await fetch(`${API_BASE}/tickets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject: "Need help from chat",
        description: history.at(-1)?.reply || message || "Customer requested ticket",
        priority: "medium",
      }),
    });
    if (!res.ok) {
      setError(`Ticket create failed (${res.status})`);
      return;
    }
    const ticket: Ticket = await res.json();
    setTickets((t) => [ticket, ...t]);
  }

  async function lookupOrder() {
    const res = await fetch(`${API_BASE}/orders/lookup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id: "ORD-1001" }),
    });
    if (!res.ok) {
      setError(`Order lookup failed (${res.status})`);
      return;
    }
    setOrder(await res.json());
  }

  async function ingestSample() {
    const res = await fetch(`${API_BASE}/knowledge/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "Warranty Policy",
        content:
          "All hardware products include a 12-month limited warranty covering manufacturing defects. Accidental damage is not covered.",
        file_type: "markdown",
      }),
    });
    if (!res.ok) {
      setError(`Ingest failed (${res.status})`);
      return;
    }
    const data = await res.json();
    setIngestStatus(`Indexed ${data.chunks_created} chunks (${data.status})`);
  }

  const latest = history.at(-1);

  return (
    <div className="min-h-screen">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-24 top-10 h-72 w-72 rounded-full bg-brand-500/10 blur-3xl animate-pulse" />
        <div className="absolute right-0 top-40 h-80 w-80 rounded-full bg-ink/5 blur-3xl" />
      </div>

      <header className="relative z-10 px-6 py-5 flex items-center justify-between">
        <div className="font-display text-2xl tracking-tight text-brand-700">AICS</div>
        <div className="flex items-center gap-4 text-sm">
          <span
            className={`inline-flex items-center gap-2 ${
              health === "ok" || health === "degraded" ? "text-brand-700" : "text-red-700"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                health === "ok" || health === "degraded" ? "bg-brand-500" : "bg-red-500"
              }`}
            />
            API {health}
          </span>
          <a className="text-brand-700 underline" href="/docs">
            Docs
          </a>
          <a className="text-brand-700 underline" href="/console">
            API
          </a>
        </div>
      </header>

      <main className="relative z-10 mx-auto grid max-w-6xl gap-10 px-6 pb-16 lg:grid-cols-[1.4fr_0.8fr]">
        <section>
          <h1 className="font-display text-4xl md:text-5xl text-ink leading-tight mb-3">
            Customer Support
          </h1>
          <p className="text-lg text-ink/70 mb-6 max-w-xl">
            Multi-agent assistance with RAG citations, order lookup, tickets, and human handoff.
          </p>

          <div className="mb-4 flex flex-wrap gap-3">
            <label className="text-sm text-ink/70">
              Channel{" "}
              <select
                className="ml-1 rounded-md border border-ink/15 bg-white/80 px-2 py-1"
                value={channel}
                onChange={(e) => setChannel(e.target.value as (typeof CHANNELS)[number])}
              >
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink/70">
              Language{" "}
              <select
                className="ml-1 rounded-md border border-ink/15 bg-white/80 px-2 py-1"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setMessage(s)}
                className="rounded-md border border-ink/10 bg-white/70 px-3 py-1.5 text-sm text-ink/80 hover:border-brand-500/40"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="mb-4 max-h-[340px] space-y-3 overflow-y-auto rounded-xl border border-ink/10 bg-white/60 p-4 backdrop-blur">
            {history.length === 0 && (
              <p className="text-sm text-ink/50">Start a conversation to see agent responses.</p>
            )}
            {history.map((item, idx) => (
              <article key={`${item.session_id}-${idx}`} className="space-y-1">
                <p className="text-ink/90 whitespace-pre-wrap leading-relaxed">
                  {item.reply || item.text}
                </p>
                <p className="text-xs text-ink/45">
                  {item.channel || channel} · {item.language || language} · {item.intent} ·{" "}
                  {item.sentiment}
                  {item.handoff_required ? " · handoff" : ""}
                </p>
              </article>
            ))}
            <div ref={bottomRef} />
          </div>

          <form onSubmit={onSubmit} className="space-y-3">
            <textarea
              className="w-full min-h-[110px] rounded-xl border border-ink/15 bg-white/80 p-4 outline-none focus:border-brand-500"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask about orders, policies, or request a human…"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-brand-700 px-5 py-2.5 text-white font-semibold transition hover:bg-brand-500 disabled:opacity-60"
            >
              {loading ? "Thinking…" : "Send"}
            </button>
          </form>

          {error && <p className="mt-3 text-red-700">{error}</p>}

          {latest?.citations && latest.citations.length > 0 && (
            <div className="mt-6">
              <h2 className="font-display text-xl mb-2">Citations</h2>
              <ul className="space-y-2 text-sm text-ink/70">
                {latest.citations.map((c, i) => (
                  <li key={i} className="border-l-2 border-brand-500/40 pl-3">
                    <strong>{c.source}</strong>
                    {c.score != null && (
                      <span className="text-ink/40"> · {c.score.toFixed(2)}</span>
                    )}
                    <div>{c.excerpt}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <aside className="space-y-6">
          <div className="rounded-xl border border-ink/10 bg-white/70 p-5 backdrop-blur">
            <h2 className="font-display text-xl mb-3">Actions</h2>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={lookupOrder}
                className="rounded-lg border border-ink/15 px-3 py-2 text-left text-sm hover:border-brand-500/50"
              >
                Lookup ORD-1001
              </button>
              <button
                type="button"
                onClick={createTicket}
                className="rounded-lg border border-ink/15 px-3 py-2 text-left text-sm hover:border-brand-500/50"
              >
                Create support ticket
              </button>
              <button
                type="button"
                onClick={ingestSample}
                className="rounded-lg border border-ink/15 px-3 py-2 text-left text-sm hover:border-brand-500/50"
              >
                Ingest warranty policy
              </button>
            </div>
            {ingestStatus && <p className="mt-3 text-xs text-brand-700">{ingestStatus}</p>}
          </div>

          {order && (
            <div className="rounded-xl border border-ink/10 bg-white/70 p-5 backdrop-blur">
              <h2 className="font-display text-xl mb-2">Order</h2>
              <p className="text-sm">
                {order.order_id} · <strong>{order.status}</strong>
              </p>
              <p className="text-sm text-ink/70">${order.total}</p>
              {order.tracking_number && (
                <p className="text-xs text-ink/50 mt-1">{order.tracking_number}</p>
              )}
            </div>
          )}

          {tickets.length > 0 && (
            <div className="rounded-xl border border-ink/10 bg-white/70 p-5 backdrop-blur">
              <h2 className="font-display text-xl mb-2">Tickets</h2>
              <ul className="space-y-2 text-sm">
                {tickets.map((t) => (
                  <li key={t.id}>
                    {t.ticket_number} — {t.subject}{" "}
                    <span className="text-ink/50">({t.status})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {latest?.agents_used && (
            <div className="rounded-xl border border-ink/10 bg-white/70 p-5 backdrop-blur">
              <h2 className="font-display text-xl mb-2">Agent path</h2>
              <p className="text-xs leading-relaxed text-ink/60">
                {latest.agents_used.join(" → ")}
              </p>
              {latest.metadata?.prompt_variant != null && (
                <p className="mt-2 text-xs text-ink/50">
                  Prompt variant: {String(latest.metadata.prompt_variant)}
                </p>
              )}
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
