/**
 * app.js — minimal SSE → HTMX bridge.
 *
 * The server emits SSE events of shape:
 *   event: db_changed
 *   data: {"type":"db_changed","collection":"queue","path":"db/queue.json"}
 *
 * We re-dispatch them as DOM CustomEvents on <body> so HTMX fragments can
 * use ``hx-trigger="db-changed:<collection> from:body"`` to refresh.
 *
 * Loaded ONCE from base.html with defer. Do NOT inline in fragments — HTMX
 * 2.x re-executes <script> tags on swap and would register N listeners.
 */
(function () {
  function dispatch(name, detail) {
    document.body.dispatchEvent(
      new CustomEvent(name, { detail: detail, bubbles: false })
    );
  }

  document.body.addEventListener("htmx:sseMessage", function (evt) {
    try {
      var data = JSON.parse(evt.detail.data || "{}");
      if (data.type === "db_changed" && data.collection) {
        dispatch("db-changed:" + data.collection, data);
      } else if (data.type === "queue_bundle_changed") {
        dispatch("db-changed:queue", data);
      }
    } catch (e) {
      /* ignore malformed events */
    }
  });
})();
