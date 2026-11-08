import { useEffect, useRef, useState } from "react";

interface Props {
  /** The search being shown ("" = the store); set from outside when it's cleared. */
  value: string;
  /** Searches to offer while the field is empty (the shopper's own regulars). */
  suggestions: string[];
  /** Show results for this query; "" goes back to the store. */
  onSearch: (query: string) => void;
}

// Example requests the basket planner handles (any 3+ word search offers it).
const REQUESTS = ["tacos for 4 on friday under $40", "healthy lunches for this week"];

const SEARCH_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" strokeLinecap="round" />
  </svg>
);

/**
 * The store's search field. Results replace the store as you pause typing (or at once
 * on Enter); clearing it, with × or Escape, brings the store back. While it is empty
 * and focused, it offers the shopper's usual searches.
 */
export function SearchBox({ value, suggestions, onSearch }: Props) {
  const [text, setText] = useState(value);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const latest = useRef(onSearch);
  latest.current = onSearch;

  // A search ended elsewhere ("Back to the store") empties the field.
  useEffect(() => setText(value), [value]);

  useEffect(() => {
    const q = text.trim();
    if (q === value) return;
    if (!q) {
      latest.current("");
      return;
    }
    if (q.length < 2) return;
    const t = window.setTimeout(() => latest.current(q), 450);
    return () => window.clearTimeout(t);
  }, [text, value]);

  const pick = (q: string) => {
    setText(q);
    onSearch(q);
    inputRef.current?.blur();
  };

  const showIdeas = focused && !text && suggestions.length > 0;

  return (
    <form
      className={`searchbox${showIdeas ? " is-open" : ""}`}
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(text.trim());
      }}
    >
      {SEARCH_ICON}
      <input
        ref={inputRef}
        type="text"
        value={text}
        placeholder="Search the store"
        aria-label="Search the store"
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setFocused(true)}
        // Delay so a click on a suggestion lands before the list closes.
        onBlur={() => window.setTimeout(() => setFocused(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setText("");
        }}
      />
      {text ? (
        <button
          type="button"
          className="searchbox-clear"
          onClick={() => {
            setText("");
            inputRef.current?.focus();
          }}
          aria-label="Clear search"
        >
          ×
        </button>
      ) : null}

      {showIdeas ? (
        <div className="searchbox-ideas">
          <p>Your usual searches</p>
          <div className="chips">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="chip"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <p>Or ask for a whole basket</p>
          <div className="chips">
            {REQUESTS.map((s) => (
              <button
                key={s}
                type="button"
                className="chip"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </form>
  );
}
