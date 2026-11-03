import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("stage results display production photos with an image allowlist", async ({
  page,
}) => {
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
  await page.addInitScript(() =>
    Object.assign(window, {
      openai: {
        toolOutput: {
          api_base_url: "https://stage.apteka.md",
          language: "ru",
          products: [
            {
              id: "1",
              name: "Аспирин",
              price: 40,
              image_url: "https://api.apteka.md/media/test/product.svg",
            },
          ],
        },
        callTool: async () => ({
          structuredContent: {
            cart_session_id: "test",
            items: [],
            count: 0,
            total: 0,
          },
        }),
        setWidgetState: () => {},
      },
    }),
  );
  await page.route("https://api.apteka.md/media/test/product.svg", (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="blue"/></svg>',
    }),
  );
  await page.route("https://widget.test/", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: html,
      headers: {
        "Content-Security-Policy":
          "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src https://api.apteka.md https://www.apteka.md data:",
      },
    }),
  );
  await page.goto("https://widget.test/");
  const photo = page.locator(".product-image");
  await expect(photo).toHaveAttribute(
    "src",
    "https://api.apteka.md/media/test/product.svg",
  );
  await expect(photo).toHaveJSProperty("naturalWidth", 32);
});
