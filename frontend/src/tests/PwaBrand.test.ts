import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(__dirname, '../..');

describe('CertExam installable PWA', () => {
  it('uses the CertExam name in the document and web manifest', () => {
    const html = readFileSync(resolve(root, 'index.html'), 'utf8');
    const manifest = JSON.parse(readFileSync(resolve(root, 'public/manifest.webmanifest'), 'utf8'));
    expect(html).toContain('<title>CertExam</title>');
    expect(html).toContain('rel="manifest"');
    expect(manifest.name).toBe('CertExam');
    expect(manifest.short_name).toBe('CertExam');
    expect(manifest.display).toBe('standalone');
    expect(manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: '192x192' }),
      expect.objectContaining({ sizes: '512x512' }),
    ]));
  });

  it('registers a service worker and never caches API or authentication requests', () => {
    const main = readFileSync(resolve(root, 'src/main.tsx'), 'utf8');
    const worker = readFileSync(resolve(root, 'public/service-worker.js'), 'utf8');
    expect(main).toContain("serviceWorker.register('/service-worker.js')");
    expect(worker).toContain("url.pathname.startsWith('/api/')");
    expect(worker).toContain("request.mode === 'navigate'");
  });

  it('ships correctly sized icons generated from the supplied artwork', () => {
    for (const size of [192, 512]) {
      const png = readFileSync(resolve(root, `public/icons/certexam-${size}.png`));
      expect(png.readUInt32BE(16)).toBe(size);
      expect(png.readUInt32BE(20)).toBe(size);
    }
  });
});
