(() => {
  const attach = (ctx) => {
    const { state, utils } = ctx;
    let sessionId = window.openai?.widgetState?.cartSessionId || "";
    let queue = Promise.resolve();
    let inFlight = 0;
    const unavailableTools = new Set();
    const references = new Map();
    try {
      sessionId ||= localStorage.getItem("apteka_cart_session_id") || "";
    } catch (_error) {
      /* Sandboxed storage may be unavailable. */
    }

    const saveSession = (id) => {
      sessionId = id || "";
      try {
        if (id) localStorage.setItem("apteka_cart_session_id", id);
        else localStorage.removeItem("apteka_cart_session_id");
      } catch (_error) {
        /* Keep using the host's widget state. */
      }
      window.openai?.setWidgetState?.({
        ...window.openai?.widgetState,
        cartSessionId: sessionId,
      });
    };
    const call = async (name, args = {}) => {
      if (typeof window.openai?.callTool !== "function")
        throw new Error("OpenAI tool bridge is unavailable");
      inFlight += 1;
      try {
        const result = await window.openai.callTool(name, {
          ...(sessionId ? { cart_session_id: sessionId } : {}),
          ...args,
        });
        const rpcError = result?.error;
        if (rpcError)
          throw Object.assign(new Error(rpcError.message), {
            code: rpcError.code,
          });
        const payload =
          result?.structuredContent ||
          result?.result?.structuredContent ||
          result;
        if (result?.isError || payload?.error)
          throw new Error(
            payload?.error?.message ||
              result?.content?.find((item) => item.type === "text")?.text ||
              "Apteka request failed",
          );
        if (payload?.cart_session_id) saveSession(payload.cart_session_id);
        return payload;
      } finally {
        inFlight -= 1;
      }
    };
    // Only a definitive tool-discovery failure permits the compatibility call.
    // Network errors and business errors must never retry a real transaction.
    const preferred = async (name, args, legacyName, legacyArgs = args) => {
      if (unavailableTools.has(name)) return call(legacyName, legacyArgs);
      try {
        return await call(name, args);
      } catch (error) {
        if (
          error?.code !== -32601 &&
          !/^(?:unknown tool|tool not found|tool unavailable)\b/i.test(
            error?.message || "",
          )
        )
          throw error;
        unavailableTools.add(name);
        return call(legacyName, legacyArgs);
      }
    };
    const cartPayload = (payload) => {
      const cart = payload.cart || payload;
      const items = (cart.items || []).map((item) => {
        const id = String(item.product_id || item.id);
        const known =
          state.products.find((product) => product.id === id) ||
          state.cartItems.find((product) => product.id === id) ||
          {};
        const price = Number(item.price);
        const discount = Number(item.discount_price);
        return {
          ...known,
          ...item,
          id,
          name: item.name || known.name || id,
          name_ru: known.nameRu || item.name,
          name_ro: known.nameRo,
          price: discount > 0 && discount < price ? discount : price,
          image_url: item.image_url || known.imageUrl,
          product_url: known.productUrl,
        };
      });
      return { ...payload, cart: { ...cart, items, synced: true } };
    };
    const cart = (name, args = {}) => {
      const task = queue.then(async () => {
        if (name === "sync_cart")
          return cartPayload(
            await preferred(
              sessionId ? "check_cart" : "sync_cart",
              {},
              "my_cart",
            ),
          );
        state.checkoutConfirmationId = "";
        if (name === "add_to_cart")
          return cartPayload(
            await preferred(
              "add_to_cart",
              {
                product_id: String(args.product.id),
                quantity: 1,
              },
              "add_to_my_cart",
            ),
          );
        return cartPayload(
          await preferred(
            "update_cart_item",
            {
              product_id: String(args.product_id),
              quantity: args.quantity,
            },
            "add_to_my_cart",
            {
              items: [
                {
                  product_id: String(args.product_id),
                  quantity: args.quantity,
                },
              ],
            },
          ),
        );
      });
      queue = task.catch(() => {});
      return task;
    };
    const getOptions = async () => {
      await queue;
      const language = utils.getActiveLanguage();
      if (!references.has(language)) {
        const task = preferred(
          "get_checkout_options",
          { language },
          "checkout_order",
          { action: "options", language },
        );
        references.set(language, task);
        task.catch(() => references.delete(language));
      }
      const payload = await references.get(language);
      if (payload.status === "cart_empty") {
        references.delete(language);
        throw new Error("Корзина пуста");
      }
      return payload;
    };
    const translated = (name, address = "") => ({
      ru: { name, address },
      ro: { name, address },
    });
    const lookup = async (path) => {
      const options = await getOptions();
      if (path === "/regions")
        return options.regions.map((region) => ({
          ...region,
          deliveryCost: region.delivery_cost,
          freeShippingCost: region.free_shipping_cost,
          translations: translated(region.name),
        }));
      if (path === "/pharmacies/list")
        return options.pharmacies.map((pharmacy) => {
          const region = options.regions.find(
            (item) => item.id === pharmacy.region_id,
          );
          const city = options.cities.find(
            (item) => item.id === pharmacy.city_id,
          );
          return {
            id: pharmacy.id,
            translations: translated(pharmacy.name, pharmacy.address),
            schedule: pharmacy.schedule,
            region: {
              id: pharmacy.region_id,
              translations: translated(region?.name || ""),
            },
            sector: {
              id: pharmacy.city_id,
              translations: translated(city?.name || ""),
            },
          };
        });
      if (path.startsWith("/cities-by-region/")) {
        const regionId = Number(path.split("/").at(-1));
        return options.cities
          .filter((city) => city.region_id === regionId)
          .map((city) => ({ ...city, translations: translated(city.name) }));
      }
      const pickup = path.includes("/pick-up/");
      const destination = Number(path.split("/").at(-1));
      const deliveryArgs = {
        language: utils.getActiveLanguage(),
        delivery_method: pickup ? "pickup" : "courier",
        ...(pickup ? { pharmacy_id: destination } : { region_id: destination }),
      };
      const response = await preferred(
        "get_delivery_windows",
        deliveryArgs,
        "checkout_order",
        { ...deliveryArgs, action: "delivery" },
      );
      const groups = {};
      for (const slot of response.windows || []) {
        groups[slot.deliveryDate] ||= [];
        groups[slot.deliveryDate].push(slot);
      }
      return {
        ...response.windows?.[0],
        ...(pickup ? {} : { availableWindows: groups }),
      };
    };
    const reviewArguments = (payload) => {
      const [first_name, ...last] = payload.customer_name.trim().split(/\s+/);
      const slot = payload.delivery_window;
      return {
        language: payload.language,
        delivery_method: payload.delivery_method,
        region_id: payload.region_id,
        city_id: payload.sector_id,
        pharmacy_id: payload.pharmacy_id,
        contact: {
          first_name,
          last_name: last.join(" "),
          phone: payload.customer_phone,
          email: payload.email,
        },
        address: {
          street: payload.street,
          house_number: payload.building,
          apartment: payload.apartment,
          entrance: payload.entrance,
          floor: payload.floor,
          intercom_code: payload.intercom_code,
        },
        payment_method:
          payload.payment_method === "card"
            ? "card_on_receipt"
            : "cash_on_receipt",
        ...(slot
          ? {
              delivery_window: {
                deliveryDate: slot.deliveryDate,
                from: slot.from,
                to: slot.to,
              },
            }
          : {}),
        comment: payload.comment,
      };
    };
    const review = async (payload) => {
      await queue;
      state.checkoutConfirmationId = "";
      const args = reviewArguments(payload);
      const result = await preferred("review_order", args, "checkout_order", {
        ...args,
        action: "review",
      });
      if (result.status !== "review")
        throw new Error("Не удалось проверить заказ. Обновите корзину.");
      state.checkoutConfirmationId = result.confirmation_id;
      state.checkoutReviewData = result.review;
      return result;
    };
    const submit = async () => {
      await queue;
      if (!state.checkoutConfirmationId)
        throw new Error("Проверьте заказ перед отправкой.");
      const args = {
        confirmation_id: state.checkoutConfirmationId,
        terms_accepted: true,
      };
      const result = await preferred("submit_order", args, "checkout_order", {
        ...args,
        action: "submit",
      });
      if (result.status !== "order_submitted" || !result.order_id)
        throw new Error(
          "Статус заказа не подтверждён. Обратитесь в поддержку.",
        );
      saveSession("");
      references.clear();
      return { ...result, order_id: result.order_number || result.order_id };
    };
    const hydrate = (candidate) => {
      let payload = candidate;
      if (payload.cart_session_id) saveSession(payload.cart_session_id);
      if (payload.status === "review") {
        state.checkoutConfirmationId = payload.confirmation_id;
        state.checkoutReviewData = payload.review;
        state.checkoutDraft = payload.review.checkout_input;
        restoreDraft();
        payload = {
          ...payload,
          cart: { items: payload.review.items, total: payload.review.subtotal },
          checkout_step: "review",
        };
      }
      if (payload.status === "order_submitted") {
        state.orderSubmitted = true;
        state.lastOrderId = payload.order_number || payload.order_id;
        payload = { ...payload, cart: { items: [] }, checkout_step: "success" };
      }
      return Array.isArray(payload.items) || payload.cart
        ? cartPayload(payload)
        : payload;
    };
    const panel = ctx.dom.cartPanel;
    const restoreDraft = () => {
      const draft = state.checkoutDraft;
      if (!draft) return;
      const { dom } = ctx;
      const contact = draft.contact;
      dom.checkoutName.value = [contact.first_name, contact.last_name]
        .filter(Boolean)
        .join(" ");
      dom.checkoutPhone.value = contact.phone;
      ctx.actions.formatCheckoutPhone();
      dom.checkoutEmail.value = contact.email || "";
      dom.checkoutComment.value = draft.comment || "";
      const fields = {
        checkoutStreet: "street",
        checkoutBuilding: "house_number",
        checkoutApartment: "apartment",
        checkoutEntrance: "entrance",
        checkoutFloor: "floor",
        checkoutIntercom: "intercom_code",
      };
      for (const [control, key] of Object.entries(fields))
        dom[control].value = draft.address?.[key] || "";
      dom.checkoutForm.querySelector(
        `input[name="products-delivery-method"][value="${draft.delivery_method}"]`,
      ).checked = true;
      const payment =
        draft.payment_method === "card_on_receipt" ? "card" : "cash";
      dom.checkoutForm.querySelector(
        `input[name="products-payment-method"][value="${payment}"]`,
      ).checked = true;
      if (!state.checkoutLookupsLoaded) return;
      const preview = state.checkoutReviewData;
      if (draft.delivery_method === "pickup")
        state.checkoutPickupCache[String(draft.pharmacy_id)] =
          preview.delivery_window;
      else {
        const groups = {};
        for (const slot of preview.available_windows) {
          groups[slot.deliveryDate] ||= [];
          groups[slot.deliveryDate].push(slot);
        }
        state.checkoutTargetCache[String(draft.region_id)] = {
          availableWindows: groups,
        };
      }
      dom.checkoutRegion.value = String(draft.region_id);
      ctx.ui.renderCheckout();
      dom.checkoutSector.value = String(draft.city_id);
      ctx.ui.renderCheckout();
      if (draft.pharmacy_id)
        dom.checkoutPharmacy.value = String(draft.pharmacy_id);
      state.checkoutDraft = null;
      ctx.ui.renderCheckout();
    };
    panel?.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const controls = [
        ...panel.querySelectorAll(
          "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]",
        ),
      ].filter((item) => item.tabIndex >= 0 && item.getClientRects().length);
      const first = controls[0];
      const last = controls.at(-1);
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === panel)
      ) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    });
    ctx.api = {
      cart,
      lookup,
      review,
      submit,
      hydrate,
      restoreDraft,
      busy: () => inFlight > 0,
      flush: () => queue,
    };
  };
  window.ProductsApi = { attach };
})();
