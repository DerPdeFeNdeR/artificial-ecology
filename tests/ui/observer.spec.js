const { test, expect } = require('@playwright/test');

async function tick(page) {
  return page.locator('#meta').textContent();
}

test.describe('observer layout and controls', () => {
  test('desktop layout keeps all observation panels visible', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    await expect(page.locator('.map-panel')).toBeVisible();
    await expect(page.locator('.sidebar')).toBeVisible();
    await expect(page.locator('.events-panel')).toBeVisible();
    await expect(page.locator('.inspector')).toBeVisible();

    const pageBounds = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    }));
    expect(pageBounds.width).toBeLessThanOrEqual(pageBounds.viewportWidth + 1);
    expect(pageBounds.height).toBeLessThanOrEqual(pageBounds.viewportHeight + 1);
  });

  test('start, stop, and inhabitant inspection work', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    await expect(page.locator('#meta')).toContainText('STATUS stopped');
    await page.getByRole('button', { name: 'Start' }).click();
    await expect.poll(() => tick(page)).toContain('TICK 1');

    const map = page.locator('#map');
    const bounds = await map.boundingBox();
    const state = await page.request.get('/api/state').then(response => response.json());
    const inhabitant = Object.values(state.world.inhabitants).find(item => item.alive);
    const cell = Math.min(600 / state.world.width, 600 / state.world.height);
    const offsetX = (600 - state.world.width * cell) / 2;
    const offsetY = (600 - state.world.height * cell) / 2;
    await map.click({
      position: {
        x: (offsetX + (inhabitant.position.x + .5) * cell) * bounds.width / 600,
        y: (offsetY + (inhabitant.position.y + .5) * cell) * bounds.height / 600,
      },
    });
    await expect(page.locator('.inspector')).toContainText('NAME');
    await expect(page.locator('.inspector')).toContainText('MEMORIES');

    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.locator('#meta')).toContainText('STATUS stopped');
  });

  test('narrow layout does not create horizontal overflow', async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 800 });
    await page.goto('/');

    const bounds = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(bounds.width).toBeLessThanOrEqual(bounds.viewportWidth + 1);
    await expect(page.locator('.events-panel')).toBeVisible();
    await expect(page.locator('.inspector')).toBeVisible();
  });
});
