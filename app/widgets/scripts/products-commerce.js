(() => {
  const attach = (ctx) => {
    const { root, state, utils } = ctx;
    const { escapeHtml: esc, getActiveLanguage, toMoney } = utils;
    const $ = (id) => document.getElementById(id);
    const text = (ru, ro) => (getActiveLanguage() === "ro" ? ro : ru);
    const search = $("products-page-search");
    const cartPage = $("products-page-my-cart");
    const checkoutPage = $("products-page-checkout");
    const form = $("checkout-form");
    const reviewNode = $("checkout-review");
    const successNode = $("checkout-success");
    let sessionId = "";
    let cart = { items: [], count: 0, total: 0 };
    let options = null;
    let confirmationId = "";
    let reviewArgs = null;
    let busy = false;
    try {
      sessionId =
        window.openai?.widgetState?.cartSessionId ||
        window.localStorage.getItem("apteka_cart_session_id") ||
        "";
    } catch (_error) {
      // Storage can be unavailable in a sandboxed iframe.
    }

    const saveSession = (value) => {
      sessionId = value || "";
      try {
        if (sessionId)
          window.localStorage.setItem("apteka_cart_session_id", sessionId);
        else window.localStorage.removeItem("apteka_cart_session_id");
      } catch (_error) {
        // The host's widget state also survives iframe recreation.
      }
      window.openai?.setWidgetState?.({
        ...window.openai?.widgetState,
        cartSessionId: sessionId,
      });
    };
    const showError = (message = "") => {
      $("commerce-error").textContent = message;
      $("commerce-error").hidden = !message;
    };
    const notice = (message = "") => {
      $("commerce-notice").textContent = message;
      $("commerce-notice").hidden = !message;
    };
    const call = async (name, args = {}) => {
      if (typeof window.openai?.callTool !== "function") {
        throw new Error(
          text(
            "Откройте виджет в ChatGPT, чтобы оформить заказ.",
            "Deschideți widgetul în ChatGPT pentru a comanda.",
          ),
        );
      }
      const result = await window.openai.callTool(name, {
        ...(sessionId ? { cart_session_id: sessionId } : {}),
        ...args,
      });
      const payload =
        result?.structuredContent ||
        result?.result?.structuredContent ||
        result;
      if (result?.isError || payload?.error) {
        throw new Error(
          payload?.error?.message ||
            result?.content?.find((item) => item.type === "text")?.text ||
            text("Не удалось выполнить действие", "Acțiunea nu a reușit"),
        );
      }
      if (payload?.cart_session_id) saveSession(payload.cart_session_id);
      return payload;
    };
    const run = async (operation) => {
      if (busy) return;
      busy = true;
      root.setAttribute("aria-busy", "true");
      showError();
      const buttons = [...root.querySelectorAll("button")].map((button) => [
        button,
        button.disabled,
      ]);
      for (const [button] of buttons) button.disabled = true;
      try {
        await operation();
      } catch (error) {
        showError(
          error?.message ||
            text(
              "Ошибка соединения. Попробуйте позже.",
              "Eroare de conexiune. Încercați mai târziu.",
            ),
        );
      } finally {
        busy = false;
        root.setAttribute("aria-busy", "false");
        for (const [button, disabled] of buttons) {
          if (button.isConnected) button.disabled = disabled;
        }
        $("cart-checkout").disabled = cart.items.length === 0;
        updateSubmit();
      }
    };
    const showPage = (page) => {
      search.hidden = page !== "search";
      cartPage.hidden = page !== "cart";
      checkoutPage.hidden = page !== "checkout";
      notice();
      const heading =
        page === "cart"
          ? $("cart-heading")
          : page === "checkout"
            ? $("checkout-heading")
            : ctx.dom.input;
      heading?.focus();
    };
    const renderCart = () => {
      const count = cart.items.reduce(
        (sum, item) => sum + Number(item.quantity),
        0,
      );
      $("cart-count").textContent = String(count);
      $("products-cart-button").setAttribute(
        "aria-label",
        `${text("Корзина", "Coș")}, ${count}`,
      );
      $("cart-heading").textContent = text("Корзина", "Coș");
      $("cart-total").textContent =
        `${text("Итого", "Total")}: ${toMoney(Number(cart.total || 0))}`;
      $("cart-checkout").textContent = text(
        "Оформить заказ",
        "Plasează comanda",
      );
      $("cart-checkout").disabled = cart.items.length === 0;
      $("cart-items").innerHTML = cart.items.length
        ? cart.items
            .map((item) => {
              const id = String(item.product_id);
              const name =
                item.name ||
                state.products.find((product) => product.id === id)?.name ||
                id;
              const price = Number(item.discount_price ?? item.price);
              return `<article class="cart-row" data-product-id="${esc(id)}">
          <div><h3>${esc(name)}</h3><p>${toMoney(price)}</p></div>
          <div class="cart-quantity">
            <button type="button" data-quantity="${Number(item.quantity) - 1}" aria-label="${text("Уменьшить количество", "Micșorează cantitatea")}">−</button>
            <span aria-label="${text("Количество", "Cantitate")}">${Number(item.quantity)}</span>
            <button type="button" data-quantity="${Number(item.quantity) + 1}" aria-label="${text("Увеличить количество", "Mărește cantitatea")}">+</button>
          </div>
          <button type="button" data-quantity="0" aria-label="${text("Удалить товар", "Elimină produsul")}">×</button>
        </article>`;
            })
            .join("")
        : `<p>${text("Корзина пуста. Добавьте товары из поиска.", "Coșul este gol. Adăugați produse din căutare.")}</p>`;
    };
    const applyCart = (payload) => {
      const next = payload.cart || payload;
      if (!Array.isArray(next.items)) return;
      cart = next;
      if (next.cart_session_id || payload.cart_session_id)
        saveSession(next.cart_session_id || payload.cart_session_id);
      confirmationId = "";
      renderCart();
    };
    const optionHtml = (items) =>
      items
        .map(
          (item) =>
            `<option value="${esc(item.id)}">${esc(item.name)}${item.address ? ` — ${esc(item.address)}` : ""}</option>`,
        )
        .join("");
    const field = (
      name,
      label,
      type = "text",
      required = false,
      autocomplete = "off",
    ) =>
      `<label>${label}<input name="${name}" type="${type}" ${required ? "required" : ""} autocomplete="${autocomplete}" ${name === "first_name" ? 'minlength="3"' : ""}></label>`;

    const filterDestinations = () => {
      const method = form.elements.delivery_method.value;
      const regionId = Number(form.elements.region_id.value);
      const pharmacyRegions = new Set(
        options.pharmacies.map((item) => item.region_id),
      );
      for (const option of form.elements.region_id.options) {
        option.hidden =
          method === "pickup" && !pharmacyRegions.has(Number(option.value));
      }
      if (form.elements.region_id.selectedOptions[0]?.hidden) {
        form.elements.region_id.value =
          [...form.elements.region_id.options].find((item) => !item.hidden)
            ?.value || "";
      }
      const selectedRegion = Number(form.elements.region_id.value) || regionId;
      const pharmacyCities = new Set(
        options.pharmacies
          .filter((item) => item.region_id === selectedRegion)
          .map((item) => item.city_id),
      );
      const cities = options.cities.filter(
        (item) =>
          item.region_id === selectedRegion &&
          (method === "courier" || pharmacyCities.has(item.id)),
      );
      const previousCity = form.elements.city_id.value;
      form.elements.city_id.innerHTML = optionHtml(cities);
      if (cities.some((item) => String(item.id) === previousCity))
        form.elements.city_id.value = previousCity;
      filterPharmacies();
      $("checkout-pickup-fields").hidden = method !== "pickup";
      $("checkout-address-fields").hidden = method !== "courier";
      form.elements.pharmacy_id.required = method === "pickup";
      for (const name of ["street", "house_number"])
        form.elements[name].required = method === "courier";
    };
    const filterPharmacies = () => {
      const previous = form.elements.pharmacy_id.value;
      const pharmacies = options.pharmacies.filter(
        (item) =>
          item.region_id === Number(form.elements.region_id.value) &&
          item.city_id === Number(form.elements.city_id.value),
      );
      form.elements.pharmacy_id.innerHTML = optionHtml(pharmacies);
      if (pharmacies.some((item) => String(item.id) === previous))
        form.elements.pharmacy_id.value = previous;
    };
    const renderForm = (payload) => {
      options = payload;
      confirmationId = "";
      reviewNode.hidden = true;
      successNode.hidden = true;
      form.hidden = false;
      $("checkout-heading").textContent = text(
        "Оформление заказа",
        "Plasarea comenzii",
      );
      form.innerHTML = `
        <fieldset><legend>${text("Способ получения", "Metoda de livrare")}</legend>
          <label class="commerce-choice"><input type="radio" name="delivery_method" value="pickup" checked>${text("Самовывоз", "Ridicare din farmacie")}</label>
          <label class="commerce-choice"><input type="radio" name="delivery_method" value="courier">${text("Курьерская доставка", "Livrare prin curier")}</label>
        </fieldset>
        <div class="checkout-grid">
          <label>${text("Регион", "Regiune")}<select name="region_id" required>${optionHtml(options.regions)}</select></label>
          <label>${text("Населённый пункт / сектор", "Localitate / sector")}<select name="city_id" required></select></label>
        </div>
        <div id="checkout-pickup-fields"><label>${text("Аптека", "Farmacie")}<select name="pharmacy_id" required></select></label></div>
        <fieldset id="checkout-address-fields" hidden><legend>${text("Адрес доставки", "Adresa de livrare")}</legend><div class="checkout-grid">
          ${field("street", text("Улица", "Strada"), "text", false, "address-line1")}
          ${field("house_number", text("Дом", "Bloc"))}
          ${field("apartment", text("Квартира", "Apartament"))}
          ${field("entrance", text("Подъезд", "Scara"))}
          ${field("floor", text("Этаж", "Etaj"))}
          ${field("intercom_code", text("Домофон", "Interfon"))}
        </div></fieldset>
        <fieldset><legend>${text("Контакты", "Date de contact")}</legend><div class="checkout-grid">
          ${field("first_name", text("Имя", "Prenume"), "text", true, "given-name")}
          ${field("last_name", text("Фамилия", "Nume"), "text", false, "family-name")}
          ${field("phone", text("Телефон", "Telefon"), "tel", true, "tel")}
          ${field("email", "Email", "email", false, "email")}
        </div><p class="commerce-hint">${text("Телефон в международном формате, например +37379802000", "Telefon în format internațional, de exemplu +37379802000")}</p></fieldset>
        <label>${text("Оплата", "Plată")}<select name="payment_method">
          <option value="cash_on_receipt">${text("Наличными при получении", "Numerar la primire")}</option>
          <option value="card_on_receipt">${text("Картой при получении", "Card la primire")}</option>
        </select></label>
        <label>${text("Комментарий", "Comentariu")}<textarea name="comment" rows="2" maxlength="1000"></textarea></label>
        <label class="commerce-choice"><input type="checkbox" name="dont_call_me">${text("Не звоните мне", "Nu mă sunați")}</label>
        <button type="submit" class="commerce-primary">${text("Проверить заказ", "Verifică comanda")}</button>`;
      filterDestinations();
    };
    const readForm = () => {
      const values = Object.fromEntries(new FormData(form));
      return {
        action: "review",
        language: getActiveLanguage(),
        delivery_method: values.delivery_method,
        region_id: Number(values.region_id),
        city_id: Number(values.city_id),
        pharmacy_id: Number(values.pharmacy_id) || undefined,
        contact: Object.fromEntries(
          ["first_name", "last_name", "phone", "email"].map((key) => [
            key,
            String(values[key] || "").trim(),
          ]),
        ),
        address: Object.fromEntries(
          [
            "street",
            "house_number",
            "apartment",
            "entrance",
            "floor",
            "intercom_code",
          ].map((key) => [key, String(values[key] || "").trim()]),
        ),
        payment_method: values.payment_method,
        comment: values.comment,
        dont_call_me: values.dont_call_me === "on",
      };
    };
    const updateSubmit = () => {
      const submit = $("checkout-confirm");
      if (submit)
        submit.disabled =
          busy || !confirmationId || !$("checkout-terms")?.checked;
    };
    const renderReview = (payload) => {
      confirmationId = payload.confirmation_id;
      const preview = payload.review;
      form.hidden = true;
      successNode.hidden = true;
      reviewNode.hidden = false;
      const contact = preview.contact || {};
      const windows = preview.available_windows || [preview.delivery_window];
      reviewNode.innerHTML = `<h3 tabindex="-1" id="review-heading">${text("Проверьте заказ", "Verificați comanda")}</h3>
        <ul>${preview.items.map((item) => `<li>${esc(item.name || item.product_id)} × ${Number(item.quantity)}</li>`).join("")}</ul>
        <p>${esc(preview.destination)}</p><p>${esc(contact.first_name)} ${esc(contact.last_name)} · ${esc(contact.phone)} · ${esc(contact.email)}</p>
        <label>${text("Время получения", "Interval de livrare")}<select id="checkout-window" ${windows.length < 2 ? "disabled" : ""}>${windows.map((window, index) => `<option value="${index}" ${JSON.stringify(window) === JSON.stringify(preview.delivery_window) ? "selected" : ""}>${esc(window.deliveryDate)} ${esc(window.from)}–${esc(window.to)}</option>`).join("")}</select></label>
        <p>${text("Оплата", "Plată")}: ${preview.payment_method === "card_on_receipt" ? text("Картой при получении", "Card la primire") : text("Наличными при получении", "Numerar la primire")}</p>
        <p>${text("Доставка", "Livrare")}: ${toMoney(Number(preview.delivery_fee))}</p>
        <p class="commerce-total">${text("Итого", "Total")}: ${toMoney(Number(preview.total))}</p>
        ${preview.comment ? `<p>${esc(preview.comment)}</p>` : ""}
        <label class="commerce-choice"><input type="checkbox" id="checkout-terms">${text("Принимаю условия", "Accept condițiile")}</label>
        <a href="https://www.apteka.md/${getActiveLanguage()}/news/polizovateliskoe-soglashenie" target="_blank" rel="noopener noreferrer">${text("Пользовательское соглашение", "Acordul utilizatorului")}</a>
        <div class="commerce-footer"><button type="button" id="checkout-edit">${text("Изменить", "Modifică")}</button>
          <button type="button" id="checkout-confirm" class="commerce-primary" disabled>${text("Подтвердить заказ", "Confirmă comanda")}</button></div>`;
      $("checkout-terms").addEventListener("change", updateSubmit);
      $("checkout-edit").addEventListener("click", () => {
        confirmationId = "";
        reviewNode.hidden = true;
        form.hidden = false;
        if (!form.innerHTML) openCheckout();
        else form.querySelector("input")?.focus();
      });
      $("checkout-window").addEventListener("change", (event) => {
        if (!reviewArgs) return;
        const selected = windows[Number(event.target.value)];
        confirmationId = "";
        updateSubmit();
        run(async () => {
          reviewArgs = { ...reviewArgs, delivery_window: selected };
          renderReview(await call("checkout_order", reviewArgs));
        });
      });
      $("checkout-confirm").addEventListener("click", () =>
        run(async () => {
          const result = await call("checkout_order", {
            action: "submit",
            confirmation_id: confirmationId,
            terms_accepted: true,
          });
          if (result.status !== "order_submitted")
            throw new Error(
              text("Заказ не подтверждён", "Comanda nu este confirmată"),
            );
          renderSuccess(result);
        }),
      );
      $("review-heading").focus();
    };
    const renderSuccess = (payload) => {
      confirmationId = "";
      reviewNode.hidden = true;
      form.hidden = true;
      successNode.hidden = false;
      successNode.textContent = `${text("Заказ оформлен", "Comanda a fost plasată")} № ${payload.order_number || payload.order_id}`;
      cart = { items: [], count: 0, total: 0 };
      saveSession("");
      renderCart();
    };
    const openCart = () =>
      run(async () => {
        applyCart(await call("my_cart"));
        showPage("cart");
      });
    const openCheckout = () =>
      run(async () => {
        const payload = await call("checkout_order", {
          action: "options",
          language: getActiveLanguage(),
        });
        if (payload.cart) applyCart(payload.cart);
        if (payload.status === "cart_empty") {
          showPage("cart");
          return;
        }
        renderForm(payload);
        showPage("checkout");
      });
    const applyPayload = (payload) => {
      const page = payload.widget?.open?.page || payload.widget_page;
      if (page !== "cart" && page !== "checkout") return false;
      if (payload.cart_session_id) saveSession(payload.cart_session_id);
      if (page === "cart") {
        applyCart(payload);
        showPage("cart");
      } else {
        if (payload.cart) applyCart(payload.cart);
        showPage("checkout");
        if (payload.status === "review") renderReview(payload);
        else if (payload.status === "order_submitted") renderSuccess(payload);
        else if (payload.status === "cart_empty") showPage("cart");
        else renderForm(payload);
      }
      return true;
    };
    $("products-cart-button").addEventListener("click", openCart);
    $("cart-checkout").addEventListener("click", openCheckout);
    for (const button of root.querySelectorAll("[data-commerce]")) {
      button.addEventListener("click", () => {
        if (busy) return;
        confirmationId = "";
        if (button.dataset.commerce === "cart") openCart();
        else showPage("search");
      });
    }
    $("cart-items").addEventListener("click", (event) => {
      const button = event.target.closest("[data-quantity]");
      if (!button) return;
      const id = button.closest("[data-product-id]").dataset.productId;
      run(async () => {
        applyCart(
          await call("add_to_my_cart", {
            items: [
              { product_id: id, quantity: Number(button.dataset.quantity) },
            ],
          }),
        );
        $("cart-items")
          .querySelector(`[data-product-id="${CSS.escape(id)}"] button`)
          ?.focus();
      });
    });
    form.addEventListener("change", (event) => {
      if (["delivery_method", "region_id"].includes(event.target.name))
        filterDestinations();
      if (event.target.name === "city_id") filterPharmacies();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      run(async () => {
        reviewArgs = readForm();
        const result = await call("checkout_order", reviewArgs);
        if (result.status === "cart_empty") {
          applyCart(result.cart);
          showPage("cart");
          return;
        }
        renderReview(result);
      });
    });
    window.addEventListener("openai:set_globals", (event) => {
      if (busy) return;
      const output = event.detail?.globals?.toolOutput;
      if (output) applyPayload(output.structuredContent || output);
    });
    ctx.commerce = {
      applyPayload,
      addProduct: (productId) =>
        run(async () => {
          applyCart(await call("add_to_my_cart", { product_id: productId }));
          notice(
            text("Товар добавлен в корзину", "Produsul a fost adăugat în coș"),
          );
        }),
    };
    renderCart();
  };
  window.ProductsCommerce = { attach };
})();
