// Execute existing Desktop history hydration, not a reimplementation or UI change.
// Unrelated media/connector/error UI imports are fail-on-use seams for text-only rows.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const require = createRequire(import.meta.url)
const esbuild = require(process.env.HERMES_ESBUILD_PATH)
const source = process.env.HERMES_DESKTOP_SOURCE
const receipt = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const out = process.argv[3]
assert(source && out)
const actual = {
  './parts': 'lib/chat-messages/parts.ts',
  './tool-parts': 'lib/chat-messages/tool-parts.ts',
  '@/lib/generated-images': 'lib/generated-images.ts',
  '@hermes/shared': '../../shared/src/skill-scaffold.ts',
  '@/components/assistant-ui/reference-kinds': 'components/assistant-ui/reference-kinds.ts',
  '@/lib/embedded-images': 'lib/embedded-images.ts',
  '@/lib/error-surface': 'lib/error-surface.ts',
  '@/lib/todos': 'lib/todos.ts',
  '@/lib/text': 'lib/text.ts'
}
const seams = {
  '@hermes/shared': ['skillInvocationText'],
  '@/components/assistant-ui/directive-text': ['formatRefValue'],
  '@/components/assistant-ui/reference-kinds': ['splitLeadingAttachmentRefs'],
  '@/lib/embedded-images': ['extractImageRefs'],
  '@/lib/error-surface': ['parseErrorSurface'],
  '@/lib/todos': ['isTodoToolName', 'parseTodos'],
  '@/lib/connector-tools': ['TOOL_LABELS_ARG'],
  '@/lib/text': ['firstStringField', 'normalize'],
  '@/lib/media': ['mediaDisplayLabel', 'mediaMarkdownHref']
}
const inputs = []
await esbuild.build({
  entryPoints: [path.join(source, 'lib/chat-messages/hydration.ts')],
  outfile: out, bundle: true, platform: 'node', format: 'esm',
  plugins: [{name: 'text-only-unrelated-ui-seams', setup(build) {
    build.onResolve({filter: /.*/}, args => {
      if (actual[args.path]) return {path: path.resolve(source, actual[args.path])}
      if (seams[args.path]) return {path: args.path, namespace: 'unrelated-ui'}
      if (args.kind === 'entry-point') return {path: args.path}
      throw new Error(`Unexpected dependency: ${args.path}`)
    })
    build.onLoad({filter: /.*/, namespace: 'unrelated-ui'}, args => ({
      contents: seams[args.path].map(name => name === 'TOOL_LABELS_ARG'
        ? `export const ${name} = '__tool_labels'`
        : `export function ${name}(){throw new Error('Unexpected unrelated UI use: ${name}')}`).join('\n'), loader: 'js'
    }))
    build.onLoad({filter: /\.ts$/}, args => {
      inputs.push(args.path)
      return {contents: fs.readFileSync(args.path, 'utf8'), loader: 'ts'}
    })
  }}]
})
const {toChatMessages} = await import(pathToFileURL(out))
const results = {}
for (const [surface, rows] of Object.entries(receipt)) {
  const row = rows.find(r => r.display_kind === 'native_audio_recognition')
  assert(row)
  // Feed ALL actual REST/projection rows, including the contentless audio receipt,
  // tool calls/results and interruption notice. Pre-filtering hid duplicate turns.
  const hydrated = toChatMessages(rows)
  const text = row.content || row.text
  const available = text.startsWith('Speech recognition (')
  const recognized = hydrated.filter(r => r.parts.some(p => p.type === 'text' && p.text === text))
  assert.equal(recognized.length, 1, surface)
  assert.equal(recognized[0].role, available ? 'user' : 'system', surface)
  assert.equal(hydrated.filter(r => r.role === 'user').length, available ? 1 : 0,
    `${surface}: contentless audio receipt must not create another user bubble`)
  if (available) assert(text.includes('may contain errors; not guaranteed verbatim'))
  else assert(text.startsWith('Speech recognition unavailable ('))
  const terminal = hydrated.at(-1)
  assert.notEqual(terminal, recognized[0])
  if (surface.startsWith('interrupted')) {
    assert.equal(terminal.role, 'system')
    assert(terminal.parts.some(p => p.text?.includes('Native audio turn interrupted')))
  } else assert.equal(terminal.role, 'assistant')
  assert(hydrated.indexOf(recognized[0]) < hydrated.indexOf(terminal))
  assert.equal(toChatMessages([{...row, content: null, text: undefined}]).length, 0, 'metadata-only row must be invisible')
  assert.equal(toChatMessages([{...row, display_kind: 'hidden'}]).length, 0)
  results[surface] = hydrated
}
console.log(JSON.stringify({result: 'PASS', actual_sources: inputs, unrelated_seams: 'throw on use; none invoked', surfaces: results}, null, 2))
