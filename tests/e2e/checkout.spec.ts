import fs from "node:fs";
import path from "node:path";
import { type Page, expect, test } from "@playwright/test";

async function loadWidget(page: Page, failSubmit = false) {
  const widget = path.resolve("app/widgets");
  const html = fs
    .readFileSync(path.join(widget, "products.html"), "utf8")
    .replace(
      /<link[^>]+href="\.\/([^\"]+)"[^>]*>/g,
      (_, relative) =>
        `<style>${fs.readFileSync(path.join(widget, relative), "utf8")}</style>`,
    )
    .replace(
      /<script src="\.\/([^\"]+)"><\/script>/g,
      (_, relative) =>
        `<script>${fs.readFileSync(path.join(widget, relative), "utf8")}</script>`,
    );
  await page.addInitScript(
    ({ failSubmit }) => {
      const product = {
        id: "101",
        name: "Парацетамол",
        price: 40,
        manufacturer: "Farm",
        image_url: "",
      };
      let items: Record<string, unknown>[] = [];
      const cart = () => ({
        cart_session_id: "session-test",
        items,
        count: items.reduce((n, i) => n + Number(i.quantity), 0),
        total: items.reduce((n, i) => n + 40 * Number(i.quantity), 0),
      });
      Object.assign(window, {
        __calls: [],
        openai: {
          toolOutput: {
            products: [product],
            query: "Парацетамол",
            language: "ru",
          },
          callTool: async (name: string, args: Record<string, unknown>) => {
            (window as unknown as { __calls: unknown[] }).__calls.push({
              name,
              args,
            });
            if (name === "add_to_my_cart") {
              if (Array.isArray(args.items)) {
                items = args.items
                  .filter((i) => i.quantity > 0)
                  .map((i) => ({
                    ...product,
                    product_id: i.product_id,
                    quantity: i.quantity,
                  }));
              } else {
                items = [
                  {
                    ...product,
                    product_id: "101",
                    quantity: Number(items[0]?.quantity || 0) + 1,
                  },
                ];
              }
              return { structuredContent: cart() };
            }
            if (name === "my_cart") return { structuredContent: cart() };
            if (name === "checkout_order") {
              if (args.action === "submit") {
                if (failSubmit)
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
              if (args.action === "review")
                return {
                  structuredContent: {
                    status: "review",
                    confirmation_id: "review-test",
                    review: {
                      ...cart(),
                      subtotal: cart().total,
                      delivery_fee: 0,
                      total: cart().total,
                      destination: "Farmacia, Street 1",
                      contact: args.contact,
                      delivery_window: {
                        deliveryDate: "03.11.2026",
                        from: "13:00",
                        to: "15:00",
                      },
                      available_windows: [
                        {
                          deliveryDate: "03.11.2026",
                          from: "13:00",
                          to: "15:00",
                        },
                      ],
                      payment_method: args.payment_method,
                    },
                  },
                };
              return {
                structuredContent: {
                  status: "delivery_method_selection",
                  cart: cart(),
                  regions: [{ id: 2, name: "Кишинёв" }],
                  cities: [{ id: 24, region_id: 2, name: "Чеканы" }],
                  pharmacies: [
                    {
                      id: 1,
                      region_id: 2,
                      city_id: 24,
                      name: "Farmacia",
                      address: "Street 1",
                    },
                  ],
                },
              };
            }
            throw new Error(`Unexpected tool ${name}`);
          },
          setWidgetState: () => {},
        },
      });
    },
    { failSubmit },
  );
  await page.route("https://widget.test/", (route) =>
    route.fulfill({ contentType: "text/html", body: html }),
  );
  await page.goto("https://widget.test/");
  await expect(
    page.getByRole("button", { name: "В корзину", exact: true }),
  ).toBeVisible();
}

for (const width of [320, 768, 1280]) {
  test(`pickup checkout with cart editing at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await loadWidget(page);
    await page.getByRole("button", { name: "В корзину", exact: true }).click();
    await page.getByRole("button", { name: /^Корзина/ }).click();
    await expect(page.locator("#products-page-my-cart")).toBeVisible();
    await page.getByRole("button", { name: "Увеличить количество" }).click();
    await expect(page.locator("#cart-total")).toContainText("80.00");
    await page
      .getByRole("button", { name: "Оформить заказ", exact: true })
      .click();
    await page.getByLabel("Имя", { exact: true }).fill("Анна");
    await page.getByLabel("Телефон", { exact: true }).fill("+37379802000");
    await page.getByRole("button", { name: "Проверить заказ" }).click();
    await expect(page.locator("#checkout-review")).toContainText(
      "Farmacia, Street 1",
    );
    await page.screenshot({
      path: test.info().outputPath("checkout-review.png"),
      fullPage: true,
    });
    await expect(
      page.getByRole("button", { name: "Подтвердить заказ" }),
    ).toBeDisabled();
    await page.getByLabel("Принимаю условия").check();
    await page.getByRole("button", { name: "Подтвердить заказ" }).click();
    await expect(page.locator("#checkout-success")).toContainText("AP-123");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    const calls = await page.evaluate(
      () =>
        (
          window as unknown as {
            __calls: { name: string; args: Record<string, unknown> }[];
          }
        ).__calls,
    );
    expect(calls.filter((c) => c.args.action === "submit")).toHaveLength(1);
    expect(
      calls
        .filter((c) => c.name !== "add_to_my_cart")
        .every((c) => c.args.cart_session_id === "session-test"),
    ).toBeTruthy();
  });
}

test("submission failure retains cart and shows an error", async ({ page }) => {
  await loadWidget(page, true);
  await page.getByRole("button", { name: "В корзину", exact: true }).click();
  await page.getByRole("button", { name: /^Корзина/ }).click();
  await page
    .getByRole("button", { name: "Оформить заказ", exact: true })
    .click();
  await page.getByLabel("Имя", { exact: true }).fill("Анна");
  await page.getByLabel("Телефон", { exact: true }).fill("+37379802000");
  await page.getByRole("button", { name: "Проверить заказ" }).click();
  await page.getByLabel("Принимаю условия").check();
  await page.getByRole("button", { name: "Подтвердить заказ" }).click();
  await expect(page.getByRole("alert")).toContainText("Order status uncertain");
  await page.getByRole("button", { name: "Вернуться в корзину" }).click();
  await expect(page.locator("#cart-items")).toContainText("Парацетамол");
  await expect(page.locator("#cart-total")).toContainText("40.00");
});

test("courier requires an address and never submits during review", async ({
  page,
}) => {
  await loadWidget(page);
  await page.getByRole("button", { name: "В корзину", exact: true }).click();
  await page.getByRole("button", { name: /^Корзина/ }).click();
  await page
    .getByRole("button", { name: "Оформить заказ", exact: true })
    .click();
  await page.getByLabel("Курьерская доставка", { exact: true }).check();
  await page.getByLabel("Имя", { exact: true }).fill("Анна");
  await page.getByLabel("Телефон", { exact: true }).fill("+37379802000");
  await page.getByRole("button", { name: "Проверить заказ" }).click();
  await expect(page.locator("#checkout-review")).toBeHidden();
  await page.getByLabel("Улица", { exact: true }).fill("Дачия");
  await page.getByLabel("Дом", { exact: true }).fill("10");
  await page.getByRole("button", { name: "Проверить заказ" }).click();
  await expect(page.locator("#checkout-review")).toBeVisible();
  const calls = await page.evaluate(
    () =>
      (window as unknown as { __calls: { args: Record<string, unknown> }[] })
        .__calls,
  );
  expect(calls.some((c) => c.args.action === "submit")).toBeFalsy();
  expect(calls.find((c) => c.args.action === "review")?.args.address).toEqual(
    expect.objectContaining({ street: "Дачия", house_number: "10" }),
  );
});

test("removing the last item disables checkout", async ({ page }) => {
  await loadWidget(page);
  await page.getByRole("button", { name: "В корзину", exact: true }).click();
  await page.getByRole("button", { name: /^Корзина/ }).click();
  await page.getByRole("button", { name: "Удалить товар" }).click();
  await expect(page.locator("#cart-items")).toContainText("Корзина пуста");
  await expect(
    page.getByRole("button", { name: "Оформить заказ", exact: true }),
  ).toBeDisabled();
});

test("host tool results can open the cart after search hydration", async ({
  page,
}) => {
  await loadWidget(page);
  await page.evaluate(() => {
    window.dispatchEvent(
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
    );
  });
  await expect(page.locator("#products-page-my-cart")).toBeVisible();
  await expect(page.locator("#cart-total")).toContainText("80.00");
});
