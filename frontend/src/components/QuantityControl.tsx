function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
    </svg>
  );
}

interface Props {
  quantity: number;
  onChange: (quantity: number) => void;
  label: string;
}

export function QuantityControl({ quantity, onChange, label }: Props) {
  if (quantity === 0) {
    return (
      <button className="btn-add" onClick={() => onChange(1)} aria-label={`Add ${label}`}>
        <span className="btn-add-plus" aria-hidden>
          +
        </span>
        <span className="btn-add-label">Add</span>
      </button>
    );
  }
  return (
    <div className="stepper" role="group" aria-label={`${label} quantity`}>
      <button onClick={() => onChange(quantity - 1)} aria-label={`Remove one ${label}`}>
        {quantity === 1 ? <TrashIcon /> : "−"}
      </button>
      <span>{quantity}</span>
      <button
        onClick={() => onChange(quantity + 1)}
        disabled={quantity >= 99}
        aria-label={`Add one ${label}`}
      >
        +
      </button>
    </div>
  );
}
