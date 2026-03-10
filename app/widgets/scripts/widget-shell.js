(function () {
  const NAV_BACK_STORAGE_KEY = "apteka_widget_nav_back_map";
  const memoryStorage = Object.create(null);
  const root = document.querySelector("[data-widget-shell]");
  if (!root) {
    return;
  }

  const normalizeText = (value) => String(value || "").trim();
  const activeWidgetId = normalizeText(root.getAttribute("data-widget-shell"));
  const backButton = document.getElementById("widget-back-button");
  const backTarget = normalizeText(backButton?.getAttribute("data-back-target")) || activeWidgetId;

  const readStorageValue = (key) => {
    try {
      return window.localStorage.getItem(key);
    } catch (_error) {
      return Object.prototype.hasOwnProperty.call(memoryStorage, key) ? String(memoryStorage[key]) : null;
    }
  };

  const writeStorageValue = (key, value) => {
    const normalizedValue = String(value);
    try {
      window.localStorage.setItem(key, normalizedValue);
      return;
    } catch (_error) {
      memoryStorage[key] = normalizedValue;
    }
  };

  const readBackMap = () => {
    try {
      const payload = JSON.parse(readStorageValue(NAV_BACK_STORAGE_KEY) || "{}");
      return payload && typeof payload === "object" ? payload : {};
    } catch (_error) {
      return {};
    }
  };

  const writeBackMap = (nextMap) => {
    writeStorageValue(NAV_BACK_STORAGE_KEY, JSON.stringify(nextMap));
  };

  const resolveBackEntry = () => {
    const backMap = readBackMap();
    const candidate = backMap[backTarget];
    if (!candidate || typeof candidate !== "object") {
      return null;
    }
    const tool = normalizeText(candidate.tool);
    if (!tool) {
      return null;
    }
    const argumentsPayload =
      candidate.arguments && typeof candidate.arguments === "object" ? candidate.arguments : {};
    return {
      tool,
      arguments: argumentsPayload,
    };
  };

  const openWidgetByTemplate = async (template, replacePrevious) => {
    if (typeof window.openai?.openWidget === "function") {
      await window.openai.openWidget(template, { replace_previous: replacePrevious });
    }
  };

  if (backButton instanceof HTMLButtonElement) {
    backButton.addEventListener("click", () => {
      const backEntry = resolveBackEntry();
      if (!backEntry) {
        return;
      }
      const backMap = readBackMap();
      delete backMap[activeWidgetId];
      writeBackMap(backMap);
      if (typeof window.openai?.callTool !== "function") {
        return;
      }
      void window.openai
        .callTool(backEntry.tool, backEntry.arguments || {})
        .then((toolResult) => {
          const structuredPayload =
            toolResult && typeof toolResult === "object" && toolResult.structuredContent
              ? toolResult.structuredContent
              : toolResult;
          const template = normalizeText(structuredPayload?.widget?.open?.template);
          if (!template) {
            return;
          }
          const replacePrevious = structuredPayload?.widget?.open?.replace_previous !== false;
          return openWidgetByTemplate(template, replacePrevious);
        });
    });
  }

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

    const backMap = readBackMap();
    backMap[nextWidgetId] = {
      tool: activeWidgetId,
      arguments: {},
    };
    writeBackMap(backMap);

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
