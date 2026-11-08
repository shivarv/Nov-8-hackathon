import type { Replay } from "../types";

interface Props {
  replay: Replay | null;
  error: string | null;
}

/**
 * The demo's proof: what this shopper really bought next (Instacart held the order
 * out; the model never saw it), and how many of those items each way of filling a
 * 10-item shelf finds.
 */
export function ReplayPanel({ replay, error }: Props) {
  if (error) return <p className="notice">Couldn't load the real next order: {error}</p>;
  if (!replay) return <div className="replay is-loading">Scoring against their real next order…</div>;
  const best = Math.max(...replay.scoreboard.map((s) => s.hits));

  return (
    <section className="replay" aria-label="Real next order">
      <header className="replay-head">
        <p className="eyebrow">Real next order · held out, never shown to the model</p>
        <h2>
          They bought {replay.n} item{replay.n === 1 ? "" : "s"}
          {replay.days_since_prior != null ? `, ${replay.days_since_prior} days after their last trip` : ""}
        </h2>
        <p>
          {replay.on_home_page} of {replay.n} are on this home page, marked{" "}
          <span className="replay-mark">Bought next</span>. How many each way of picking 10 items finds:
        </p>
      </header>
      <ol className="replay-board">
        {replay.scoreboard.map((s) => (
          <li key={s.name} className={s.hits === best && best > 0 ? "is-best" : undefined}>
            <span className="replay-name">{s.name}</span>
            <span className="replay-bar" aria-hidden>
              <span style={{ width: `${(100 * s.hits) / Math.max(replay.n, 1)}%` }} />
            </span>
            <span className="replay-hits">
              {s.hits}/{Math.min(replay.n, s.k)}
            </span>
            <span className="replay-desc">{s.description}</span>
          </li>
        ))}
      </ol>
      <p className="replay-foot">
        One shopper is an anecdote. Over 60 shoppers (prototype/evaluate.py), counting what they
        buy finds ~36% of the next basket in 10 picks; BehaviorGPT over the whole store ~8%.
      </p>
    </section>
  );
}
