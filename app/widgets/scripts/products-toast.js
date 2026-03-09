(function () {
  const attach = (ctx) => {
    const layer = document.getElementById("products-toast-layer");
    if (!(layer instanceof HTMLElement)) {
      return;
    }
    if (layer.parentElement !== document.body) {
      document.body.append(layer);
    }

    const MAX_VISIBLE_TOASTS = 7;
    const DEFAULT_DURATION_MS = 1300;
    const productsToastQueue = [];
    const activeToasts = [];

    const positionLayer = () => {
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
      const layerWidth = Math.min(264, Math.max(180, viewportWidth - 24));
      layer.style.top = "4px";
      layer.style.left = "8px";
      layer.style.right = "auto";
      layer.style.width = `${layerWidth}px`;
    };
    positionLayer();
    window.addEventListener("resize", positionLayer);
    window.addEventListener("scroll", positionLayer, { passive: true });
    window.setTimeout(positionLayer, 0);

    const createToastElement = (payload) => {
      const toast = document.createElement("article");
      toast.className = "products-toast";
      toast.setAttribute("role", "status");

      const header = document.createElement("header");
      header.className = "products-toast-header";

      const status = document.createElement("p");
      status.className = "products-toast-status";

      const statusIcon = document.createElement("span");
      statusIcon.className = "products-toast-status-icon";
      statusIcon.textContent = "✓";

      const statusText = document.createElement("span");
      statusText.textContent = payload.title;

      status.append(statusIcon, statusText);

      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "products-toast-close";
      closeButton.setAttribute("aria-label", "Закрыть уведомление");
      closeButton.textContent = "×";

      header.append(status, closeButton);

      const message = document.createElement("p");
      message.className = "products-toast-message";
      message.textContent = payload.message;

      toast.append(header, message);
      return { toast, closeButton };
    };

    const dismissToast = (record) => {
      const activeIndex = activeToasts.indexOf(record);
      if (activeIndex >= 0) {
        activeToasts.splice(activeIndex, 1);
      }
      if (record.timerId) {
        window.clearTimeout(record.timerId);
        record.timerId = 0;
      }
      record.element.classList.remove("is-visible");
      record.element.classList.add("is-leaving");
      window.setTimeout(() => {
        if (record.element.parentElement === layer) {
          record.element.remove();
        }
        showFromQueue();
      }, 180);
    };

    const showFromQueue = () => {
      while (productsToastQueue.length > 0 && activeToasts.length < MAX_VISIBLE_TOASTS) {
        const nextPayload = productsToastQueue.shift();
        if (!nextPayload) {
          continue;
        }

        const { toast, closeButton } = createToastElement(nextPayload);
        layer.append(toast);
        toast.classList.add("is-visible");

        const record = {
          element: toast,
          timerId: 0,
        };
        activeToasts.push(record);

        closeButton.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          dismissToast(record);
        });

        record.timerId = window.setTimeout(dismissToast, nextPayload.durationMs, record);
      }
    };

    const enqueue = (payload) => {
      positionLayer();
      productsToastQueue.push({
        title: String(payload?.title || "Успешно"),
        message: String(payload?.message || "Успешно добавлен в корзину"),
        durationMs: Number(payload?.durationMs) > 0 ? Number(payload.durationMs) : DEFAULT_DURATION_MS,
      });
      showFromQueue();
    };

    ctx.toast = {
      enqueue,
    };
  };

  window.ProductsToast = {
    attach,
  };
})();
