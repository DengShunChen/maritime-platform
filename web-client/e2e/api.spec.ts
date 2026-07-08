import { test, expect } from '@playwright/test';

test.describe('Backend API smoke', () => {
  test('health', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('ok');
  });

  test('cache stats', async ({ request }) => {
    const res = await request.get('/cache/stats');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.tile).toBeDefined();
    expect(body.tile).toHaveProperty('hits');
    expect(body.wind_texture).toBeDefined();
  });

  test('wind texture metadata', async ({ request }) => {
    const res = await request.get('/wind_texture?time=0&metadata=true');
    expect(res.status()).toBeLessThan(500);
  });
});
