import React from "react";
import "./styles/error-boundary.css";

/**
 * Stops one bad render from blanking the whole app.
 *
 * Without this, a throw during render unmounts the tree and the user sees a
 * white page with nothing to act on -- which is what a non-array symbol list
 * used to do to the Backtest page.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled render error:", error, info);
  }

  handleReload = () => {
    this.setState({ error: null });
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="error-boundary" role="alert">
        <h2>This page stopped responding</h2>
        <p>
          Something went wrong while rendering. Reloading usually clears it. If it
          keeps happening, the API may be returning something unexpected.
        </p>
        <pre>{String(this.state.error?.message || this.state.error)}</pre>
        <button type="button" onClick={this.handleReload}>
          Reload page
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
