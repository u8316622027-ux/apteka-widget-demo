(function () {
  const createContext = (root) => {
    const INITIAL_PAYLOAD_WAIT_MS = 5000;
    const INITIAL_PAYLOAD_POLL_MS = 140;
    const LOCAL_CART_KEY = "apteka_widget_cart";
    const CART_ITEMS_KEY = "apteka_widget_cart_items";
    const LOCAL_CART_SESSION_ID_KEY = "apteka_widget_cart_session_id";
    const FALLBACK_IMAGE_PATH = "/assets/images/placeholder-600x600.png";
    const memoryStorage = Object.create(null);

    const state = {
      loadedOnce: false,
      isSearching: false,
      isLoading: true,
      products: [],
      lastQuery: "",
      apiBaseUrl: "",
      cartSyncQueue: Promise.resolve(),
      cartBootstrapCompleted: false,
    };

    const input = document.getElementById("products-search-input");
    const searchButton = document.getElementById("products-search-button");
    const track = document.getElementById("product-track");
    const leftArrow = document.getElementById("products-arrow-left");
    const rightArrow = document.getElementById("products-arrow-right");
    const cartBadge = document.getElementById("products-cart-badge");
    const loadingOverlay = document.getElementById("products-loading-overlay");
    const cartButton = document.getElementById("products-cart-button");
    const cartModal = document.getElementById("products-cart-modal");
    const cartModalClose = document.getElementById("products-cart-close");
    const cartModalItems = document.getElementById("products-cart-items");
    const cartModalTotal = document.getElementById("products-cart-total");
    const supportButton = document.getElementById("products-support-button");
    const supportLayer = document.getElementById("products-support-layer");
    const supportPopup = document.getElementById("products-support-popup");

    const normalizeText = (value) => String(value || "").trim();
    const escapeHtml = (value) =>
      String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    const debugLog = () => {};
    const readStorageValue = (key) => {
      try {
        return window.localStorage.getItem(key);
      } catch (_error) {
        debugLog("storage_read_fallback", { key });
        return Object.prototype.hasOwnProperty.call(memoryStorage, key) ? String(memoryStorage[key]) : null;
      }
    };
    const writeStorageValue = (key, value) => {
      const normalizedValue = String(value);
      try {
        window.localStorage.setItem(key, normalizedValue);
        return;
      } catch (_error) {
        memoryStorage[key] = normalizedValue;
        debugLog("storage_write_fallback", { key });
      }
    };
    const toMoney = (value) => {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "";
      }
      return `${value.toFixed(2)} MDL`;
    };

    const computeDiscount = (price, discountPrice) => {
      if (
        typeof price !== "number" ||
        typeof discountPrice !== "number" ||
        Number.isNaN(price) ||
        Number.isNaN(discountPrice) ||
        price <= 0 ||
        discountPrice >= price
      ) {
        return null;
      }
      return Math.max(1, Math.round(((price - discountPrice) / price) * 100));
    };

    const resolveImageUrl = (rawUrl) => {
      const imageUrl = normalizeText(rawUrl);
      if (!imageUrl) {
        return "";
      }
      if (imageUrl.startsWith("data:")) {
        return imageUrl;
      }
      if (/^https?:\/\//i.test(imageUrl)) {
        return imageUrl;
      }
      const baseUrl = normalizeText(state.apiBaseUrl);
      if (!baseUrl) {
        return imageUrl;
      }
      try {
        return new URL(imageUrl, baseUrl).href;
      } catch (_error) {
        return imageUrl;
      }
    };

    const getFallbackImage = () => {
      const baseUrl = normalizeText(state.apiBaseUrl);
      if (!baseUrl) {
        return FALLBACK_IMAGE_PATH;
      }
      try {
        return new URL(FALLBACK_IMAGE_PATH, baseUrl).href;
      } catch (_error) {
        return FALLBACK_IMAGE_PATH;
      }
    };

    const setLoading = (nextValue) => {
      state.isLoading = Boolean(nextValue);
      if (state.isLoading) {
        root.classList.add("is-loading");
        return;
      }
      root.classList.remove("is-loading");
      if (loadingOverlay) {
        loadingOverlay.setAttribute("aria-hidden", "true");
      }
    };

    const extractItems = (payload) => {
      if (Array.isArray(payload?.items)) {
        return payload.items.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload?.results)) {
        return payload.results.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload?.products)) {
        return payload.products.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload?.data?.items)) {
        return payload.data.items.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload?.data?.results)) {
        return payload.data.results.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload?.data?.products)) {
        return payload.data.products.filter((item) => item && typeof item === "object");
      }
      if (Array.isArray(payload)) {
        return payload.filter((item) => item && typeof item === "object");
      }
      return [];
    };

    const mapProduct = (item) => {
      const translations = typeof item.translations === "object" && item.translations ? item.translations : {};
      const ro = typeof translations.ro === "object" && translations.ro ? translations.ro : {};
      const ru = typeof translations.ru === "object" && translations.ru ? translations.ru : {};
      const name =
        normalizeText(item.name_ru) ||
        normalizeText(item.name_ro) ||
        normalizeText(ro.name) ||
        normalizeText(ru.name) ||
        normalizeText(item.name) ||
        "Товар";
      const manufacturer = normalizeText(item.manufacturer) || "Производитель не указан";

      const priceRaw = item.price;
      const discountRaw = item.discountPrice ?? item.discount_price;
      const price = Number(priceRaw);
      const discountPrice = Number(discountRaw);

      let imageUrl =
        resolveImageUrl(item.image) ||
        resolveImageUrl(item.image_url) ||
        resolveImageUrl(item.imageUrl) ||
        resolveImageUrl(item.picture) ||
        resolveImageUrl(item.photo) ||
        resolveImageUrl(item.thumbnail);

      const extractFromObjects = (value) => {
        if (Array.isArray(value)) {
          for (const row of value) {
            if (typeof row === "string") {
              const fromString = resolveImageUrl(row);
              if (fromString) {
                return fromString;
              }
              continue;
            }
            if (!row || typeof row !== "object") {
              continue;
            }
            const fromObject =
              resolveImageUrl(row.full) ||
              resolveImageUrl(row.preview) ||
              resolveImageUrl(row.url) ||
              resolveImageUrl(row.image) ||
              resolveImageUrl(row.src) ||
              resolveImageUrl(row.path);
            if (fromObject) {
              return fromObject;
            }
          }
        }
        if (value && typeof value === "object") {
          return (
            resolveImageUrl(value.full) ||
            resolveImageUrl(value.preview) ||
            resolveImageUrl(value.url) ||
            resolveImageUrl(value.image) ||
            resolveImageUrl(value.src) ||
            resolveImageUrl(value.path)
          );
        }
        return "";
      };

      if (!imageUrl && typeof item.meta === "object" && item.meta) {
        imageUrl =
          resolveImageUrl(item.meta.image) ||
          resolveImageUrl(item.meta.image_url) ||
          resolveImageUrl(item.meta.thumbnail) ||
          extractFromObjects(item.meta.images);
      }
      if (!imageUrl) {
        imageUrl =
          extractFromObjects(item.images) ||
          extractFromObjects(item.gallery) ||
          extractFromObjects(item.photos) ||
          extractFromObjects(item.media);
      }
      if (!imageUrl) {
        imageUrl = getFallbackImage();
      }

      return {
        id:
          normalizeText(item.id) ||
          normalizeText(item.product_id) ||
          normalizeText(item.productId) ||
          normalizeText(item.item_id) ||
          normalizeText(item.sku),
        name,
        manufacturer,
        price: Number.isNaN(price) ? null : price,
        discountPrice: Number.isNaN(discountPrice) ? null : discountPrice,
        imageUrl,
      };
    };

    const readLocalCartCount = () => {
      try {
        const payload = JSON.parse(readStorageValue(LOCAL_CART_KEY) || "{}");
        if (!payload || typeof payload !== "object") {
          return 0;
        }
        return Object.values(payload).reduce((sum, qty) => {
          const parsed = Number(qty);
          return sum + (Number.isFinite(parsed) && parsed > 0 ? parsed : 0);
        }, 0);
      } catch (_error) {
        return 0;
      }
    };

    const writeLocalCartAdd = (productId) => {
      if (!productId) {
        return;
      }
      try {
        const payload = JSON.parse(readStorageValue(LOCAL_CART_KEY) || "{}");
        const next = payload && typeof payload === "object" ? payload : {};
        const prev = Number(next[productId]);
        next[productId] = Number.isFinite(prev) && prev > 0 ? prev + 1 : 1;
        writeStorageValue(LOCAL_CART_KEY, JSON.stringify(next));
      } catch (_error) {
        return;
      }
    };

    const readLocalCart = () => {
      try {
        const payload = JSON.parse(readStorageValue(LOCAL_CART_KEY) || "{}");
        return payload && typeof payload === "object" ? payload : {};
      } catch (_error) {
        return {};
      }
    };

    const writeLocalCart = (next) => {
      writeStorageValue(LOCAL_CART_KEY, JSON.stringify(next));
    };

    const readCartItems = () => {
      try {
        const payload = JSON.parse(readStorageValue(CART_ITEMS_KEY) || "{}");
        return payload && typeof payload === "object" ? payload : {};
      } catch (_error) {
        return {};
      }
    };

    const writeCartItems = (next) => {
      writeStorageValue(CART_ITEMS_KEY, JSON.stringify(next));
    };

    const readStoredCartSessionId = () => normalizeText(readStorageValue(LOCAL_CART_SESSION_ID_KEY));

    const writeStoredCartSessionId = (sessionId) => {
      writeStorageValue(LOCAL_CART_SESSION_ID_KEY, normalizeText(sessionId));
    };

    const clearLocalCartState = () => {
      writeLocalCart({});
      writeCartItems({});
    };

    const ensureLocalCartBootstrap = () => {
      const localCart = readLocalCart();
      const localItems = readCartItems();
      writeLocalCart(localCart);
      writeCartItems(localItems);
    };

    const persistCartSessionFromToolPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return false;
      }
      const candidates = [
        payload,
        payload.structuredContent,
        payload.result,
        payload.result?.structuredContent,
        payload.data,
        payload.payload,
      ];
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object") {
          continue;
        }
        const nextSessionId = normalizeText(
          candidate.cart_session_id ||
            candidate.cartSessionId ||
            candidate.cart?.cart_session_id ||
            candidate.cart?.cartSessionId,
        );
        if (!nextSessionId) {
          continue;
        }
        writeStoredCartSessionId(nextSessionId);
        return true;
      }
      return false;
    };

    const enqueueCartSync = (requestFactory) => {
      const run = async () => {
        try {
          const result = await requestFactory();
          persistCartSessionFromToolPayload(result);
          return result;
        } catch (error) {
          throw error;
        }
      };
      state.cartSyncQueue = state.cartSyncQueue.catch(() => null).then(run);
      return state.cartSyncQueue;
    };

    const rememberCartItem = (productId) => {
      if (!productId) {
        return;
      }
      const product = state.products.find((item) => item.id === productId);
      if (!product) {
        return;
      }
      const payload = readCartItems();
      payload[productId] = {
        id: product.id,
        name: product.name,
        manufacturer: product.manufacturer,
        price: product.price,
        discountPrice: product.discountPrice,
        imageUrl: product.imageUrl || getFallbackImage(),
      };
      writeCartItems(payload);
    };

    const getPriceForCart = (item) => {
      const price = Number(item?.price);
      const discountPrice = Number(item?.discountPrice);
      if (Number.isFinite(discountPrice)) {
        return discountPrice;
      }
      if (Number.isFinite(price)) {
        return price;
      }
      return 0;
    };

    const normalizeCartQuantity = (value) => {
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        return 0;
      }
      return Math.floor(parsed);
    };

    const applyCartSnapshot = (snapshot) => {
      if (!snapshot || typeof snapshot !== "object") {
        return false;
      }

      const nextSessionId = normalizeText(snapshot.cart_session_id || snapshot.cartSessionId);
      const storedSessionId = readStoredCartSessionId();
      if (nextSessionId && storedSessionId && storedSessionId !== nextSessionId) {
        clearLocalCartState();
      }
      if (nextSessionId) {
        writeStoredCartSessionId(nextSessionId);
      }

      const sourceItems = Array.isArray(snapshot.items) ? snapshot.items : [];
      if (!sourceItems.length) {
        writeLocalCart({});
        writeCartItems({});
        ctx.ui.renderCartBadge();
        if (cartModal && !cartModal.hidden) {
          ctx.ui.renderCartModal();
        }
        return true;
      }

      const localCart = {};
      const localItems = {};

      for (const rawItem of sourceItems) {
        if (!rawItem || typeof rawItem !== "object") {
          continue;
        }
        const productId =
          normalizeText(rawItem.product_id) ||
          normalizeText(rawItem.productId) ||
          normalizeText(rawItem.id) ||
          normalizeText(rawItem.item_id);
        if (!productId) {
          continue;
        }
        const qty = normalizeCartQuantity(rawItem.quantity);
        if (qty <= 0) {
          continue;
        }
        localCart[productId] = qty;
        const mappedItem = mapProduct(rawItem);
        localItems[productId] = {
          id: productId,
          name: normalizeText(rawItem.name) || mappedItem.name,
          manufacturer: normalizeText(rawItem.manufacturer) || mappedItem.manufacturer,
          price: typeof rawItem.price === "number" ? rawItem.price : mappedItem.price,
          discountPrice:
            typeof rawItem.discount_price === "number"
              ? rawItem.discount_price
              : typeof rawItem.discountPrice === "number"
                ? rawItem.discountPrice
                : mappedItem.discountPrice,
          imageUrl: mappedItem.imageUrl || getFallbackImage(),
        };
      }

      writeLocalCart(localCart);
      writeCartItems(localItems);
      ctx.ui.renderCartBadge();
      if (cartModal && !cartModal.hidden) {
        ctx.ui.renderCartModal();
      }
      return true;
    };

    const hasCartItemStructure = (items) => {
      if (!Array.isArray(items)) {
        return false;
      }
      if (!items.length) {
        return true;
      }
      return items.some((item) => {
        if (!item || typeof item !== "object") {
          return false;
        }
        return Boolean(
          normalizeText(item.product_id) ||
            normalizeText(item.productId) ||
            normalizeText(item.id) ||
            normalizeText(item.item_id),
        );
      });
    };

    const isCartSnapshotCandidate = (candidate) => {
      if (!candidate || typeof candidate !== "object") {
        return false;
      }
      const hasCartKeys =
        Boolean(normalizeText(candidate.cart_session_id || candidate.cartSessionId)) ||
        Object.prototype.hasOwnProperty.call(candidate, "cart_created") ||
        Object.prototype.hasOwnProperty.call(candidate, "cartCreated") ||
        Array.isArray(candidate.items) ||
        Array.isArray(candidate.cart?.items);
      if (!hasCartKeys) {
        return false;
      }
      return hasCartItemStructure(candidate.items) || hasCartItemStructure(candidate.cart?.items);
    };

    const syncLocalCartFromToolPayload = (payload) => {
      if (!payload || typeof payload !== "object") {
        return false;
      }
      const candidates = [
        payload,
        payload.structuredContent,
        payload.result,
        payload.result?.structuredContent,
        payload.data,
        payload.payload,
      ];
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object") {
          continue;
        }
        if (!isCartSnapshotCandidate(candidate)) {
          continue;
        }
        const merged = {
          cart_session_id:
            candidate.cart_session_id || candidate.cartSessionId || candidate.cart?.cart_session_id || candidate.cart?.cartSessionId,
          items: Array.isArray(candidate.items)
            ? candidate.items
            : Array.isArray(candidate.cart?.items)
              ? candidate.cart.items
              : [],
          cart_created: candidate.cart_created ?? candidate.cartCreated,
        };
        if (applyCartSnapshot(merged)) {
          return true;
        }
      }
      return false;
    };

    const ctx = {
      root,
      state,
      constants: {
        INITIAL_PAYLOAD_WAIT_MS,
        INITIAL_PAYLOAD_POLL_MS,
      },
      dom: {
        input,
        searchButton,
        track,
        leftArrow,
        rightArrow,
        cartBadge,
        loadingOverlay,
        cartButton,
        cartModal,
        cartModalClose,
        cartModalItems,
        cartModalTotal,
        supportButton,
        supportLayer,
        supportPopup,
      },
      ui: {
        renderProducts: () => {},
        renderCartModal: () => {},
        renderCartBadge: () => {},
        toggleCartModal: (_nextState) => {},
        updateCarouselControls: () => {},
        toggleSupportPopup: (_nextState) => {},
      },
      actions: {
        addToCart: (_productId) => {},
        searchProducts: (_query) => Promise.resolve(),
        callSetCartItemQuantity: () => Promise.resolve(),
        openSupportPopup: () => {},
      },
      utils: {
        normalizeText,
        escapeHtml,
        debugLog,
        toMoney,
        computeDiscount,
        resolveImageUrl,
        getFallbackImage,
        setLoading,
        extractItems,
        mapProduct,
        getPriceForCart,
        normalizeCartQuantity,
      },
      cart: {
        readLocalCartCount,
        writeLocalCartAdd,
        readLocalCart,
        writeLocalCart,
        readCartItems,
        writeCartItems,
        readStoredCartSessionId,
        writeStoredCartSessionId,
        clearLocalCartState,
        ensureLocalCartBootstrap,
        rememberCartItem,
        applyCartSnapshot,
        hasCartItemStructure,
        isCartSnapshotCandidate,
        syncLocalCartFromToolPayload,
      },
      sync: {
        enqueueCartSync,
        persistCartSessionFromToolPayload,
      },
      toast: {
        enqueue: (_payload) => {},
      },
    };

    return ctx;
  };

  window.ProductsState = {
    createContext,
  };
})();
