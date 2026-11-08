interface Props {
  quantity: number;
  onChange: (quantity: number) => void;
  label: string;
}

export function QuantityControl({ quantity, onChange, label }: Props) {
  if (quantity === 0) {
    return (
      <button className="btn-add" onClick={() => onChange(1)} aria-label={`Add ${label}`}>
        + Add
      </button>
    );
  }
  return (
    <div className="stepper" role="group" aria-label={`${label} quantity`}>
      <button onClick={() => onChange(quantity - 1)} aria-label={`Remove one ${label}`}>
        −
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
