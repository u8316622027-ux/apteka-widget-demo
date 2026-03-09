(function () {
  const attach = (ctx) => {
    const { state, dom, utils, cart, sync } = ctx;
    const { track, leftArrow, rightArrow, cartBadge, cartModal, cartModalItems, cartModalTotal } = dom;
    const { normalizeText, escapeHtml, toMoney, computeDiscount, getFallbackImage, getPriceForCart } = utils;
    const { readLocalCartCount, readLocalCart, writeLocalCart, readCartItems } = cart;

    const renderCartModal = () => {
      if (!cartModalItems || !cartModalTotal) {
        return;
      }
      const cartPayload = readLocalCart();
      const cartItems = readCartItems();
      const rows = Object.entries(cartPayload)
        .map(([productId, rawQuantity]) => {
          const quantity = Number(rawQuantity);
          if (!Number.isFinite(quantity) || quantity <= 0) {
            return null;
          }
          const fromProductsState = state.products.find((entry) => entry.id === productId) || null;
          const item = (cartItems[productId] && typeof cartItems[productId] === "object" ? cartItems[productId] : fromProductsState) || {};
          const linePrice = getPriceForCart(item);
          return {
            productId,
            quantity,
            name: normalizeText(item.name) || `Товар #${productId}`,
            manufacturer: normalizeText(item.manufacturer) || "Производитель не указан",
            priceText: Number.isFinite(linePrice) && linePrice > 0 ? toMoney(linePrice) : "Цена уточняется",
            imageUrl: normalizeText(item.imageUrl) || getFallbackImage(),
            lineTotal: Number.isFinite(linePrice) ? linePrice * quantity : 0,
          };
        })
        .filter(Boolean);

      if (!rows.length) {
        const empty = document.createElement("p");
        empty.className = "cart-modal-empty";
        empty.textContent = "В корзине пока нет товаров";
        cartModalItems.replaceChildren(empty);
        cartModalTotal.textContent = "Итого: 0.00 MDL";
        return;
      }

      let total = 0;
      const rowNodes = rows.map((row) => {
        total += row.lineTotal;

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

        const name = document.createElement("p");
        name.className = "cart-modal-item-name";
        name.textContent = row.name;

        const manufacturer = document.createElement("p");
        manufacturer.className = "cart-modal-item-meta";
        manufacturer.textContent = row.manufacturer;

        const price = document.createElement("p");
        price.className = "cart-modal-item-price";
        price.textContent = row.priceText;

        content.append(name, manufacturer, price);

        const qty = document.createElement("div");
        qty.className = "cart-modal-qty";
        const decrease = document.createElement("button");
        decrease.className = "cart-modal-qty-button";
        decrease.dataset.action = "cart-decrease";
        decrease.textContent = "−";
        const value = document.createElement("span");
        value.className = "cart-modal-qty-value";
        value.textContent = String(row.quantity);
        const increase = document.createElement("button");
        increase.className = "cart-modal-qty-button";
        increase.dataset.action = "cart-increase";
        increase.textContent = "+";

        qty.append(decrease, value, increase);
        article.append(image, content, qty);
        return article;
      });

      cartModalItems.replaceChildren(...rowNodes);
      cartModalTotal.textContent = `Итого: ${toMoney(total)}`;
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
    ctx.ui.toggleCartModal = toggleCartModal;
    ctx.ui.renderCartBadge = renderCartBadge;
    ctx.ui.updateCarouselControls = updateCarouselControls;
    ctx.ui.renderProducts = renderProducts;
  };

  window.ProductsRender = {
    attach,
  };
})();
