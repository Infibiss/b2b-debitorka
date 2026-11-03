#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const [url = 'http://127.0.0.1:8004/', label = 'audit', profile = 'mobile'] = process.argv.slice(2);
if (url === '--help') {
  console.log('Usage: node scripts/lighthouse.mjs [url] [report-label] [mobile|desktop]');
  console.log('LIGHTHOUSE_OUTPUT_DIR sets the report directory (default: var/lighthouse).');
  console.log('LIGHTHOUSE_CLI optionally selects an existing Lighthouse CLI file.');
  process.exit(0);
}
if (!['http:', 'https:'].includes(new URL(url).protocol)) {
  throw new Error('The audited URL must use HTTP or HTTPS.');
}
if (!/^[a-zA-Z0-9_-]+$/.test(label) || !['mobile', 'desktop'].includes(profile)) {
  throw new Error('Use a simple report label and the mobile or desktop profile.');
}

const prefix = resolve(process.env.LIGHTHOUSE_OUTPUT_DIR || 'var/lighthouse', label);
mkdirSync(dirname(prefix), { recursive: true });
const flags = [
  url,
  '--chrome-flags=--headless=new --no-first-run --no-default-browser-check',
  '--only-categories=performance,accessibility,best-practices,seo',
  '--output=json',
  '--output=html',
  `--output-path=${prefix}`,
  '--quiet',
];
if (profile === 'desktop') flags.push('--preset=desktop');
// Pin the tool, but keep it out of the application bundle and production dependencies.
if (process.env.LIGHTHOUSE_CLI) {
  execFileSync(process.execPath, [resolve(process.env.LIGHTHOUSE_CLI), ...flags], {
    stdio: 'inherit',
  });
} else {
  execFileSync(
    'npx',
    [
      '--yes',
      '--registry=https://registry.npmjs.org',
      '--package=lighthouse@13.1.0',
      'lighthouse',
      ...flags,
    ],
    { stdio: 'inherit' }
  );
}
const report = JSON.parse(readFileSync(`${prefix}.report.json`, 'utf8'));
if (report.runtimeError) throw new Error(report.runtimeError.message);
const summary = {
  url: report.finalDisplayedUrl,
  fetchTime: report.fetchTime,
  lighthouseVersion: report.lighthouseVersion,
  userAgent: report.environment.hostUserAgent,
  profile,
  scores: Object.fromEntries(
    Object.entries(report.categories).map(([key, value]) => [key, Math.round(value.score * 100)])
  ),
  metrics: Object.fromEntries(
    [
      'first-contentful-paint',
      'largest-contentful-paint',
      'total-blocking-time',
      'cumulative-layout-shift',
      'speed-index',
      'total-byte-weight',
    ].map((key) => [key, report.audits[key].displayValue])
  ),
  reports: [`${prefix}.report.html`, `${prefix}.report.json`],
};
writeFileSync(`${prefix}.summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
console.log(JSON.stringify(summary, null, 2));
