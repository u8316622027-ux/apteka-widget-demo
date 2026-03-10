(function () {
  const attach = (ctx) => {
    const { state, dom, utils, cart } = ctx;
    const {
      track,
      leftArrow,
      rightArrow,
      cartBadge,
      cartModal,
      cartModalItems,
      cartModalTotal,
      pageCartItems,
      pageCartTotal,
      checkoutItems,
      checkoutTotal,
      pageSearch,
      pageMyCart,
      pageCheckout,
      pageTracking,
      trackingLookup,
      trackingCount,
      trackingOrders,
    } = dom;
    const { normalizeText, escapeHtml, toMoney, computeDiscount, getFallbackImage, getPriceForCart } = utils;
    const { readLocalCartCount, readLocalCart, writeLocalCart, readCartItems } = cart;

    const getCartSummary = (persistInvalidCleanup = false) => {
      const cartPayload = readLocalCart();
      const cartItems = readCartItems();
      const nextCartPayload = { ...cartPayload };
      const invalidProductIds = [];
      const rows = Object.entries(cartPayload)
        .map(([productId, rawQuantity]) => {
          const quantity = Number(rawQuantity);
          if (!Number.isFinite(quantity) || quantity <= 0) {
            return null;
          }
          const fromProductsState = state.products.find((entry) => entry.id === productId) || null;
          const item = (cartItems[productId] && typeof cartItems[productId] === "object" ? cartItems[productId] : fromProductsState) || {};
          const linePrice = getPriceForCart(item);
          if (!Number.isFinite(linePrice) || linePrice <= 0) {
            invalidProductIds.push(productId);
            return null;
          }
          return {
            productId,
            quantity,
            name: normalizeText(item.name) || `Товар #${productId}`,
            manufacturer: normalizeText(item.manufacturer) || "Производитель не указан",
            priceText: toMoney(linePrice),
            lineTotalText: `Итого: ${toMoney(linePrice * quantity)}`,
            imageUrl: normalizeText(item.imageUrl) || getFallbackImage(),
            lineTotal: linePrice * quantity,
          };
        })
        .filter(Boolean);

      if (persistInvalidCleanup && invalidProductIds.length) {
        for (const productId of invalidProductIds) {
          delete nextCartPayload[productId];
        }
        writeLocalCart(nextCartPayload);
      }

      const total = rows.reduce((sum, row) => sum + row.lineTotal, 0);
      const count = rows.reduce((sum, row) => sum + row.quantity, 0);
      return { rows, total, count };
    };

    const buildCartRowNode = (row, interactive) => {
      const article = document.createElement("article");
      article.className = "cart-modal-item";
      article.dataset.productId = row.productId;

      const image = document.createElement("img");
      image.className = "cart-modal-item-image";
      image.src = row.imageUrl;
      image.alt = row.name;
      image.loading = "lazy";
      image.addEventListener("error", () => {
        image.src = getFallbackImage();
      });

      const content = document.createElement("div");
      content.className = "cart-modal-item-content";

      const name = document.createElement("p");
      name.className = "cart-modal-item-name";
      name.textContent = row.name;

      const manufacturer = document.createElement("p");
      manufacturer.className = "cart-modal-item-meta";
      manufacturer.textContent = row.manufacturer;

      const price = document.createElement("p");
      price.className = "cart-modal-item-price";
      price.textContent = row.priceText;

      const lineTotal = document.createElement("p");
      lineTotal.className = "cart-modal-item-line-total";
      lineTotal.textContent = row.lineTotalText;

      content.append(name, manufacturer, price);

      const qty = document.createElement("div");
      qty.className = "cart-modal-qty";
      const decrease = document.createElement("button");
      decrease.className = "cart-modal-qty-button";
      decrease.dataset.action = "cart-decrease";
      decrease.textContent = "−";
      decrease.setAttribute("aria-label", `Уменьшить количество ${row.name}`);
      const value = document.createElement("span");
      value.className = "cart-modal-qty-value";
      value.textContent = String(row.quantity);
      const increase = document.createElement("button");
      increase.className = "cart-modal-qty-button";
      increase.dataset.action = "cart-increase";
      increase.textContent = "+";
      increase.setAttribute("aria-label", `Увеличить количество ${row.name}`);

      qty.append(decrease, value, increase);
      const remove = document.createElement("button");
      remove.className = "cart-modal-remove";
      remove.dataset.action = "cart-remove";
      remove.textContent = "✕";
      remove.setAttribute("aria-label", `Удалить ${row.name} из корзины`);

      if (!interactive) {
        decrease.disabled = true;
        increase.disabled = true;
        remove.hidden = true;
        remove.setAttribute("aria-hidden", "true");
      }

      article.append(image, content, lineTotal, qty, remove);

      return article;
    };

    const renderCartRows = (container, totalNode, interactive) => {
      if (!(container instanceof HTMLElement) || !(totalNode instanceof HTMLElement)) {
        return;
      }
      const { rows, total } = getCartSummary(true);
      if (!rows.length) {
        const empty = document.createElement("p");
        empty.className = "cart-modal-empty";
        empty.textContent = "В корзине пока нет товаров";
        container.replaceChildren(empty);
        totalNode.textContent = "Итого: 0.00 MDL";
        return;
      }

      const rowNodes = rows.map((row) => buildCartRowNode(row, interactive));
      container.replaceChildren(...rowNodes);
      totalNode.textContent = `Итого: ${toMoney(total)}`;
    };

    const renderCartModal = () => {
      renderCartRows(cartModalItems, cartModalTotal, true);
    };

    const renderPageCart = () => {
      renderCartRows(pageCartItems, pageCartTotal, true);
    };

    const renderCheckoutSummary = () => {
      renderCartRows(checkoutItems, checkoutTotal, false);
    };

    const renderTrackingPage = () => {
      if (
        !(trackingLookup instanceof HTMLElement) ||
        !(trackingCount instanceof HTMLElement) ||
        !(trackingOrders instanceof HTMLElement)
      ) {
        return;
      }
      const trackingState = state.tracking && typeof state.tracking === "object" ? state.tracking : {};
      const lookup = normalizeText(trackingState.lookup);
      const count = Number(trackingState.count) || 0;
      const orders = Array.isArray(trackingState.orders) ? trackingState.orders : [];
      trackingLookup.textContent = lookup ? `Запрос: ${lookup}` : "";
      trackingCount.textContent = `Найдено заказов: ${count}`;
      if (!orders.length) {
        const empty = document.createElement("p");
        empty.className = "cart-modal-empty";
        empty.textContent = "Заказы не найдены";
        trackingOrders.replaceChildren(empty);
        return;
      }
      const nodes = orders.map((order, index) => {
        const card = document.createElement("article");
        card.className = "products-tracking-order";
        const title = document.createElement("p");
        title.className = "products-tracking-order-title";
        title.textContent =
          normalizeText(order.order_number) ||
          normalizeText(order.orderNumber) ||
          normalizeText(order.id) ||
          `Заказ #${index + 1}`;
        const status = document.createElement("p");
        status.className = "products-tracking-order-status";
        status.textContent = normalizeText(order.status) || "Статус не указан";
        const hint = document.createElement("p");
        hint.className = "products-tracking-order-hint";
        hint.textContent = normalizeText(order.status_hint) || "Детали статуса недоступны";
        card.append(title, status, hint);
        return card;
      });
      trackingOrders.replaceChildren(...nodes);
    };

    const toggleCartModal = (nextState) => {
      if (!cartModal) {
        return;
      }
      const shouldOpen = typeof nextState === "boolean" ? nextState : cartModal.hidden;
      cartModal.hidden = !shouldOpen;
      if (shouldOpen) {
        renderCartModal();
      }
    };

    const showInternalPage = (pageName) => {
      const normalized = normalizeText(pageName).toLowerCase();
      if (pageSearch instanceof HTMLElement) {
        pageSearch.hidden = normalized !== "search";
      }
      if (pageMyCart instanceof HTMLElement) {
        pageMyCart.hidden = normalized !== "my-cart";
      }
      if (pageCheckout instanceof HTMLElement) {
        pageCheckout.hidden = normalized !== "checkout";
      }
      if (pageTracking instanceof HTMLElement) {
        pageTracking.hidden = normalized !== "tracking";
      }
      if (normalized === "my-cart") {
        renderPageCart();
      }
      if (normalized === "checkout") {
        renderCheckoutSummary();
      }
      if (normalized === "tracking") {
        renderTrackingPage();
      }
    };

    const renderCartBadge = () => {
      const count = readLocalCartCount();
      if (!cartBadge) {
        return;
      }
      if (count <= 0) {
        cartBadge.hidden = true;
        cartBadge.textContent = "0";
        return;
      }
      cartBadge.hidden = false;
      cartBadge.textContent = String(count);
    };

    const updateCarouselControls = () => {
      if (!track || !leftArrow || !rightArrow) {
        return;
      }
      const canScroll = track.scrollWidth > track.clientWidth + 2;
      const maxScroll = Math.max(0, track.scrollWidth - track.clientWidth);
      leftArrow.disabled = !canScroll || track.scrollLeft <= 2;
      rightArrow.disabled = !canScroll || track.scrollLeft >= maxScroll - 2;
    };

    const renderProducts = () => {
      if (!track) {
        return;
      }

      if (state.isLoading || !state.loadedOnce) {
        track.innerHTML = `
          <article class="skeleton-card" aria-hidden="true">
            <div class="skeleton-block skeleton-image"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-meta"></div>
            <div class="skeleton-block skeleton-price"></div>
            <div class="skeleton-block skeleton-button"></div>
          </article>
          <article class="skeleton-card" aria-hidden="true">
            <div class="skeleton-block skeleton-image"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-meta"></div>
            <div class="skeleton-block skeleton-price"></div>
            <div class="skeleton-block skeleton-button"></div>
          </article>
          <article class="skeleton-card" aria-hidden="true">
            <div class="skeleton-block skeleton-image"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-title"></div>
            <div class="skeleton-block skeleton-meta"></div>
            <div class="skeleton-block skeleton-price"></div>
            <div class="skeleton-block skeleton-button"></div>
          </article>
        `;
        updateCarouselControls();
        return;
      }

      if (!state.products.length) {
        track.innerHTML =
          '<article class="product-card"><h3 class="product-title">Ничего не найдено</h3><p class="manufacturer">Попробуйте другой запрос</p></article>';
        updateCarouselControls();
        return;
      }

      track.innerHTML = state.products
        .map((product) => {
          const hasBasePrice = typeof product.price === "number" && product.price > 0;
          const hasDiscountPrice = typeof product.discountPrice === "number" && product.discountPrice > 0;
          const hasDiscount = hasBasePrice && hasDiscountPrice && product.discountPrice < product.price;
          const effectivePrice = hasDiscount ? product.discountPrice : hasBasePrice ? product.price : null;
          const discount = hasDiscount ? computeDiscount(product.price, product.discountPrice) : null;
          const discountBadge = discount ? `<span class="discount">-${discount}%</span>` : "";
          const oldPriceLine = hasDiscount ? `<p class="old-price">${toMoney(product.price)} ${discountBadge}</p>` : "";
          const inStock = typeof effectivePrice === "number";
          const priceLine = inStock
            ? `<p class="new-price">${toMoney(effectivePrice)}</p>`
            : '<p class="new-price is-unavailable">Нет в наличии</p>';
          const actionButton = inStock
            ? `<button class="add-to-cart-button" data-action="add-to-cart" data-product-id="${escapeHtml(product.id)}">В корзину</button>`
            : `<button class="add-to-cart-button add-to-cart-button--ghost" data-action="support-contact" data-product-id="${escapeHtml(product.id)}">Уточнить наличие</button>`;
          const safeImageUrl = escapeHtml(product.imageUrl);
          const safeName = escapeHtml(product.name);
          const safeManufacturer = escapeHtml(product.manufacturer);
          const safeFallbackImage = escapeHtml(getFallbackImage());
          const safeProductId = escapeHtml(product.id);

          return `
            <article class="product-card ${inStock ? "" : "is-unavailable"}" data-product-id="${safeProductId}">
              <img
                class="product-image"
                src="${safeImageUrl}"
                alt="${safeName}"
                loading="lazy"
                onerror="this.onerror=null;this.src='${safeFallbackImage}'"
              />
              <h3 class="product-title">${safeName}</h3>
              <div class="product-manufacturer-row">
                <p class="manufacturer">${safeManufacturer}</p>
              </div>
              <div class="product-price-row">${oldPriceLine}</div>
              ${priceLine}
              ${actionButton}
            </article>
          `;
        })
        .join("");

      const addButtons = track.querySelectorAll('[data-action="add-to-cart"]');
      for (const button of addButtons) {
        if (!(button instanceof HTMLElement)) {
          continue;
        }
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          ctx.actions.addToCart(normalizeText(button.dataset.productId));
        });
      }

      const supportButtons = track.querySelectorAll('[data-action="support-contact"]');
      for (const button of supportButtons) {
        if (!(button instanceof HTMLElement)) {
          continue;
        }
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (typeof ctx.actions.openSupportPopup === "function") {
            ctx.actions.openSupportPopup(button);
          }
        });
      }

      updateCarouselControls();
    };

    ctx.ui.renderCartModal = renderCartModal;
    ctx.ui.renderPageCart = renderPageCart;
    ctx.ui.renderCheckoutSummary = renderCheckoutSummary;
    ctx.ui.renderTrackingPage = renderTrackingPage;
    ctx.ui.toggleCartModal = toggleCartModal;
    ctx.ui.showInternalPage = showInternalPage;
    ctx.ui.renderCartBadge = renderCartBadge;
    ctx.ui.updateCarouselControls = updateCarouselControls;
    ctx.ui.renderProducts = renderProducts;
    ctx.ui.getCartSummary = () => getCartSummary(true);
  };

  window.ProductsRender = {
    attach,
  };
})();
