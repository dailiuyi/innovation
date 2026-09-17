// Exercise the actual component's asynchronous loaders with deliberately reordered responses.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../frontend/src/views/demo/DraftPanel.vue', import.meta.url), 'utf8')
const script = source.split('<script setup>')[1].split('</script>')[0]
  .replace(/^import .*$/gm, '').replaceAll('import.meta.url', "'file:///hash.worker.js'")
const pending = []
const props = { sceneId: 'scene-a' }
const context = vm.createContext({
  defineProps: () => props, defineEmits: () => () => {}, ref: value => ({ value }),
  useRoute: () => ({ query: {} }), useRouter: () => ({ replace: async () => {} }),
  watch: () => {}, onBeforeUnmount: () => {},
  request: { get: url => new Promise(resolve => pending.push({ url, resolve })) }
})
vm.runInContext(script, context)
const run = code => vm.runInContext(code, context)
const draft = id => ({ id, sceneId: props.sceneId, description: id })
const response = name => ({ items: [{ fileName: name }], total: 1 })

const firstSelection = run("selectDraft('a')")
const secondSelection = run("selectDraft('b')")
pending[1].resolve(draft('b'))
await new Promise(resolve => setImmediate(resolve))
pending[2].resolve(response('b.bin'))
await secondSelection
pending[0].resolve(draft('a'))
await firstSelection
assert.equal(run('selected.value.id'), 'b')
assert.equal(run('files.value[0].fileName'), 'b.bin')

pending.length = 0
const oldFiles = run('loadFiles()')
const newFiles = run('loadFiles()')
pending[1].resolve(response('new.bin'))
await newFiles
pending[0].resolve(response('old.bin'))
await oldFiles
assert.equal(run('files.value[0].fileName'), 'new.bin')

pending.length = 0
const oldDrafts = run('loadDrafts()')
const newDrafts = run('loadDrafts()')
pending[1].resolve({ items: [draft('new')], total: 1 })
await newDrafts
pending[0].resolve({ items: [draft('old')], total: 1 })
await oldDrafts
assert.equal(run('drafts.value[0].id'), 'new')

pending.length = 0
const wrongScene = run("selectDraft('foreign')")
pending[0].resolve({ id: 'foreign', sceneId: 'another-scene' })
await wrongScene
assert.equal(run('selected.value'), null)
assert.match(run('error.value'), /不属于当前场景/)

pending.length = 0
const closed = run("selectDraft('a')")
props.sceneId = ''
pending[0].resolve({ id: 'a', sceneId: 'scene-a' })
await closed
assert.equal(run('selected.value'), null)
console.log('PASS: selection order, file response order, draft response order, scene ownership, closed panel')
