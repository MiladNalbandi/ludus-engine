'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

/**
 * Small pieces the module screens share. Plain buttons and lists, nothing nested inside anything
 * interactive: the journey test once caught reorder buttons inside a button, which a screen reader
 * announces as one control and a keyboard cannot reach.
 */

/**
 * A delete that asks once. The first press shows the question in place; the answer buttons are
 * real buttons, and focus moves to "Keep it" so that a second Enter does not delete by accident.
 */
export function ConfirmDelete({
  what,
  onConfirm,
  disabled,
}: {
  what: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const [asking, setAsking] = useState(false);
  const keep = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (asking) {
      keep.current?.focus();
    }
  }, [asking]);

  if (!asking) {
    return (
      <button
        type="button"
        className="danger small"
        aria-label={`Delete ${what}`}
        disabled={disabled}
        onClick={() => setAsking(true)}
      >
        Delete
      </button>
    );
  }

  return (
    <span className="actions" role="group" aria-label={`Delete ${what}?`}>
      <span>Delete {what} for good?</span>
      <button
        type="button"
        className="danger small"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        Yes, delete
      </button>
      <button ref={keep} type="button" className="quiet small" onClick={() => setAsking(false)}>
        Keep it
      </button>
    </span>
  );
}

/** The problems found before sending, one per line, announced when they appear. */
export function Problems({ problems }: { problems: readonly string[] }) {
  if (problems.length === 0) {
    return null;
  }
  return (
    <ul className="error" role="alert" style={{ margin: 0, paddingLeft: '1.1rem' }}>
      {problems.map((problem) => (
        <li key={problem}>{problem}</li>
      ))}
    </ul>
  );
}

/** A failure from the engine, in its own words. */
export function EngineError({ message }: { message: string | null }) {
  return message ? (
    <p className="error" role="alert">
      {message}
    </p>
  ) : null;
}

/** Tabs between a module's screens. Links, so each tab has its own address and Back works. */
export function SubNav({
  label,
  tabs,
}: {
  label: string;
  tabs: { href: string; label: string; current: boolean }[];
}) {
  return (
    <nav aria-label={label}>
      <ul className="subnav">
        {tabs.map((tab) => (
          <li key={tab.href}>
            <Link href={tab.href} aria-current={tab.current ? 'page' : undefined}>
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
