import { test as base, expect } from '@playwright/test';

// Each test models an independent client behind the local trusted test proxy.
// Keep production rate limits active without pooling 24 users into one IP bucket.
export const test = base.extend({
  extraHTTPHeaders: async ({ extraHTTPHeaders }, use, info) => {
    const ip = `198.18.${info.project.name === 'mobile' ? 2 : 1}.${info.testId.split('').reduce((value, char) => (value * 31 + char.charCodeAt(0)) % 250, 0) + 1}`;
    await use({ ...extraHTTPHeaders, 'X-Forwarded-For': ip });
  },
});
export { expect };

export type { Page } from '@playwright/test';
