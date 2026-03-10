(function () {
  const attach = (ctx) => {
    const { dom, state, utils } = ctx;
    const { items, total } = dom;
    const { toMoney } = utils;

    const buildCard = (row) => {
      const article = document.createElement("article");
      article.className = "my-cart-card";
      article.dataset.productId = row.productId;

      const image = document.createElement("img");
      image.className = "my-cart-image";
      image.src = row.imageUrl;
      image.alt = row.name;
      image.loading = "lazy";

      const content = document.createElement("div");
      content.className = "my-cart-content";

      const name = document.createElement("p");
      name.className = "my-cart-name";
      name.textContent = row.name;

      const meta = document.createElement("p");
      meta.className = "my-cart-meta";
      meta.textContent = row.manufacturer;

      const price = document.createElement("p");
      price.className = "my-cart-price";
      price.textContent = row.priceText;

      const lineTotal = document.createElement("p");
      lineTotal.className = "my-cart-line-total";
      lineTotal.textContent = row.lineTotalText;

      content.append(name, meta, price, lineTotal);

      const controls = document.createElement("div");
      controls.className = "my-cart-controls";

      const decrease = document.createElement("button");
      decrease.className = "my-cart-control";
      decrease.type = "button";
      decrease.dataset.action = "decrease";
      decrease.setAttribute("aria-label", `Уменьшить количество ${row.name}`);
      decrease.textContent = "−";

      const qty = document.createElement("span");
      qty.className = "my-cart-qty";
      qty.textContent = String(row.quantity);

      const increase = document.createElement("button");
      increase.className = "my-cart-control";
      increase.type = "button";
      increase.dataset.action = "increase";
      increase.setAttribute("aria-label", `Увеличить количество ${row.name}`);
      increase.textContent = "+";

      const remove = document.createElement("button");
      remove.className = "my-cart-remove";
      remove.type = "button";
      remove.dataset.action = "remove";
      remove.setAttribute("aria-label", `Удалить ${row.name} из корзины`);
      remove.textContent = "×";

      controls.append(decrease, qty, increase);
      article.append(image, content, controls, remove);
      return article;
    };

    const render = () => {
      if (!(items instanceof HTMLElement) || !(total instanceof HTMLElement)) {
        return;
      }
      if (!state.rows.length) {
        const empty = document.createElement("p");
        empty.className = "my-cart-empty";
        empty.textContent = "В корзине пока нет товаров";
        items.replaceChildren(empty);
        total.textContent = "Итого: 0.00 MDL";
        return;
      }
      items.replaceChildren(...state.rows.map(buildCard));
      total.textContent = `Итого: ${toMoney(state.total)}`;
    };

    ctx.ui = {
      render,
    };
  };

  window.MyCartRender = {
    attach,
  };
})();
