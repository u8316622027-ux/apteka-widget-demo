(() => {
  const attach = (ctx) => {
    const THEME_MODE_KEY = "apteka_widget_theme_mode";
    const THEME_VALUE_KEY = "apteka_widget_theme_value";
    const { root, utils } = ctx;
    const { normalizeText, debugLog } = utils;
    const indicator = document.getElementById("theme-debug-indicator") || null;
    const notice = document.getElementById("theme-notice") || null;
    let noticeTimeoutId = 0;

    const normalizeTheme = (value) => {
      const normalized = normalizeText(value).toLowerCase();
      if (normalized.startsWith("dark")) {
        return "dark";
      }
      if (normalized.startsWith("light")) {
        return "light";
      }
      return "";
    };

    const readStorage = (key) => {
      try {
        return window.localStorage.getItem(key);
      } catch (_error) {
        return null;
      }
    };

    const writeStorage = (key, value) => {
      try {
        window.localStorage.setItem(key, value);
      } catch (_error) {
        // ignore storage errors
      }
    };

    const resolveHostTheme = () => {
      const openaiTheme =
        normalizeTheme(window.openai?.theme) ||
        normalizeTheme(window.openai?.user?.theme) ||
        normalizeTheme(window.openai?.preferences?.theme) ||
        normalizeTheme(window.__OPENAI_THEME__);
      if (openaiTheme) {
        return openaiTheme;
      }
      try {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        if (media.matches) {
          return "dark";
        }
      } catch (_error) {
        // ignore matchMedia errors
      }
      return "light";
    };

    const resolveIndicatorValue = (mode, theme) => {
      const isAuto = mode === "auto";
      const isDark = theme === "dark";
      if (isAuto) {
        return isDark ? "1.2" : "1.1";
      }
      return isDark ? "2.2" : "2.1";
    };

    const updateIndicator = (mode, theme) => {
      if (!(indicator instanceof HTMLElement)) {
        return;
      }
      const value = resolveIndicatorValue(mode, theme);
      indicator.textContent = value;
      indicator.dataset.themeMode = mode;
      indicator.dataset.themeValue = theme;
    };

    const showNotice = (message) => {
      if (!(notice instanceof HTMLElement)) {
        return;
      }
      const text = normalizeText(message);
      if (!text) {
        return;
      }
      notice.textContent = text;
      notice.classList.add("is-visible");
      if (noticeTimeoutId) {
        window.clearTimeout(noticeTimeoutId);
      }
      noticeTimeoutId = window.setTimeout(() => {
        notice.classList.remove("is-visible");
      }, 6000);
    };

    const applyTheme = (theme) => {
      const normalized = normalizeTheme(theme) || "light";
      root.setAttribute("data-theme", normalized);
      document.documentElement.setAttribute("data-theme", normalized);
      writeStorage(THEME_VALUE_KEY, normalized);
      updateIndicator(
        normalizeText(readStorage(THEME_MODE_KEY)) || "auto",
        normalized,
      );
      debugLog("theme_applied", { theme: normalized });
    };

    const applyAutoTheme = () => {
      applyTheme(resolveHostTheme());
    };

    const listenToSchemeChanges = () => {
      try {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        media.addEventListener("change", () => {
          if (normalizeText(readStorage(THEME_MODE_KEY)) === "auto") {
            applyAutoTheme();
          }
        });
      } catch (_error) {
        // ignore matchMedia errors
      }
    };

    const setManualTheme = (theme) => {
      writeStorage(THEME_MODE_KEY, "manual");
      applyTheme(theme);
    };

    const setAutoTheme = () => {
      writeStorage(THEME_MODE_KEY, "auto");
      applyAutoTheme();
    };

    const loadInitialTheme = () => {
      const mode = normalizeText(readStorage(THEME_MODE_KEY)) || "auto";
      const value = normalizeText(readStorage(THEME_VALUE_KEY));
      if (mode === "manual" && value) {
        applyTheme(value);
        return;
      }
      setAutoTheme();
    };

    const updateFromPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return;
      }
      showNotice(
        payload.assistant_notice || payload.notice || payload.message || "",
      );
      const mode = normalizeText(payload.theme_mode || payload.mode);
      const theme = normalizeTheme(payload.theme);
      if (payload.auto_disabled === false) {
        setAutoTheme();
        return;
      }
      if (payload.auto_disabled === true && theme) {
        setManualTheme(theme);
        return;
      }
      if (mode === "auto") {
        setAutoTheme();
        return;
      }
      if (theme) {
        setManualTheme(theme);
      }
    };

    loadInitialTheme();
    listenToSchemeChanges();

    ctx.theme = {
      updateFromPayload,
      setManualTheme,
      setAutoTheme,
    };
  };

  window.ProductsTheme = {
    attach,
  };
})();
