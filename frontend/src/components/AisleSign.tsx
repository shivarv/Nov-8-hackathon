import type { ReactNode } from "react";
import type { FeedSection } from "../types";

// Where the shelf's picks come from: mostly their own orders, or mostly new to them.
const CONFIDENCE_LABEL = {
  sure: "From your orders",
  good: "Picked for you",
  explore: "To discover",
} as const;

/** Where in the store this section is, shown on the sign's left plate. */
function plate(section: FeedSection): { top: string; big: string } {
  switch (section.kind) {
    case "regulars":
      return { top: "Entrance", big: "★" };
    case "pairs":
    case "mission":
      return { top: "For this basket", big: "+" };
    case "aisle":
      return { top: "Aisle", big: String(section.aisle_number ?? "") };
    case "due":
      return { top: "Before checkout", big: "↻" };
    case "treat":
      return { top: "Checkout", big: "$" };
    case "foryou":
      return { top: "For you", big: "♥" };
  }
}

interface Props {
  section: FeedSection;
  action?: ReactNode;
}

/** Section header styled as an overhead aisle sign; its finish shows the model's confidence. */
export function AisleSign({ section, action }: Props) {
  const { top, big } = plate(section);
  return (
    <header className={`sign sign--${section.confidence} sign--${section.kind}`}>
      <div className="sign-plate" aria-hidden>
        <span className="sign-plate-top">{top}</span>
        <span className="sign-plate-big">{big}</span>
      </div>
      <div className="sign-body">
        <h2 className="sign-title">{section.title}</h2>
        <p className="sign-sub">{section.subtitle}</p>
      </div>
      <div className="sign-side">
        <span className="sign-confidence">{CONFIDENCE_LABEL[section.confidence]}</span>
        {action}
      </div>
    </header>
  );
}
