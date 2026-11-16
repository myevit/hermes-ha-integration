// Fork-owned visual qualification: paint the ACTUAL Desktop message components
// (unmodified /opt/hermes/apps/desktop/src) in a real browser with the real
// compiled stylesheet, and assert the recognition words are actually visible.
// No product UI is added; nothing under /opt/hermes is written.
//
// Usage:
//   node companion/tests/visual/verify_recognition_visual.mjs <receipt.json> <outdir>
// Env: HERMES_ESBUILD_PATH, HERMES_DESKTOP_SOURCE, HERMES_DESKTOP_DEPS,
//      HERMES_PLAYWRIGHT_PATH, HERMES_PLAYWRIGHT_BROWSERS
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const require = createRequire(import.meta.url)
// Must be set before Playwright is required (it reads the cache path at import).
process.env.PLAYWRIGHT_BROWSERS_PATH = process.env.HERMES_PLAYWRIGHT_BROWSERS
const esbuild = require(process.env.HERMES_ESBUILD_PATH)
const playwright = require(process.env.HERMES_PLAYWRIGHT_PATH)
// The installed Playwright is a patch ahead of the cached browser build; point
// it at the browser that is actually present rather than downloading one.
const chromiumPath = process.env.HERMES_CHROMIUM_PATH
const source = process.env.HERMES_DESKTOP_SOURCE
const deps = process.env.HERMES_DESKTOP_DEPS
const receiptPath = process.argv[2]
const outDir = process.argv[3]
assert(source && deps && receiptPath && outDir, 'missing env/paths')
fs.mkdirSync(outDir, { recursive: true })

const alias = {
  '@/': path.join(source, ''),
  '@hermes/shared': path.join(source, '../../shared/src/index.ts'),
  '@hermes/shared/ansi': path.join(source, '../../shared/src/ansi.ts'),
  '@hermes/shared/color': path.join(source, '../../shared/src/color.ts'),
  '@hermes/shared/i18n': path.join(source, '../../shared/src/i18n.ts'),
  '@hermes/plugin-sdk': path.join(source, 'sdk/index.ts')
}
// Modules the text-only transcript path never calls. Stubbed throw-on-use so a
// surprise call fails loudly instead of silently rendering substitute UI.
const seams = {
  '@/lib/browser-launch-session': ['WEBAPP_LAUNCH_REQUIRED', 'isWebappLaunchRequired'],
  '@/lib/desktop-fs': ['readDesktopFileDataUrl', 'isReadFileErrorResult', 'desktopFsCacheKey'],
  '@/lib/host-capabilities': ['hostHas'],
  '@/lib/notifications-store': ['notify', 'notifyError']
}
const inputs = []
const bundlePath = path.join(outDir, 'recognition-render.bundle.mjs')
// Plugin-resolved paths bypass esbuild's extension resolution, so resolve the
// same candidate list the app's bundler uses.
function withExtension(base) {
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  }
  return base
}
const seamPlugin = {
  name: 'visual-harness-seams',
  setup(build) {
    build.onResolve({ filter: /^@\// }, args => ({ path: withExtension(path.join(source, args.path.slice(2))) }))
    build.onResolve({ filter: /^@hermes\/shared(\/.*)?$/ }, args => ({ path: alias[args.path] }))
    build.onResolve({ filter: /^@hermes\/plugin-sdk$/ }, () => ({ path: alias['@hermes/plugin-sdk'] }))
    build.onResolve({ filter: /^@\/lib\/(browser-launch-session|desktop-fs|host-capabilities)$/ },
      args => ({ path: args.path, namespace: 'unused-seam' }))
    build.onLoad({ filter: /.*/, namespace: 'unused-seam' }, args => ({
      contents: `const fail = () => { throw new Error('Unused seam called: ${args.path}') }\n` +
        `export const WEBAPP_LAUNCH_REQUIRED = fail()\nexport const isWebappLaunchRequired = fail\n` +
        `export const readDesktopFileDataUrl = fail\nexport const isReadFileErrorResult = fail\n` +
        `export const desktopFsCacheKey = fail\nexport const hostHas = fail\n` +
        `export const notify = fail\nexport const notifyError = fail\n` +
        `export default fail\n`,
      loader: 'js'
    }))
    build.onLoad({ filter: /\.[jt]sx?$/ }, args => {
      inputs.push(args.path)
      return { contents: fs.readFileSync(args.path, 'utf8'), loader: args.path.endsWith('.tsx') ? 'tsx' : 'ts' }
    })
  }
}
await esbuild.build({
  entryPoints: [path.join(import.meta.dirname, 'recognition-render-harness.tsx')],
  outfile: bundlePath, bundle: true, platform: 'browser', format: 'esm', target: 'es2022',
  jsx: 'automatic', jsxImportSource: 'react', nodePaths: [deps], minify: false, logLevel: 'warning',
  // A lazily code-split mermaid renderer, absent from the borrowed dependency
  // tree and never reached by plain text rows.
  external: ['pele/lazy'],
  define: { 'process.env.NODE_ENV': '"production"' },
  // Vite substitutes `import.meta.env` at build time; the harness reproduces the
  // production values (DEV false, MODE production) the shipped bundle sees.
  banner: { js: "import.meta.env = { DEV: false, PROD: true, MODE: 'production', BASE_URL: '/', SSR: false };" },
  plugins: [seamPlugin]
})

// Real compiled stylesheet from the unmodified Desktop source. The official
// install ships no node_modules, so the stylesheet is staged in a scratch dir
// whose node_modules is the borrowed dependency tree. Tailwind's Node API takes
// candidate class names from its caller (the CLI/Vite plugin does the file
// scanning), so candidates are read out of the unmodified Desktop source here.
const { compile } = createRequire(path.join(deps, 'noop.cjs'))('@tailwindcss/node')
const cssRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'recognition-visual-css-'))
fs.symlinkSync(deps, path.join(cssRoot, 'node_modules'))
const stylesheet = fs.readFileSync(path.join(source, 'styles.css'), 'utf8')
const compiled = await compile(stylesheet, { base: cssRoot, onDependency: () => {} })

function* sourceFiles(root) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name)
    if (entry.isDirectory()) yield* sourceFiles(full)
    else if (/\.(tsx?|jsx?|html)$/.test(entry.name)) yield full
  }
}

const candidates = new Set()
for (const file of sourceFiles(source)) {
  const text = fs.readFileSync(file, 'utf8')
  for (const literal of text.matchAll(/(['"`])([^'"`\n]*)\1/g)) {
    for (const token of literal[2].split(/\s+/)) {
      if (token && token.length < 120) candidates.add(token)
    }
  }
}
const css = compiled.build([...candidates])
fs.writeFileSync(path.join(outDir, 'recognition-render.css'), css)

const receipt = JSON.parse(fs.readFileSync(receiptPath, 'utf8'))
const cases = Object.entries(receipt).filter(([name]) => name.endsWith('_desktop'))
assert(cases.length >= 2, `expected several desktop surfaces, got ${cases.length}`)
// The pre-change persisted shape for the same words: the row the old engine
// wrote, role 'system' with identical text/metadata, rendered by the same
// unmodified components. This is the defect baseline, not a mock-up.
const success = receipt.success_desktop
if (success) {
  cases.push(['success_system_before_desktop', success.map(row =>
    row.display_kind === 'native_audio_recognition' ? { ...row, role: 'system' } : row)])
}

const casesDir = path.join(outDir, 'cases')
fs.mkdirSync(casesDir, { recursive: true })
// Module scripts are blocked over file://, so serve the fixtures over loopback.
const server = http.createServer((request, response) => {
  const requested = decodeURIComponent(new URL(request.url, 'http://x').pathname)
  // Fonts the real stylesheet references resolve against the borrowed deps.
  const asset = requested.endsWith('/codicon.ttf')
    ? path.join(deps, '@vscode/codicons/dist/codicon.ttf')
    : requested.includes('/fonts/') ? path.join(deps, 'katex/dist', requested.slice(requested.indexOf('/fonts/'))) : null
  const target = asset || path.join(outDir, requested)
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    response.writeHead(404).end()

    return
  }
  const type = target.endsWith('.css') ? 'text/css'
    : target.endsWith('.mjs') ? 'text/javascript'
      : target.endsWith('.ttf') ? 'font/ttf'
        : target.endsWith('.woff2') ? 'font/woff2' : 'text/html'
  response.writeHead(200, { 'content-type': type })
  fs.createReadStream(target).pipe(response)
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const results = {}
const browser = await playwright.chromium.launch(chromiumPath ? { executablePath: chromiumPath } : {})
try {
  for (const [name, rows] of cases) {
    const htmlPath = path.join(casesDir, `${name}.html`)
    fs.writeFileSync(htmlPath, `<!doctype html><html class="dark"><head><meta charset="utf-8">
<link rel="icon" href="data:,">
<style>${css}</style></head><body class="bg-(--dt-background) text-foreground">
<script>window.__ROWS__ = ${JSON.stringify(rows)}</script>
<div id="root" class="mx-auto h-screen w-full max-w-3xl px-4"></div>
<script type="module" src="/recognition-render.bundle.mjs"></script></body></html>`)
    for (const [label, viewport] of [['wide', { width: 900, height: 720 }], ['narrow', { width: 360, height: 720 }]]) {
      const page = await browser.newPage({ colorScheme: 'dark', viewport, deviceScaleFactor: 2 })
      const errors = []
      const missing = []
      page.on('pageerror', error => errors.push(String(error)))
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
      page.on('response', response => { if (response.status() === 404) missing.push(response.url()) })
      await page.goto(`${origin}/cases/${name}.html`, { waitUntil: 'load' })
      try {
        await page.waitForFunction(() => window.__MOUNTED__ === true, null, { timeout: 20000 })
      } catch (error) {
        const body = await page.evaluate(() => document.body.innerHTML.slice(0, 600)).catch(() => '')
        throw new Error(`${name}/${label} did not mount: ${errors.join(' | ')}\n${body}\n${error}`)
      }
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(250)
      const measured = await page.evaluate(() => {
        const root = getComputedStyle(document.documentElement)
        const pick = selector => document.querySelector(selector)
        const textOf = element => (element ? element.textContent : null)
        const row = pick('[data-slot="aui_user-message-root"], [data-slot="aui_system-message-root"]')
        const bubble = pick('[data-slot="aui_user-message-root"]') ? pick('.composer-human-message') : null
        const body = bubble || row
        const inner = body ? body.querySelector('[data-slot="aui_user-message-text"]') || body : null
        const styles = inner ? getComputedStyle(inner) : null
        const rect = body ? body.getBoundingClientRect() : null
        // Per-line visibility: hit-test every line box of the row's longest text
        // node, so a clamped/faded row reports exactly which lines a reader sees.
        const clamp = body ? body.querySelector('.sticky-human-clamp') : null
        const lines = { total: 0, visible: 0, clamp: clamp ? clamp.dataset.clamped ?? null : null, maxHeight: clamp ? getComputedStyle(clamp).maxHeight : null }
        if (row) {
          const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT)
          let longest = null
          while (walker.nextNode()) {
            if (!longest || walker.currentNode.data.length > longest.data.length) longest = walker.currentNode
          }
          if (longest) {
            const range = document.createRange()
            range.selectNodeContents(longest)
            for (const box of range.getClientRects()) {
              if (box.width < 1 || box.height < 1) continue
              lines.total += 1
              const hit = document.elementFromPoint(box.left + 1, box.top + box.height / 2)
              if (hit && row.contains(hit)) lines.visible += 1
            }
          }
        }
        return {
          theme: { mode: document.documentElement.dataset.hermesMode, background: root.getPropertyValue('--dt-background').trim(), colorScheme: root.colorScheme },
          role: row ? row.dataset.role : null,
          hasUserBubble: Boolean(pick('[data-slot="aui_user-message-root"]')),
          userBubbleCount: document.querySelectorAll('[data-slot="aui_user-message-root"]').length,
          systemRowCount: document.querySelectorAll('[data-slot="aui_system-message-root"]').length,
          lines,
          font: styles ? { size: styles.fontSize, lineHeight: styles.lineHeight, family: styles.fontFamily } : null,
          clamped: body ? { client: body.clientHeight, scroll: body.scrollHeight } : null,
          text: textOf(inner),
          textLength: textOf(inner) ? textOf(inner).length : 0,
          rect: rect ? { width: Math.round(rect.width), height: Math.round(rect.height) } : null,
          bodyHtml: body ? body.innerHTML.slice(0, 400) : null,
          wholeText: document.body.innerText
        }
      })
      assert.equal(errors.length, 0, `${name}/${label}: ${errors.join(' | ')} [missing: ${missing.join(' ')}]`)
      const available = name.startsWith('success') && !name.includes('_before_') || name.startsWith('interrupted_available') || name.startsWith('long_non_latin')
      const baseline = name.includes('_before_')
      assert.equal(measured.role, available ? 'user' : 'system', `${name}/${label}: role`)
      assert.equal(measured.userBubbleCount, available ? 1 : 0, `${name}/${label}: user bubbles`)
      assert.equal(measured.theme.mode, 'dark', `${name}/${label}: theme`)
      if (available) {
        // The words row must be the app's ordinary human bubble typography and
        // must actually paint: at least the clamp's own lines are hit-testable.
        assert.equal(measured.font.size, '13px', `${name}/${label}: human bubble font`)
        assert(measured.lines.visible >= Math.min(measured.lines.total, 3),
          `${name}/${label}: only ${measured.lines.visible}/${measured.lines.total} text lines painted`)
      } else if (baseline) {
        // Pre-change persisted shape: the same words, painted as the faint
        // 11px system line this change replaces.
        assert.equal(measured.font.size, '11px', `${name}/${label}: system row font`)
        assert(measured.text.startsWith('Speech recognition ('), `${name}/${label}: words in system row`)
      } else {
        assert.equal(measured.font.size, '11px', `${name}/${label}: system row font`)
        assert(measured.text.startsWith('Speech recognition unavailable ('), `${name}/${label}: machine wording`)
      }
      if (name.startsWith('long_non_latin')) {
        // Long utterance: the app's standard 4-line human-bubble clamp applies
        // (same as any long typed prompt). Record it instead of pretending.
        assert.equal(measured.lines.clamp, 'true', `${name}/${label}: clamp marker`)
        assert(measured.text.endsWith('Конец распознавания.'), `${name}/${label}: full text in the row`)
      }
      const image = path.join(outDir, `${name}-${label}.png`)
      await page.screenshot({ path: image, fullPage: true })
      results[`${name}/${label}`] = { ...measured, image }
      await page.close()
    }
  }
} finally {
  await browser.close()
  server.close()
}
fs.writeFileSync(path.join(outDir, 'visual-measurements.json'),
  JSON.stringify({ cases: results, actual_sources: inputs.length, bundle: bundlePath, css_bytes: css.length }, null, 2))
console.log(JSON.stringify({ result: 'RENDERED', cases: Object.keys(results) }, null, 2))
