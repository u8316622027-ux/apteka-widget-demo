(function () {
  const createContext = (root) => {
    const LOCAL_CART_KEY = "apteka_widget_cart";
    const CART_ITEMS_KEY = "apteka_widget_cart_items";
    const LOCAL_CART_SESSION_ID_KEY = "apteka_widget_cart_session_id";
    const LAST_SEARCH_QUERY_KEY = "apteka_widget_last_query";
    const FALLBACK_IMAGE_PATH = "/assets/images/placeholder-600x600.png";
    const memoryStorage = Object.create(null);

    const state = {
      rows: [],
      total: 0,
      count: 0,
    };

    const dom = {
      items: document.getElementById("my-cart-items"),
      total: document.getElementById("my-cart-total"),
      backButton: document.getElementById("my-cart-back-button"),
      checkoutButton: document.getElementById("my-cart-checkout-button"),
    };

    const normalizeText = (value) => String(value || "").trim();

    const readStorageValue = (key) => {
      try {
        return window.localStorage.getItem(key);
      } catch (_error) {
        return Object.prototype.hasOwnProperty.call(memoryStorage, key)
          ? String(memoryStorage[key])
          : null;
      }
    };

    const writeStorageValue = (key, value) => {
      const normalizedValue = String(value);
      try {
        window.localStorage.setItem(key, normalizedValue);
        return;
      } catch (_error) {
        memoryStorage[key] = normalizedValue;
      }
    };

    const readJsonObject = (key) => {
      try {
        const parsed = JSON.parse(readStorageValue(key) || "{}");
        return parsed && typeof parsed === "object" ? parsed : {};
      } catch (_error) {
        return {};
      }
    };

    const writeJsonObject = (key, value) => {
      writeStorageValue(key, JSON.stringify(value));
    };

    const toMoney = (value) => {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "0.00 MDL";
      }
      return `${value.toFixed(2)} MDL`;
    };

    const getFallbackImage = () => FALLBACK_IMAGE_PATH;

    const readLocalCart = () => readJsonObject(LOCAL_CART_KEY);
    const writeLocalCart = (value) => writeJsonObject(LOCAL_CART_KEY, value);
    const readCartItems = () => readJsonObject(CART_ITEMS_KEY);
    const writeCartItems = (value) => writeJsonObject(CART_ITEMS_KEY, value);

    const readStoredCartSessionId = () => normalizeText(readStorageValue(LOCAL_CART_SESSION_ID_KEY));
    const writeStoredCartSessionId = (value) => {
      writeStorageValue(LOCAL_CART_SESSION_ID_KEY, normalizeText(value));
    };

    const readLastSearchQuery = () => normalizeText(readStorageValue(LAST_SEARCH_QUERY_KEY));

    const normalizeCartQuantity = (value) => {
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        return 0;
      }
      return Math.floor(parsed);
    };

    const getPriceForCart = (item) => {
      const price = Number(item?.price);
      const discountPrice = Number(item?.discountPrice);
      if (Number.isFinite(discountPrice) && discountPrice > 0) {
        return discountPrice;
      }
      if (Number.isFinite(price) && price > 0) {
        return price;
      }
      return 0;
    };

    const buildRows = () => {
      const localCart = readLocalCart();
      const cartItems = readCartItems();
      const rows = Object.entries(localCart)
        .map(([productId, rawQuantity]) => {
          const quantity = normalizeCartQuantity(rawQuantity);
          if (!productId || quantity <= 0) {
            return null;
          }
          const meta =
            cartItems[productId] && typeof cartItems[productId] === "object"
              ? cartItems[productId]
              : {};
          const linePrice = getPriceForCart(meta);
          if (linePrice <= 0) {
            return null;
          }
          return {
            productId,
            quantity,
            name: normalizeText(meta.name) || `Товар #${productId}`,
            manufacturer: normalizeText(meta.manufacturer) || "Производитель не указан",
            priceText: toMoney(linePrice),
            lineTotalText: `Итого: ${toMoney(linePrice * quantity)}`,
            imageUrl: normalizeText(meta.imageUrl) || getFallbackImage(),
            lineTotal: linePrice * quantity,
          };
        })
        .filter(Boolean);

      state.rows = rows;
      state.total = rows.reduce((sum, row) => sum + row.lineTotal, 0);
      state.count = rows.reduce((sum, row) => sum + row.quantity, 0);
      return state;
    };

    const applyCartSnapshot = (snapshot) => {
      if (!snapshot || typeof snapshot !== "object") {
        return false;
      }

      const nextSessionId = normalizeText(snapshot.cart_session_id || snapshot.cartSessionId);
      if (nextSessionId) {
        writeStoredCartSessionId(nextSessionId);
      }

      const sourceItems = Array.isArray(snapshot.items) ? snapshot.items : [];
      const nextCart = {};
      const nextCartItems = {};

      for (const rawItem of sourceItems) {
        if (!rawItem || typeof rawItem !== "object") {
          continue;
        }
        const productId =
          normalizeText(rawItem.product_id) ||
          normalizeText(rawItem.productId) ||
          normalizeText(rawItem.id);
        const quantity = normalizeCartQuantity(rawItem.quantity);
        const price = Number(rawItem.price);
        const discountPrice = Number(rawItem.discount_price ?? rawItem.discountPrice);
        const normalizedPrice = Number.isFinite(price) ? price : undefined;
        const normalizedDiscountPrice = Number.isFinite(discountPrice) ? discountPrice : undefined;
        const effectivePrice =
          typeof normalizedDiscountPrice === "number" && normalizedDiscountPrice > 0
            ? normalizedDiscountPrice
            : typeof normalizedPrice === "number" && normalizedPrice > 0
              ? normalizedPrice
              : 0;
        if (!productId || quantity <= 0 || effectivePrice <= 0) {
          continue;
        }
        nextCart[productId] = quantity;
        nextCartItems[productId] = {
          id: productId,
          name: normalizeText(rawItem.name) || `Товар #${productId}`,
          manufacturer: normalizeText(rawItem.manufacturer) || "Производитель не указан",
          price: normalizedPrice,
          discountPrice: normalizedDiscountPrice,
          imageUrl: normalizeText(rawItem.image_url || rawItem.imageUrl) || getFallbackImage(),
        };
      }

      writeLocalCart(nextCart);
      writeCartItems(nextCartItems);
      buildRows();
      return true;
    };

    const isCartSnapshotCandidate = (candidate) => {
      if (!candidate || typeof candidate !== "object") {
        return false;
      }
      return (
        Array.isArray(candidate.items) ||
        Array.isArray(candidate.cart?.items) ||
        Boolean(normalizeText(candidate.cart_session_id || candidate.cartSessionId))
      );
    };

    const syncLocalCartFromToolPayload = (payload) => {
      const candidates = [
        payload,
        payload?.structuredContent,
        payload?.result,
        payload?.result?.structuredContent,
        payload?.data,
      ];
      for (const candidate of candidates) {
        if (!isCartSnapshotCandidate(candidate)) {
          continue;
        }
        const snapshot = {
          cart_session_id:
            candidate.cart_session_id ||
            candidate.cartSessionId ||
            candidate.cart?.cart_session_id ||
            candidate.cart?.cartSessionId,
          items: Array.isArray(candidate.items)
            ? candidate.items
            : Array.isArray(candidate.cart?.items)
              ? candidate.cart.items
              : [],
        };
        if (applyCartSnapshot(snapshot)) {
          return true;
        }
      }
      return false;
    };

    buildRows();

    return {
      root,
      state,
      dom,
      utils: {
        normalizeText,
        toMoney,
      },
      cart: {
        readLocalCart,
        writeLocalCart,
        readCartItems,
        writeCartItems,
        readStoredCartSessionId,
        writeStoredCartSessionId,
        readLastSearchQuery,
        buildRows,
        applyCartSnapshot,
        syncLocalCartFromToolPayload,
        normalizeCartQuantity,
      },
    };
  };

  window.MyCartState = {
    createContext,
  };
})();
