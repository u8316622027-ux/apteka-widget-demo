(function () {
  const attach = (ctx) => {
    const LAST_SEARCH_QUERY_KEY = "apteka_widget_last_query";
    const { state, dom, constants, utils, cart, sync } = ctx;
    const { input, cartModal } = dom;
    const { INITIAL_PAYLOAD_WAIT_MS, INITIAL_PAYLOAD_POLL_MS } = constants;
    const { normalizeText, debugLog, extractItems, mapProduct, setLoading, getPriceForCart } = utils;
    const {
      readLocalCart,
      readCartItems,
      normalizeCartQuantity,
      readStoredCartSessionId,
      ensureLocalCartBootstrap,
      rememberCartItem,
      writeLocalCartAdd,
      syncLocalCartFromToolPayload,
      writeLocalCart,
    } = {
      ...cart,
      normalizeCartQuantity: utils.normalizeCartQuantity,
    };
    const { enqueueCartSync } = sync;

    const callAddToMyCart = (product) => {
      const productId = normalizeText(product?.id);
      if (!productId) {
        debugLog("call_add_to_my_cart_skipped", { reason: "empty_product_id" });
        return Promise.resolve();
      }
      const payload = {
        product_id: productId,
        use_add_endpoint: true,
        name: normalizeText(product?.name) || undefined,
        price: typeof product?.price === "number" ? product.price : undefined,
        discount_price:
          typeof product?.discountPrice === "number" ? product.discountPrice : undefined,
        manufacturer: normalizeText(product?.manufacturer) || undefined,
        image_url: normalizeText(product?.imageUrl) || undefined,
      };
      debugLog("call_add_to_my_cart_start", { productId, source: "subject_fallback" });
      if (typeof window.openai?.callTool !== "function") {
        debugLog("call_add_to_my_cart_error", { reason: "openai.callTool unavailable" });
        return Promise.reject(new Error("openai.callTool is unavailable"));
      }
      return window.openai.callTool("add_to_my_cart", payload).then((result) => {
        debugLog("call_add_to_my_cart_done", {
          hasStructuredContent: Boolean(result && result.structuredContent),
        });
        return result;
      });
    };

    const callSetCartItemQuantity = () => {
      if (typeof window.openai?.callTool !== "function") {
        return Promise.reject(new Error("openai.callTool is unavailable"));
      }
      const localCart = readLocalCart();
      const cartItems = readCartItems();
      const cartSessionId = readStoredCartSessionId();
      const nextLocalCart = { ...localCart };
      const payloadItems = Object.entries(localCart)
        .map(([productId, rawQuantity]) => {
          const normalizedProductId = normalizeText(productId);
          const quantity = normalizeCartQuantity(rawQuantity);
          if (!normalizedProductId || quantity < 0) {
            return null;
          }
          const itemMeta =
            cartItems[normalizedProductId] && typeof cartItems[normalizedProductId] === "object"
              ? cartItems[normalizedProductId]
              : {};
          if (quantity > 0) {
            const price = getPriceForCart(itemMeta);
            if (price <= 0) {
              delete nextLocalCart[normalizedProductId];
              itemMeta.price = 0;
              itemMeta.discountPrice = 0;
              return null;
            }
          }
          return {
            product_id: normalizedProductId,
            quantity,
            name: normalizeText(itemMeta?.name) || undefined,
            manufacturer: normalizeText(itemMeta?.manufacturer) || undefined,
            price: typeof itemMeta?.price === "number" ? itemMeta.price : undefined,
            discount_price: typeof itemMeta?.discountPrice === "number" ? itemMeta.discountPrice : undefined,
            image_url: normalizeText(itemMeta?.imageUrl) || undefined,
          };
        })
        .filter(Boolean);
      writeLocalCart(nextLocalCart);
      if (!payloadItems.length) {
        return Promise.resolve();
      }
      const payload = {
        items: payloadItems,
        cart_session_id: cartSessionId || undefined,
      };
      return window.openai.callTool("add_to_my_cart", payload);
    };

    const bootstrapCartFromBackend = async () => {
      if (typeof window.openai?.callTool !== "function") {
        return false;
      }
      try {
        const storedSessionId = readStoredCartSessionId();
        const toolResult = await window.openai.callTool("my_cart", {
          cart_session_id: storedSessionId || undefined,
        });
        return syncLocalCartFromToolPayload(toolResult);
      } catch (_error) {
        return false;
      }
    };

    const wait = (delayMs) =>
      new Promise((resolve) => {
        window.setTimeout(resolve, delayMs);
      });

    const ensureCartBootstrapWithRetry = async () => {
      for (let attempt = 0; attempt < 6; attempt += 1) {
        const ok = await bootstrapCartFromBackend();
        if (ok) {
          state.cartBootstrapCompleted = true;
          return true;
        }
        await wait(180);
      }
      return false;
    };

    const scheduleDeferredCartBootstrap = () => {
      const startedAt = Date.now();
      const maxDurationMs = 18000;
      const attemptEveryMs = 1200;

      const run = () => {
        if (state.cartBootstrapCompleted) {
          return;
        }
        if (ctx.root.getAttribute("aria-hidden") === "true") {
          return;
        }
        if (Date.now() - startedAt > maxDurationMs) {
          return;
        }
        Promise.resolve(ensureCartBootstrapWithRetry())
          .then((ok) => {
            if (ok) {
              return;
            }
            window.setTimeout(() => {
              run();
            }, attemptEveryMs);
          })
          .catch(() => {
            window.setTimeout(() => {
              run();
            }, attemptEveryMs);
          });
      };

      window.setTimeout(() => {
        run();
      }, attemptEveryMs);
    };

    const extractToolPage = (payload) => {
      if (!payload || typeof payload !== "object") {
        return "";
      }
      const widgetNode = payload.widget && typeof payload.widget === "object" ? payload.widget : {};
      const openNode = widgetNode.open && typeof widgetNode.open === "object" ? widgetNode.open : {};
      return (
        normalizeText(openNode.page) ||
        normalizeText(payload.widget_page) ||
        normalizeText(payload.page)
      ).toLowerCase();
    };

    const hasSearchResultsPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return false;
      }
      return (
        Array.isArray(payload.products) ||
        Array.isArray(payload.results) ||
        Object.prototype.hasOwnProperty.call(payload, "no_results") ||
        Object.prototype.hasOwnProperty.call(payload, "query")
      );
    };

    const hasTrackingPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return false;
      }
      return Array.isArray(payload.orders) || Object.prototype.hasOwnProperty.call(payload, "lookup");
    };

    const extractInitialToolPayload = () => {
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
        if (!candidate || typeof candidate !== "object") {
          continue;
        }
        syncLocalCartFromToolPayload(candidate);
        if (Array.isArray(candidate.products) || Array.isArray(candidate.items) || Array.isArray(candidate.results)) {
          return candidate;
        }
        if (
          candidate.structuredContent &&
          typeof candidate.structuredContent === "object" &&
          (Array.isArray(candidate.structuredContent.products) ||
            Array.isArray(candidate.structuredContent.items) ||
            Array.isArray(candidate.structuredContent.results))
        ) {
          syncLocalCartFromToolPayload(candidate.structuredContent);
          return candidate.structuredContent;
        }
      }
      return null;
    };

    const extractPayloadFromMessage = (rawMessage) => {
      if (!rawMessage || typeof rawMessage !== "object") {
        return null;
      }
      const candidates = [
        rawMessage,
        rawMessage.payload,
        rawMessage.data,
        rawMessage.result,
        rawMessage.result?.structuredContent,
        rawMessage.structuredContent,
      ];
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object") {
          continue;
        }
        syncLocalCartFromToolPayload(candidate);
        if (Array.isArray(candidate.products) || Array.isArray(candidate.items) || Array.isArray(candidate.results)) {
          return candidate;
        }
        if (
          candidate.structuredContent &&
          typeof candidate.structuredContent === "object" &&
          (Array.isArray(candidate.structuredContent.products) ||
            Array.isArray(candidate.structuredContent.items) ||
            Array.isArray(candidate.structuredContent.results))
        ) {
          syncLocalCartFromToolPayload(candidate.structuredContent);
          return candidate.structuredContent;
        }
      }
      return null;
    };

    const applyInitialToolPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return false;
      }
      if (normalizeText(payload.api_base_url)) {
        state.apiBaseUrl = normalizeText(payload.api_base_url);
      }
      const requestedPage = extractToolPage(payload);
      if (requestedPage) {
        state.requestedPage = requestedPage;
      }
      if (hasTrackingPayload(payload)) {
        state.tracking = {
          lookup: normalizeText(payload.lookup),
          count: Number(payload.count) || 0,
          orders: Array.isArray(payload.orders) ? payload.orders : [],
        };
      }
      const query = normalizeText(payload.query);
      if (query) {
        try {
          window.localStorage.setItem(LAST_SEARCH_QUERY_KEY, query);
        } catch (_error) {
          // ignore storage write errors
        }
      }
      const isSearchPayload = hasSearchResultsPayload(payload) || !requestedPage || requestedPage === "search";
      if (isSearchPayload) {
        const mapped = extractItems(payload).map(mapProduct).filter((product) => product.id);
        if (query && input) {
          input.value = query;
        }
        state.products = mapped;
        state.lastQuery = query;
        state.loadedOnce = true;
        return true;
      }
      state.loadedOnce = true;
      return true;
    };

    const tryHydrateInitialPayload = () => {
      const payload = extractInitialToolPayload();
      if (!payload) {
        return false;
      }
      if (!applyInitialToolPayload(payload)) {
        return false;
      }
      setLoading(false);
      ctx.ui.renderProducts();
      return true;
    };

    const waitForInitialPayload = () =>
      new Promise((resolve) => {
        if (tryHydrateInitialPayload()) {
          resolve(true);
          return;
        }

        const onMessage = (event) => {
          const messagePayload = extractPayloadFromMessage(event?.data);
          if (!messagePayload) {
            return;
          }
          if (!applyInitialToolPayload(messagePayload)) {
            return;
          }
          window.clearInterval(intervalId);
          window.clearTimeout(timeoutId);
          window.removeEventListener("message", onMessage);
          setLoading(false);
          ctx.ui.renderProducts();
          resolve(true);
        };

        window.addEventListener("message", onMessage, { passive: true });

        const intervalId = window.setInterval(() => {
          if (!tryHydrateInitialPayload()) {
            return;
          }
          window.clearInterval(intervalId);
          window.clearTimeout(timeoutId);
          window.removeEventListener("message", onMessage);
          resolve(true);
        }, INITIAL_PAYLOAD_POLL_MS);

        const timeoutId = window.setTimeout(() => {
          window.clearInterval(intervalId);
          window.removeEventListener("message", onMessage);
          resolve(false);
        }, INITIAL_PAYLOAD_WAIT_MS);
      });

    const searchProducts = async (query) => {
      const normalized = normalizeText(query);
      if (!normalized) {
        return;
      }
      if (state.isSearching) {
        return;
      }

      state.isSearching = true;
      state.lastQuery = normalized;
      try {
        window.localStorage.setItem(LAST_SEARCH_QUERY_KEY, normalized);
      } catch (_error) {
        // ignore storage write errors
      }
      setLoading(true);

      try {
        if (typeof window.openai?.callTool !== "function") {
          throw new Error("openai.callTool is unavailable");
        }
        const toolResult = await window.openai.callTool("search_products", { query: normalized });
        const payload =
          (toolResult && typeof toolResult === "object" && toolResult.structuredContent) ||
          toolResult ||
          {};
        if (normalizeText(payload.api_base_url)) {
          state.apiBaseUrl = normalizeText(payload.api_base_url);
        }
        state.requestedPage = "search";
        state.products = extractItems(payload).map(mapProduct).filter((product) => product.id);
      } catch (_error) {
        state.products = [];
      } finally {
        state.isSearching = false;
        state.loadedOnce = true;
        setLoading(false);
        ctx.ui.renderProducts();
      }
    };

    const addToCart = (productId) => {
      debugLog("add_to_cart_click", { productId });
      if (ctx.toast && typeof ctx.toast.enqueue === "function") {
        ctx.toast.enqueue({
          title: "Успешно",
          message: "Успешно добавлен в корзину",
        });
      }
      writeLocalCartAdd(productId);
      const product = state.products.find((item) => item.id === productId) || null;
      rememberCartItem(productId);
      ctx.ui.renderCartBadge();
      if (cartModal && !cartModal.hidden) {
        ctx.ui.renderCartModal();
      }
      ctx.ui.renderPageCart();
      ctx.ui.renderCheckoutSummary();
      enqueueCartSync(() => callAddToMyCart(product)).catch((error) => {
        debugLog("call_add_to_my_cart_error", {
          message: String(error && error.message ? error.message : error),
        });
        console.error("products cart sync failed", error);
      });
    };

    ctx.actions.callSetCartItemQuantity = callSetCartItemQuantity;
    ctx.actions.searchProducts = searchProducts;
    ctx.actions.addToCart = addToCart;

    ctx.tools = {
      ensureLocalCartBootstrap,
      ensureCartBootstrapWithRetry,
      scheduleDeferredCartBootstrap,
      waitForInitialPayload,
    };
  };

  window.ProductsTools = {
    attach,
  };
})();
