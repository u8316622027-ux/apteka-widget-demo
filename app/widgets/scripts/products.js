(function () {
  const root = document.querySelector("[data-widget-shell]");
  if (!root) {
    return;
  }

  if (typeof window.ProductsState?.createContext !== "function") {
    return;
  }

  const ctx = window.ProductsState.createContext(root);
  window.ProductsRender.attach(ctx);
  window.ProductsTools.attach(ctx);
  if (typeof window.ProductsSupport?.attach === "function") {
    window.ProductsSupport.attach(ctx);
  }
  if (typeof window.ProductsToast?.attach === "function") {
    window.ProductsToast.attach(ctx);
  }

  const { state, dom, utils, cart, sync, ui, actions, tools } = ctx;
  const { input, searchButton, track, leftArrow, rightArrow, cartButton, cartModal, cartModalClose, cartModalItems } = dom;
  const { normalizeText, debugLog } = utils;
  const { readLocalCart, writeLocalCart } = cart;
  const { enqueueCartSync } = sync;
  const { searchProducts, addToCart, callSetCartItemQuantity } = actions;

  const scrollTrack = (direction) => {
    if (!track) {
      return;
    }
    const firstCard = track.querySelector(".product-card");
    const step = firstCard instanceof HTMLElement ? firstCard.offsetWidth + 14 : 280;
    track.scrollBy({ left: direction * step, behavior: "smooth" });
    window.setTimeout(ui.updateCarouselControls, 280);
  };

  if (leftArrow) {
    leftArrow.addEventListener("click", () => scrollTrack(-1));
  }
  if (rightArrow) {
    rightArrow.addEventListener("click", () => scrollTrack(1));
  }
  if (track) {
    track.addEventListener("scroll", ui.updateCarouselControls);
    track.addEventListener("click", (event) => {
      const path =
        typeof event.composedPath === "function"
          ? event.composedPath()
          : [];
      const pathButton = path.find(
        (node) =>
          node instanceof Element &&
          node.matches?.("[data-action]"),
      );
      const target = event.target;
      const fallbackButton =
        target instanceof Element
          ? target.closest("[data-action]")
          : target?.parentElement?.closest("[data-action]");
      const actionButton = pathButton || fallbackButton;
      debugLog("track_click", {
        hasPathButton: Boolean(pathButton),
        hasFallbackButton: Boolean(fallbackButton),
      });
      if (actionButton instanceof HTMLElement) {
        const action = normalizeText(actionButton.dataset.action);
        if (action === "add-to-cart") {
          addToCart(normalizeText(actionButton.dataset.productId));
          return;
        }
        if (action === "support-contact") {
          event.preventDefault();
          event.stopPropagation();
          if (typeof actions.openSupportPopup === "function") {
            actions.openSupportPopup(actionButton);
          }
        }
      }
    });
  }

  if (searchButton) {
    searchButton.addEventListener("click", (event) => {
      event.preventDefault();
      searchProducts(input ? input.value : "");
    });
  }

  if (input) {
    input.addEventListener("focus", () => {
      if (!state.loadedOnce) {
        searchProducts(input.value);
      }
    });
    input.addEventListener("click", () => {
      if (!state.loadedOnce) {
        searchProducts(input.value);
      }
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        searchProducts(input.value);
      }
    });
  }

  if (cartButton) {
    cartButton.addEventListener("click", () => {
      ui.toggleCartModal(true);
    });
  }

  if (cartModalClose) {
    cartModalClose.addEventListener("click", () => {
      ui.toggleCartModal(false);
    });
  }

  if (cartModal) {
    cartModal.addEventListener("click", (event) => {
      if (event.target === cartModal) {
        ui.toggleCartModal(false);
      }
    });
  }

  if (cartModalItems) {
    cartModalItems.addEventListener("click", (event) => {
      const target = event.target;
      const actionElement =
        target instanceof Element ? target.closest("[data-action]") : target?.parentElement?.closest("[data-action]");
      if (!(actionElement instanceof HTMLElement)) {
        return;
      }
      const action = normalizeText(actionElement.dataset.action);
      if (!action) {
        return;
      }
      const row = actionElement.closest("[data-product-id]");
      if (!(row instanceof HTMLElement)) {
        return;
      }
      const productId = normalizeText(row.dataset.productId);
      if (!productId) {
        return;
      }
      const payload = readLocalCart();
      const currentQty = Number(payload[productId]) || 0;
      if (action === "cart-increase") {
        payload[productId] = currentQty + 1;
      } else if (action === "cart-decrease") {
        const nextQty = currentQty - 1;
        if (nextQty > 0) {
          payload[productId] = nextQty;
        } else {
          delete payload[productId];
        }
      } else {
        return;
      }
      writeLocalCart(payload);
      ui.renderCartBadge();
      ui.renderCartModal();
      enqueueCartSync(() => callSetCartItemQuantity()).catch((error) => {
        debugLog("call_add_to_my_cart_error", {
          message: String(error && error.message ? error.message : error),
        });
      });
    });
  }

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cartModal && !cartModal.hidden) {
      ui.toggleCartModal(false);
    }
  });

  tools.ensureLocalCartBootstrap();
  debugLog("widget_bootstrap", {
    hasOpenAi: Boolean(window.openai),
    hasCallTool: typeof window.openai?.callTool === "function",
  });
  ui.renderCartBadge();
  utils.setLoading(true);
  ui.renderProducts();
  tools.scheduleDeferredCartBootstrap();

  Promise.resolve(tools.ensureCartBootstrapWithRetry())
    .then(() => tools.waitForInitialPayload())
    .then((didHydrateFromToolPayload) => {
      if (!didHydrateFromToolPayload) {
        state.loadedOnce = true;
        utils.setLoading(false);
        ui.renderProducts();
      }
      ui.updateCarouselControls();
    });

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
  };
  channel.postMessage({ widgetId: activeWidgetId, openedAt: Date.now() });
})();
