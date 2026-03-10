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
  const {
    input,
    searchButton,
    track,
    leftArrow,
    rightArrow,
    cartButton,
    cartModal,
    cartModalClose,
    cartModalItems,
    goToCartButton,
    checkoutButton,
    pageCartItems,
    pageCartCheckoutButton,
    pageCartContinueButton,
    backFromMyCartButton,
    backFromCheckoutButton,
    backFromTrackingButton,
    checkoutForm,
    checkoutName,
    checkoutPhone,
  } = dom;
  const { normalizeText, debugLog } = utils;
  const { readLocalCart, writeLocalCart, readStoredCartSessionId } = cart;
  const { enqueueCartSync } = sync;
  const { searchProducts, addToCart, callSetCartItemQuantity } = actions;
  const MIN_CHECKOUT_TOTAL_MDL = 30;
  let cartSyncTimerId = 0;
  let checkoutBackPage = "search";
  let currentPage = "search";

  const openaiApi = window.openai;
  const hasCallTool = typeof openaiApi?.callTool === "function";
  const hasOpenWidget = typeof openaiApi?.openWidget === "function";

  const resolveWidgetPage = (pageName) => {
    const normalizedPage = normalizeText(pageName).toLowerCase();
    if (normalizedPage === "my_cart") {
      return "my-cart";
    }
    if (normalizedPage === "checkout_order") {
      return "checkout";
    }
    if (normalizedPage === "track_order_status_ui") {
      return "tracking";
    }
    const allowedPages = ["search", "my-cart", "checkout", "tracking"];
    return allowedPages.includes(normalizedPage) ? normalizedPage : "search";
  };

  const showInternalPage = (pageName) => {
    currentPage = resolveWidgetPage(pageName);
    ui.showInternalPage(currentPage);
  };

  const openInternalRouteIfSupported = (template, source, pageHint) => {
    if (hasOpenWidget) {
      return false;
    }
    const normalizedTemplate = normalizeText(template).toLowerCase();
    const normalizedPageHint = resolveWidgetPage(pageHint);
    if (normalizedTemplate.includes("products") && normalizedPageHint !== "search") {
      showInternalPage(normalizedPageHint);
      debugLog("widget_open_success", { template, via: "internal-router", source });
      return true;
    }
    if (normalizedTemplate.includes("my-cart")) {
      showInternalPage("my-cart");
      debugLog("widget_open_success", { template, via: "internal-router", source });
      return true;
    }
    if (normalizedTemplate.includes("checkout")) {
      showInternalPage("checkout");
      debugLog("widget_open_success", { template, via: "internal-router", source });
      return true;
    }
    if (normalizedTemplate.includes("tracking")) {
      showInternalPage("tracking");
      debugLog("widget_open_success", { template, via: "internal-router", source });
      return true;
    }
    return false;
  };

  const openWidgetByTemplate = async (template, fallbackTool, fallbackArgs) => {
    debugLog("widget_open_attempt", {
      template,
      fallbackTool,
      hasOpenWidget,
      hasCallTool,
      });
    try {
      const pageHint =
        fallbackArgs && typeof fallbackArgs === "object" ? fallbackArgs.toolPage : "";
      if (hasOpenWidget) {
        await openaiApi.openWidget(template, { replace_previous: true });
        debugLog("widget_open_success", { template, via: "openWidget" });
        return;
      }

      if (!hasOpenWidget) {
        if (openInternalRouteIfSupported(template, "direct", pageHint)) {
          return;
        }
      }

      if (!hasCallTool) {
        debugLog("widget_open_error", {
          template,
          message: "openWidget unavailable and callTool is missing",
          level: "error",
        });
        return;
      }

      const fallbackToolName = normalizeText(fallbackTool);
      if (!fallbackToolName) {
        debugLog("widget_open_error", {
          template,
          message: "fallback tool is empty",
          level: "error",
        });
        return;
      }

      debugLog("widget_open_fallback_tool", {
        template,
        tool: fallbackToolName,
      });
      const toolResult = await openaiApi.callTool(fallbackToolName, fallbackArgs || {});
      const structuredPayload =
        toolResult && typeof toolResult === "object" && toolResult.structuredContent
          ? toolResult.structuredContent
          : toolResult;
      const fallbackTemplate = normalizeText(structuredPayload?.widget?.open?.template);
      const fallbackPage = normalizeText(structuredPayload?.widget?.open?.page) || pageHint;
      if (!fallbackTemplate) {
        debugLog("widget_open_error", {
          template,
          tool: fallbackToolName,
          message: "tool result has no widget.open.template",
          level: "error",
        });
        return;
      }

      if (hasOpenWidget) {
        const replacePrevious = structuredPayload?.widget?.open?.replace_previous !== false;
        await openaiApi.openWidget(fallbackTemplate, { replace_previous: replacePrevious });
        debugLog("widget_open_success", {
          template: fallbackTemplate,
          via: "tool+openWidget",
          tool: fallbackToolName,
        });
        return;
      }

      if (!hasOpenWidget) {
        if (openInternalRouteIfSupported(fallbackTemplate, "tool-template", fallbackPage)) {
          return;
        }
      }

      debugLog("widget_open_error", {
        template: fallbackTemplate,
        via: "tool-no-host-open",
        tool: fallbackToolName,
        message: "tool returned template but openWidget is unavailable",
        level: "error",
      });
    } catch (error) {
      debugLog("widget_open_error", {
        template,
        fallbackTool,
        message: String(error && error.message ? error.message : error),
        level: "error",
      });
    }
  };

  const scheduleCartQuantitySync = () => {
    window.clearTimeout(cartSyncTimerId);
    cartSyncTimerId = window.setTimeout(() => {
      enqueueCartSync(() => callSetCartItemQuantity()).catch((error) => {
        debugLog("call_add_to_my_cart_error", {
          message: String(error && error.message ? error.message : error),
        });
      });
    }, 260);
  };

  const refreshCartViews = () => {
    ui.renderCartBadge();
    ui.renderCartModal();
    ui.renderPageCart();
    ui.renderCheckoutSummary();
  };

  const applyCartAction = (productId, action) => {
    action = normalizeText(action);
    productId = normalizeText(productId);
    if (!action || !productId) {
      return;
    }

    const payload = readLocalCart();
    const currentQty = Number(payload[productId]) || 0;
    if (action === "cart-increase") {
      payload[productId] = currentQty + 1;
    } else if (action === "cart-decrease") {
      const nextQty = currentQty - 1;
      payload[productId] = nextQty > 0 ? nextQty : 0;
    } else if (action === "cart-remove") {
      payload[productId] = 0;
    } else {
      return;
    }

    writeLocalCart(payload);
    refreshCartViews();
    scheduleCartQuantitySync();
  };

  const onCartListClick = (event) => {
    const target = event.target;
    const actionElement =
      target instanceof Element ? target.closest("[data-action]") : target?.parentElement?.closest("[data-action]");
    if (!(actionElement instanceof HTMLElement)) {
      return;
    }
    const row = actionElement.closest("[data-product-id]");
    if (!(row instanceof HTMLElement)) {
      return;
    }
    applyCartAction(row.dataset.productId, actionElement.dataset.action);
  };

  const validateCheckout = () => {
    const { total, count } = ui.getCartSummary();
    if (count <= 0) {
      if (ctx.toast && typeof ctx.toast.enqueue === "function") {
        ctx.toast.enqueue({
          title: "Внимание",
          message: "У вас пустая корзина",
          durationMs: 1600,
          kind: "error",
        });
      }
      return false;
    }
    if (total < MIN_CHECKOUT_TOTAL_MDL) {
      if (ctx.toast && typeof ctx.toast.enqueue === "function") {
        ctx.toast.enqueue({
          title: "Внимание",
          message: "Минимальная сумма заказа 30 mdl",
          durationMs: 1600,
          kind: "error",
        });
      }
      return false;
    }
    return true;
  };

  const openCheckoutFlow = (sourcePage) => {
    if (!validateCheckout()) {
      return;
    }
    checkoutBackPage = sourcePage === "my-cart" ? "my-cart" : "search";
    const cartSessionId = readStoredCartSessionId();
    debugLog("cart_navigation_click", {
      target: "checkout_order",
      cartSessionId: cartSessionId || null,
    });
    ui.toggleCartModal(false);
    void openWidgetByTemplate("ui://widget/products.html", "checkout_order", {
      cart_session_id: cartSessionId || undefined,
      toolPage: "checkout",
    });
  };

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
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      const pathButton = path.find((node) => node instanceof Element && node.matches?.("[data-action]"));
      const target = event.target;
      const fallbackButton =
        target instanceof Element ? target.closest("[data-action]") : target?.parentElement?.closest("[data-action]");
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
    cartModalItems.addEventListener("click", onCartListClick);
  }

  if (pageCartItems) {
    pageCartItems.addEventListener("click", onCartListClick);
  }

  if (goToCartButton) {
    goToCartButton.addEventListener("click", () => {
      const cartSessionId = readStoredCartSessionId();
      debugLog("cart_navigation_click", {
        target: "my_cart",
        cartSessionId: cartSessionId || null,
      });
      ui.toggleCartModal(false);
      void openWidgetByTemplate("ui://widget/my-cart.html", "my_cart", {
        cart_session_id: cartSessionId || undefined,
        toolPage: "my-cart",
      });
    });
  }

  if (checkoutButton) {
    checkoutButton.addEventListener("click", () => {
      openCheckoutFlow("search");
    });
  }

  if (pageCartCheckoutButton) {
    pageCartCheckoutButton.addEventListener("click", () => {
      openCheckoutFlow("my-cart");
    });
  }

  if (pageCartContinueButton) {
    pageCartContinueButton.addEventListener("click", () => {
      showInternalPage("search");
    });
  }

  if (backFromMyCartButton) {
    backFromMyCartButton.addEventListener("click", () => {
      showInternalPage("search");
    });
  }

  if (backFromCheckoutButton) {
    backFromCheckoutButton.addEventListener("click", () => {
      showInternalPage(checkoutBackPage);
    });
  }

  if (backFromTrackingButton) {
    backFromTrackingButton.addEventListener("click", () => {
      showInternalPage("search");
    });
  }

  if (checkoutForm instanceof HTMLFormElement) {
    checkoutForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const nameValue = normalizeText(checkoutName?.value);
      const phoneValue = normalizeText(checkoutPhone?.value);
      if (!nameValue || !phoneValue) {
        if (ctx.toast && typeof ctx.toast.enqueue === "function") {
          ctx.toast.enqueue({
            title: "Внимание",
            message: "Заполните имя и телефон",
            durationMs: 1700,
            kind: "error",
          });
        }
        return;
      }
      if (ctx.toast && typeof ctx.toast.enqueue === "function") {
        ctx.toast.enqueue({
          title: "Успешно",
          message: "Данные заказа заполнены",
          durationMs: 1500,
        });
      }
      showInternalPage("search");
    });
  }

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cartModal && !cartModal.hidden) {
      ui.toggleCartModal(false);
      return;
    }
    if (event.key === "Escape" && currentPage !== "search") {
      showInternalPage("search");
    }
  });

  tools.ensureLocalCartBootstrap();
  debugLog("widget_bootstrap", {
    hasOpenAi: Boolean(openaiApi),
    hasCallTool,
    hasOpenWidget,
  });
  ui.renderCartBadge();
  ui.renderPageCart();
  ui.renderCheckoutSummary();
  ui.renderTrackingPage();
  showInternalPage("search");
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
      ui.renderPageCart();
      ui.renderCheckoutSummary();
      ui.renderTrackingPage();
      showInternalPage(state.requestedPage || "search");
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
