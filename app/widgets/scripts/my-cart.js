(function () {
  const root = document.querySelector("[data-widget-shell='my_cart']");
  if (!root || typeof window.MyCartState?.createContext !== "function") {
    return;
  }

  const ctx = window.MyCartState.createContext(root);
  if (typeof window.MyCartRender?.attach === "function") {
    window.MyCartRender.attach(ctx);
  }

  const { dom, cart, ui, state, utils } = ctx;
  const { items, backButton, checkoutButton } = dom;
  const { normalizeText } = utils;

  const hydrateFromInitialPayload = () => {
    const candidates = [
      window.__APTEKA_WIDGET_PAYLOAD__,
      window.__MCP_STRUCTURED_CONTENT__,
      window.__MCP_TOOL_RESULT__,
      window.__OPENAI_TOOL_RESULT__,
      window.__INITIAL_TOOL_RESULT__,
      window.openai?.structuredContent,
      window.openai?.toolResult?.structuredContent,
      window.openai?.toolResult,
      window.openai?.toolOutput?.structuredContent,
      window.openai?.toolOutput,
      window.openai?.lastToolResult?.structuredContent,
      window.openai?.lastToolResult,
    ];
    for (const candidate of candidates) {
      if (cart.syncLocalCartFromToolPayload(candidate)) {
        return true;
      }
    }
    return false;
  };

  const render = () => {
    cart.buildRows();
    if (ui && typeof ui.render === "function") {
      ui.render();
    }
  };

  const refreshFromBackend = async () => {
    if (typeof window.openai?.callTool !== "function") {
      return false;
    }
    const toolResult = await window.openai.callTool("my_cart", {
      cart_session_id: cart.readStoredCartSessionId() || undefined,
    });
    cart.syncLocalCartFromToolPayload(toolResult);
    render();
    return true;
  };

  const setQuantity = async (productId, quantity) => {
    const normalizedProductId = normalizeText(productId);
    if (!normalizedProductId) {
      return;
    }
    const nextCart = {
      ...cart.readLocalCart(),
      [normalizedProductId]: quantity,
    };
    if (quantity <= 0) {
      delete nextCart[normalizedProductId];
    }
    cart.writeLocalCart(nextCart);
    render();
    if (typeof window.openai?.callTool !== "function") {
      return;
    }
    const itemMeta = cart.readCartItems()[normalizedProductId] || {};
    const payload = {
      cart_session_id: cart.readStoredCartSessionId() || undefined,
      items: [
        {
          product_id: normalizedProductId,
          quantity: quantity > 0 ? quantity : 0,
          name: normalizeText(itemMeta.name) || undefined,
          manufacturer: normalizeText(itemMeta.manufacturer) || undefined,
          price: typeof itemMeta.price === "number" ? itemMeta.price : undefined,
          discount_price:
            typeof itemMeta.discountPrice === "number" ? itemMeta.discountPrice : undefined,
          image_url: normalizeText(itemMeta.imageUrl) || undefined,
        },
      ],
    };
    const result = await window.openai.callTool("add_to_my_cart", payload);
    cart.syncLocalCartFromToolPayload(result);
    render();
  };

  const goBackToProducts = async () => {
    if (typeof window.openai?.openWidget === "function") {
      await window.openai.openWidget("ui://widget/products.html", { replace_previous: true });
      return;
    }
    const lastQuery = cart.readLastSearchQuery();
    if (typeof window.openai?.callTool === "function" && lastQuery) {
      await window.openai.callTool("search_products", { query: lastQuery });
    }
  };

  const openCheckout = async () => {
    if (state.count <= 0 || typeof window.openai?.callTool !== "function") {
      return;
    }
    const toolResult = await window.openai.callTool("checkout_order", {
      cart_session_id: cart.readStoredCartSessionId() || undefined,
    });
    const structuredPayload =
      toolResult && typeof toolResult === "object" && toolResult.structuredContent
        ? toolResult.structuredContent
        : toolResult;
    const template = normalizeText(structuredPayload?.widget?.open?.template) || "ui://widget/products.html";
    if (typeof window.openai?.openWidget === "function") {
      await window.openai.openWidget(template, { replace_previous: true });
    }
  };

  if (items instanceof HTMLElement) {
    items.addEventListener("click", (event) => {
      const target = event.target;
      const button =
        target instanceof Element ? target.closest("[data-action]") : null;
      if (!(button instanceof HTMLElement)) {
        return;
      }
      const card = button.closest("[data-product-id]");
      if (!(card instanceof HTMLElement)) {
        return;
      }
      const productId = normalizeText(card.dataset.productId);
      const localCart = cart.readLocalCart();
      const currentQuantity = cart.normalizeCartQuantity(localCart[productId]);
      if (button.dataset.action === "increase") {
        void setQuantity(productId, currentQuantity + 1);
        return;
      }
      if (button.dataset.action === "decrease") {
        void setQuantity(productId, Math.max(0, currentQuantity - 1));
        return;
      }
      if (button.dataset.action === "remove") {
        void setQuantity(productId, 0);
      }
    });
  }

  if (backButton instanceof HTMLElement) {
    backButton.addEventListener("click", () => {
      void goBackToProducts();
    });
  }

  if (checkoutButton instanceof HTMLElement) {
    checkoutButton.addEventListener("click", () => {
      void openCheckout();
    });
  }

  hydrateFromInitialPayload();
  render();
  void refreshFromBackend().catch(() => {
    render();
  });
})();
