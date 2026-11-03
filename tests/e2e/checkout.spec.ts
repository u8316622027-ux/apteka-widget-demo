import fs from "node:fs";
import path from "node:path";
import { type Page, expect, test } from "@playwright/test";

async function loadWidget(page: Page, failure = "") {
  const widget = path.resolve("app/widgets");
  const html = fs
    .readFileSync(path.join(widget, "products.html"), "utf8")
    .replace(
      /<link[^>]+href="\.\/([^\"]+)"[^>]*>/g,
      (_, file) =>
        `<style>${fs.readFileSync(path.join(widget, file), "utf8")}</style>`,
    )
    .replace(
      /<script src="\.\/([^\"]+)"><\/script>/g,
      (_, file) =>
        `<script>${fs.readFileSync(path.join(widget, file), "utf8")}</script>`,
    );
  await page.addInitScript(
    ({ failure }) => {
      const product = {
        id: "101",
        name: "Парацетамол",
        name_ru: "Парацетамол",
        name_ro: "Paracetamol",
        price: 40,
        manufacturer: "Farm",
        image_url: "",
      };
      let items: Record<string, unknown>[] = [];
      let cartCreated = false;
      let submissionAttempts = 0;
      const cart = () => ({
        cart_session_id: cartCreated ? "session-test" : "",
        items,
        count: items.reduce((n, i) => n + Number(i.quantity), 0),
        total: items.reduce((n, i) => n + 40 * Number(i.quantity), 0),
      });
      const slot = {
        deliveryDate: "03.11.2026",
        from: "13:00",
        to: "15:00",
        orderEnd: "05.11.2026",
        pharmacyClose: "20:00",
      };
      Object.assign(globalThis, {
        __calls: [],
        openai: {
          toolOutput: {
            products: [product],
            query: "Парацетамол",
            language: "ru",
          },
          setWidgetState: () => {},
          callTool: async (name: string, args: Record<string, unknown>) => {
            (globalThis as unknown as { __calls: unknown[] }).__calls.push({
              name,
              args,
            });
            const legacyNames = [
              "my_cart",
              "add_to_my_cart",
              "checkout_order",
              "sync_cart",
            ];
            if (legacyNames.includes(name))
              throw new Error(`Unexpected legacy tool ${name}`);
            if (
              (failure === "review_unavailable" && name === "review_order") ||
              (failure === "submit_unavailable" && name === "submit_order")
            )
              throw new Error(`Tool not found: ${name}`);
            if (name === "search_products")
              return {
                structuredContent: {
                  products: [product],
                  language: args.language,
                  query: args.query,
                },
              };
            if (
              ["add_to_cart", "update_cart_item", "add_to_my_cart"].includes(
                name,
              )
            ) {
              cartCreated = true;
              if (failure === "cart")
                return {
                  isError: true,
                  content: [{ type: "text", text: "Cart unavailable" }],
                };
              if (name === "update_cart_item")
                items =
                  Number(args.quantity) > 0
                    ? [
                        {
                          ...product,
                          product_id: args.product_id,
                          quantity: args.quantity,
                        },
                      ]
                    : [];
              else if (Array.isArray(args.items))
                items = args.items
                  .filter((i) => Number(i.quantity) > 0)
                  .map((i) => ({
                    ...product,
                    product_id: i.product_id,
                    quantity: i.quantity,
                  }));
              else
                items = [
                  {
                    ...product,
                    product_id: "101",
                    quantity: Number(items[0]?.quantity || 0) + 1,
                  },
                ];
              return { structuredContent: cart() };
            }
            if (["my_cart", "sync_cart", "check_cart"].includes(name))
              return { structuredContent: cart() };
            const checkoutAction =
              (
                {
                  get_checkout_options: "options",
                  get_delivery_windows: "delivery",
                  review_order: "review",
                  submit_order: "submit",
                } as Record<string, string>
              )[name] || (name === "checkout_order" ? args.action : "");
            if (checkoutAction) {
              if (checkoutAction === "submit") {
                submissionAttempts += 1;
                if (failure === "validation" && submissionAttempts === 1)
                  return {
                    isError: true,
                    structuredContent: {
                      error: {
                        type: "validation_error",
                        message:
                          "Заказ не принят (HTTP 422). Проверьте: способ оплаты.",
                      },
                    },
                  };
                if (failure === "submit")
                  return {
                    isError: true,
                    content: [{ type: "text", text: "Order status uncertain" }],
                  };
                return {
                  structuredContent: {
                    status: "order_submitted",
                    order_id: "123",
                    order_number: "AP-123",
                  },
                };
              }
              if (checkoutAction === "delivery")
                return {
                  structuredContent: {
                    status: "delivery_windows",
                    windows: [slot],
                  },
                };
              if (checkoutAction === "review") {
                if (failure === "review")
                  return {
                    isError: true,
                    content: [{ type: "text", text: "Review unavailable" }],
                  };
                const fee = args.delivery_method === "courier" ? 40 : 0;
                return {
                  structuredContent: {
                    status: "review",
                    confirmation_id: `review-${args.payment_method}`,
                    review: {
                      items,
                      subtotal: cart().total,
                      delivery_fee: fee,
                      total: cart().total + fee,
                      destination: "Farmacia, Street 1",
                      contact: args.contact,
                      delivery_method: args.delivery_method,
                      delivery_window: slot,
                      available_windows: [slot],
                      payment_method: args.payment_method,
                    },
                  },
                };
              }
              return {
                structuredContent: {
                  status: "delivery_method_selection",
                  cart: cart(),
                  regions: [
                    {
                      id: 2,
                      name: args.language === "ro" ? "Chișinău" : "Кишинёв",
                      delivery_cost: 40,
                    },
                  ],
                  cities: [
                    {
                      id: 24,
                      region_id: 2,
                      name: args.language === "ro" ? "Ciocana" : "Чеканы",
                    },
                  ],
                  pharmacies: [
                    {
                      id: 1,
                      region_id: 2,
                      city_id: 24,
                      name: "Farmacia",
                      address: "Street 1",
                      schedule: {},
                    },
                  ],
                },
              };
            }
            throw new Error(`Unexpected tool ${name}`);
          },
        },
      });
    },
    { failure },
  );
  await page.route("https://widget.test/", (route) =>
    route.fulfill({ contentType: "text/html", body: html }),
  );
  await page.goto("https://widget.test/");
  await expect(page.locator('[data-action="add-to-cart"]')).toBeVisible();
}

async function openCheckout(page: Page, method = "pickup") {
  await page.locator('[data-action="add-to-cart"]').click();
  await page.locator("#products-cart-button").click();
  await expect(page.getByRole("dialog", { name: "Корзина" })).toBeVisible();
  await page.locator("#products-cart-checkout").click();
  await expect(page.locator('[data-checkout-step="delivery"]')).toBeVisible();
  await page
    .locator(
      `#products-checkout-flow input[name="products-delivery-method"][value="${method}"]`,
    )
    .check();
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator('[data-checkout-step="address"]')).toBeVisible();
}

async function choose(page: Page, field: string, value: string) {
  await page.locator(`#products-checkout-flow-${field}-trigger`).click();
  await page
    .locator(
      `[data-select-option="products-checkout-flow-${field}"][data-select-value="${value}"]`,
    )
    .click();
}

async function fillContact(page: Page, courier = false) {
  await page.locator("#products-checkout-flow-name").fill("Ana Popescu");
  await page.locator("#products-checkout-flow-phone").fill("79802000");
  await choose(page, "region", "2");
  await choose(page, "sector", "24");
  if (courier) {
    await page.locator("#products-checkout-flow-street").fill("Dacia");
    await page.locator("#products-checkout-flow-building").fill("10");
  } else
    await page
      .locator('input[name="products-pharmacy-option"][value="1"]')
      .check();
  await expect(
    page.locator("#products-checkout-flow-delivery-windows"),
  ).toContainText("03.11.2026");
}

for (const width of [320, 768, 1280]) {
  test(`Kokiko cart modal and pickup flow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await loadWidget(page);
    await page.locator('[data-action="add-to-cart"]').click();
    await expect(page.locator("#products-cart-toast-region")).toContainText(
      "Добавлен в корзину",
    );
    await page.locator("#products-cart-button").click();
    await expect(page.locator("#products-cart-panel")).toHaveAttribute(
      "aria-modal",
      "true",
    );
    await page.locator('[data-action="cart-increase"]').click();
    await expect(page.locator("#products-cart-total")).toContainText("80.00");
    await page.screenshot({
      path: test.info().outputPath("cart.png"),
      fullPage: true,
    });
    await page.locator("#products-cart-checkout").click();
    await page.locator('#products-checkout-flow input[value="pickup"]').check();
    await page.locator('[data-checkout-action="next"]').click();
    await fillContact(page);
    await page.screenshot({
      path: test.info().outputPath("address.png"),
      fullPage: true,
    });
    await page.locator('[data-checkout-action="next"]').click();
    await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
    await expect(page.locator("#products-checkout-flow-review")).toContainText(
      "80.00",
    );
    await expect(page.locator("#products-checkout-flow-submit")).toHaveCSS(
      "background-color",
      "rgb(31, 85, 214)",
    );
    await page.screenshot({
      path: test.info().outputPath("review.png"),
      fullPage: true,
    });
    await page.locator("#products-checkout-flow-submit").click();
    await expect(
      page.locator("#products-checkout-flow-consent"),
    ).toHaveAttribute("aria-invalid", "true");
    await page.locator("#products-checkout-flow-consent").check();
    await page.locator("#products-checkout-flow-submit").click();
    await expect(page.locator('[data-checkout-step="success"]')).toBeVisible();
    await expect(
      page.locator("#products-checkout-flow-order-number"),
    ).toContainText("AP-123");
    await page.locator('[data-checkout-action="continue"]').click();
    await expect(page.locator("#products-cart-layer")).toBeHidden();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    const calls = await page.evaluate(
      () =>
        (
          globalThis as unknown as {
            __calls: { name: string; args: Record<string, unknown> }[];
          }
        ).__calls,
    );
    expect(calls.filter((call) => call.name === "submit_order")).toHaveLength(
      1,
    );
    expect(
      calls.every((call) =>
        [
          "check_cart",
          "add_to_cart",
          "update_cart_item",
          "get_checkout_options",
          "get_delivery_windows",
          "review_order",
          "submit_order",
          "search_products",
        ].includes(call.name),
      ),
    ).toBeTruthy();
  });
}

test("Kokiko modal closes by X, Escape and backdrop and returns focus", async ({
  page,
}) => {
  await loadWidget(page);
  for (const method of ["close", "escape", "backdrop"]) {
    await page.locator("#products-cart-button").click();
    if (method === "close") await page.locator("#products-cart-close").click();
    else if (method === "escape") await page.keyboard.press("Escape");
    else
      await page
        .locator("#products-cart-layer")
        .click({ position: { x: 1, y: 1 } });
    await expect(page.locator("#products-cart-layer")).toBeHidden();
    await expect(page.locator("#products-cart-button")).toBeFocused();
  }
});

test("courier validates address and payment changes update the confirmed order", async ({
  page,
}) => {
  await loadWidget(page);
  await openCheckout(page, "courier");
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator("#products-checkout-flow-name")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await fillContact(page, true);
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
  await expect(
    page.locator(".products-review-total-row--highlight"),
  ).toContainText("80.00");
  await page
    .locator('input[name="products-payment-method"][value="card"]')
    .check();
  await page.locator("#products-checkout-flow-consent").check();
  await page.locator("#products-checkout-flow-submit").click();
  await expect(page.locator('[data-checkout-step="success"]')).toBeVisible();
  const calls = await page.evaluate(
    () =>
      (
        globalThis as unknown as {
          __calls: { name: string; args: Record<string, unknown> }[];
        }
      ).__calls,
  );
  const reviews = calls.filter((call) => call.name === "review_order");
  expect(reviews.at(-1)?.args.payment_method).toBe("card_on_receipt");
  expect(reviews.at(-1)?.args.address).toEqual(
    expect.objectContaining({ street: "Dacia", house_number: "10" }),
  );
  expect(
    calls.find((call) => call.name === "submit_order")?.args.confirmation_id,
  ).toBe("review-card_on_receipt");
});

test("back buttons preserve fields and Escape closes the custom picker first", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await loadWidget(page);
  await openCheckout(page);
  await page.locator("#products-checkout-flow-region-trigger").click();
  const menu = await page
    .locator("#products-checkout-flow-region-menu")
    .boundingBox();
  const panel = await page.locator("#products-cart-panel").boundingBox();
  expect(
    menu &&
      panel &&
      menu.x >= panel.x &&
      menu.x + menu.width <= panel.x + panel.width + 1,
  ).toBeTruthy();
  await page.keyboard.press("Escape");
  await expect(page.locator("#products-cart-layer")).toBeVisible();
  await expect(
    page.locator("#products-checkout-flow-region-menu"),
  ).toBeHidden();
  await fillContact(page);
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
  await page.locator("#products-checkout-flow-back").click();
  await expect(page.locator("#products-checkout-flow-name")).toHaveValue(
    "Ana Popescu",
  );
  await page.locator("#products-checkout-flow-back").click();
  await expect(page.locator('[data-checkout-step="delivery"]')).toBeVisible();
  await page.locator("#products-checkout-flow-back").click();
  await expect(page.locator("#products-cart-items")).toBeVisible();
});

test("failed submission keeps the review and cart", async ({ page }) => {
  await loadWidget(page, "submit");
  await openCheckout(page);
  await fillContact(page);
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
  await page.locator("#products-checkout-flow-consent").check();
  await page.locator("#products-checkout-flow-submit").click();
  await expect(page.locator("#products-checkout-flow-status")).toContainText(
    "Order status uncertain",
  );
  await expect(page.locator('[data-checkout-step="success"]')).toBeHidden();
  await expect(page.locator("#products-cart-count")).toHaveText("1");
});

test("validation rejection keeps the cart and allows an explicit corrected submission", async ({
  page,
}) => {
  await loadWidget(page, "validation");
  await openCheckout(page);
  await fillContact(page);
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
  await page.locator("#products-checkout-flow-consent").check();
  await page.locator("#products-checkout-flow-submit").click();
  await expect(page.locator("#products-checkout-flow-status")).toContainText(
    "способ оплаты",
  );
  await expect(page.locator("#products-cart-count")).toHaveText("1");
  const count = await page.evaluate(
    () =>
      (
        globalThis as unknown as {
          __calls: { name: string; args: Record<string, unknown> }[];
        }
      ).__calls.filter((call) => call.name === "submit_order").length,
  );
  expect(count).toBe(1);
  await page
    .locator('input[name="products-payment-method"][value="card"]')
    .check();
  await page.locator("#products-checkout-flow-submit").click();
  await expect(page.locator('[data-checkout-step="success"]')).toBeVisible();
});

test("remove, decrease, theme, language and support buttons work", async ({
  page,
}) => {
  await loadWidget(page);
  await page.locator('[data-action="add-to-cart"]').click();
  await page.locator("#products-cart-button").click();
  await page.locator('[data-action="cart-decrease"]').click();
  await expect(page.locator(".products-cart-qty")).toHaveText("1");
  await page.locator('[data-action="cart-remove"]').click();
  await expect(page.locator("#products-cart-items")).toContainText(
    "Корзина пуста",
  );
  await expect(page.locator("#products-cart-checkout")).toBeDisabled();
  await page.locator("#products-cart-close").click();
  await page.locator("#products-theme-toggle").click();
  const theme = await page.locator("html").getAttribute("data-theme");
  await page.locator("#products-theme-toggle").click();
  expect(await page.locator("html").getAttribute("data-theme")).not.toBe(theme);
  await page.locator("#products-language-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ro");
  await page.locator("#products-support-button").click();
  await expect(page.locator("#products-support-popup")).toBeVisible();
  await expect(page.locator("#products-support-telegram")).toHaveAttribute(
    "href",
    "https://t.me/aptekamd_bot",
  );
  await page.locator("#products-support-close").click();
  await expect(page.locator("#products-support-layer")).toBeHidden();
});

test("failed cart mutation rolls back the optimistic item", async ({
  page,
}) => {
  await loadWidget(page, "cart");
  await page.locator('[data-action="add-to-cart"]').click();
  await page.locator("#products-cart-button").click();
  await expect(page.locator("#products-cart-status")).toContainText(
    "Cart unavailable",
  );
  await expect(page.locator("#products-cart-count")).toHaveText("0");
  await expect(page.locator("#products-cart-checkout")).toBeDisabled();
});

test("failed review stays on address and cannot send an order", async ({
  page,
}) => {
  await loadWidget(page, "review");
  await openCheckout(page);
  await fillContact(page);
  await page.locator('[data-checkout-action="next"]').click();
  await expect(page.locator("#products-checkout-flow-status")).toContainText(
    "Review unavailable",
  );
  await expect(page.locator('[data-checkout-step="address"]')).toBeVisible();
  await expect(page.locator("#products-checkout-flow-submit")).toBeHidden();
});

test("rapid additions share one server session and keep the final quantity", async ({
  page,
}) => {
  await loadWidget(page);
  await page.locator('[data-action="add-to-cart"]').click({ clickCount: 3 });
  await expect(page.locator("#products-cart-count")).toHaveText("3");
  await page.locator("#products-cart-button").click();
  await expect(page.locator("#products-cart-total")).toContainText("120.00");
  const calls = await page.evaluate(
    () =>
      (
        globalThis as unknown as {
          __calls: { name: string; args: Record<string, unknown> }[];
        }
      ).__calls,
  );
  expect(calls.filter((call) => call.name === "add_to_cart")).toHaveLength(3);
  const additions = calls.filter((call) => call.name === "add_to_cart");
  expect(additions[0].args.cart_session_id).toBeUndefined();
  expect(
    additions
      .slice(1)
      .every((call) => call.args.cart_session_id === "session-test"),
  ).toBeTruthy();
});

test("host tool results open the same Kokiko cart modal", async ({ page }) => {
  await loadWidget(page);
  await page.evaluate(() =>
    globalThis.dispatchEvent(
      new CustomEvent("openai:set_globals", {
        detail: {
          globals: {
            toolOutput: {
              cart_session_id: "session-host",
              count: 2,
              total: 80,
              items: [
                {
                  product_id: "101",
                  name: "Парацетамол",
                  price: 40,
                  quantity: 2,
                },
              ],
              widget: { open: { page: "cart" } },
            },
          },
        },
      }),
    ),
  );
  await expect(page.locator("#products-cart-layer")).toBeVisible();
  await expect(page.locator("#products-cart-total")).toContainText("80.00");
});

test("a chat review restores contact and delivery before confirmation", async ({
  page,
}) => {
  await loadWidget(page);
  await page.evaluate(() =>
    globalThis.dispatchEvent(
      new CustomEvent("openai:set_globals", {
        detail: {
          globals: {
            toolOutput: {
              status: "review",
              cart_session_id: "session-test",
              confirmation_id: "chat-review",
              widget: { open: { page: "checkout" } },
              review: {
                items: [
                  {
                    product_id: "101",
                    name: "Парацетамол",
                    price: 40,
                    quantity: 1,
                  },
                ],
                subtotal: 40,
                total: 40,
                delivery_fee: 0,
                destination: "Farmacia, Street 1",
                contact: {
                  first_name: "Ana",
                  last_name: "Popescu",
                  phone: "+37379802000",
                  email: "",
                },
                payment_method: "cash_on_receipt",
                delivery_method: "pickup",
                delivery_window: {
                  deliveryDate: "03.11.2026",
                  from: "13:00",
                  to: "15:00",
                },
                available_windows: [
                  { deliveryDate: "03.11.2026", from: "13:00", to: "15:00" },
                ],
                checkout_input: {
                  delivery_method: "pickup",
                  region_id: 2,
                  city_id: 24,
                  pharmacy_id: 1,
                  contact: {
                    first_name: "Ana",
                    last_name: "Popescu",
                    phone: "+37379802000",
                    email: "",
                  },
                  address: {},
                  payment_method: "cash_on_receipt",
                  comment: "",
                },
              },
            },
          },
        },
      }),
    ),
  );
  await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
  await expect(page.locator("#products-checkout-flow-review")).toContainText(
    "Ana Popescu",
  );
  await page.locator("#products-checkout-flow-back").click();
  await expect(page.locator("#products-checkout-flow-name")).toHaveValue(
    "Ana Popescu",
  );
  await expect(page.locator("#products-checkout-flow-region")).toHaveValue("2");
  await expect(page.locator("#products-checkout-flow-pharmacy")).toHaveValue(
    "1",
  );
});

test("chat can open checkout without supplying browser cart contents", async ({
  page,
}) => {
  await loadWidget(page);
  await page.locator('[data-action="add-to-cart"]').click();
  await expect(page.locator("#products-cart-count")).toHaveText("1");
  await page.evaluate(() =>
    globalThis.dispatchEvent(
      new CustomEvent("openai:set_globals", {
        detail: {
          globals: {
            toolOutput: {
              status: "ok",
              action: "open_checkout",
              cart_session_id: "session-test",
              checkout_step: "delivery",
              widget: { open: { page: "checkout" } },
            },
          },
        },
      }),
    ),
  );
  await expect(page.locator('[data-checkout-step="delivery"]')).toBeVisible();
  await page
    .locator(
      '#products-checkout-flow input[name="products-delivery-method"][value="pickup"]',
    )
    .check();
  await page.locator('[data-checkout-action="next"]').click();
  await fillContact(page);
});

test("chat preferences keep the visible products and cart", async ({
  page,
}) => {
  await loadWidget(page);
  await page.locator('[data-action="add-to-cart"]').click();
  await expect(page.locator("#products-cart-count")).toHaveText("1");
  for (const output of [
    { action: "set_widget_theme", theme: "dark", theme_mode: "manual" },
    { action: "set_widget_language", language: "ro" },
  ]) {
    await page.evaluate(
      (toolOutput) =>
        globalThis.dispatchEvent(
          new CustomEvent("openai:set_globals", {
            detail: { globals: { toolOutput } },
          }),
        ),
      output,
    );
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("lang", "ro");
  expect(
    await page.evaluate(() => localStorage.getItem("apteka_widget_language")),
  ).toBe("ro");
  await expect(page.locator('[data-action="add-to-cart"]')).toBeVisible();
  await expect(page.locator("#products-cart-count")).toHaveText("1");
});

test("initial cart loading only reads and never creates an empty backend cart", async ({
  page,
}) => {
  await loadWidget(page);
  await expect
    .poll(() =>
      page.evaluate(() =>
        (globalThis as unknown as { __calls: { name: string }[] }).__calls.map(
          (call) => call.name,
        ),
      ),
    )
    .toContain("check_cart");
  const calls = await page.evaluate(
    () => (globalThis as unknown as { __calls: { name: string }[] }).__calls,
  );
  expect(calls.every((call) => call.name === "check_cart")).toBeTruthy();
  await expect(page.locator("#products-cart-count")).toHaveText("0");
});

for (const operation of ["review", "submit"]) {
  test(`unavailable ${operation} never falls back to an obsolete checkout tool`, async ({
    page,
  }) => {
    await loadWidget(page, `${operation}_unavailable`);
    await openCheckout(page);
    await fillContact(page);
    await page.locator('[data-checkout-action="next"]').click();
    if (operation === "submit") {
      await expect(page.locator('[data-checkout-step="review"]')).toBeVisible();
      await page.locator("#products-checkout-flow-consent").check();
      await page.locator("#products-checkout-flow-submit").click();
    }
    await expect(page.locator("#products-checkout-flow-status")).toContainText(
      `Tool not found: ${operation}_order`,
    );
    await expect(page.locator('[data-checkout-step="success"]')).toBeHidden();
    await expect(page.locator("#products-cart-count")).toHaveText("1");
    const calls = await page.evaluate(
      () => (globalThis as unknown as { __calls: { name: string }[] }).__calls,
    );
    expect(
      calls.filter((call) => call.name === `${operation}_order`),
    ).toHaveLength(1);
    expect(
      calls.some((call) =>
        ["my_cart", "add_to_my_cart", "checkout_order", "sync_cart"].includes(
          call.name,
        ),
      ),
    ).toBeFalsy();
  });
}
