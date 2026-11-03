'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * Catches a module screen that throws while rendering, so one broken screen is one broken
 * screen: the rail and every other module stay usable.
 *
 * The shell keys it by the address, so moving to another screen starts it afresh. "Try again"
 * renders the same screen once more, which is enough when the failure came from something that
 * has since changed — a response that arrived half-formed, say.
 */
type Props = { label: string; children: ReactNode };
type State = { error: Error | null };

export class ScreenBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(thrown: unknown): State {
    return { error: thrown instanceof Error ? thrown : new Error(String(thrown)) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`The ${this.props.label} screen failed`, error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    return (
      <main className="screen screen-failed">
        <h1>{this.props.label} stopped working</h1>
        <p className="error" role="alert">
          {error.message || 'The screen failed without saying why.'}
        </p>
        <p className="muted">
          The rest of the editor still works. Try this screen again, or open another one from the
          navigation.
        </p>
        <button type="button" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </main>
    );
  }
}
