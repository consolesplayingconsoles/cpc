"""Drive engine: replay a data stream (e.g. a vacuum's cleaning route) as controller
input. `controller` is the generic translator + output sinks; `dreame_events` is the
Dreame-specific adapter that turns routes/state into action triggers. Lazy-loaded by
api.py's Robutek drive (dev-only: the KeyboardSink needs pynput + macOS)."""
