(function () {
  const root = document.querySelector("[data-widget-shell]");
  if (!root) {
    return;
  }

  const activeWidgetId = String(root.getAttribute("data-widget-shell") || "").trim();
  if (!activeWidgetId || typeof window.BroadcastChannel !== "function") {
    return;
  }

  const channel = new window.BroadcastChannel("apteka-widget-shell");
  let active = true;

  channel.onmessage = (event) => {
    const nextWidgetId = String(event?.data?.widgetId || "").trim();
    if (!nextWidgetId || nextWidgetId === activeWidgetId || !active) {
      return;
    }

    active = false;
    root.style.display = "none";
    root.setAttribute("aria-hidden", "true");
    try {
      window.close();
    } catch (_error) {
      return;
    }
  };

  channel.postMessage({ widgetId: activeWidgetId, openedAt: Date.now() });
})();
