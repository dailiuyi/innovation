// Exercise the actual component's asynchronous loaders with deliberately reordered responses.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../frontend/src/views/demo/DraftPanel.vue', import.meta.url), 'utf8')
const script = source.split('<script setup>')[1].split('</script>')[0]
  .replace(/^import .*$/gm, '').replaceAll('import.meta.url', "'file:///hash.worker.js'")
  .replaceAll('import.meta.env.VITE_APP_BASE_API', "''").replaceAll('import.meta.env', '({VITE_APP_BASE_API:""})')
let sceneChanged
const route = { query: {} }
const pending = []
const props = { sceneId: 'scene-a' }
const context = vm.createContext({
  defineProps: () => props, defineEmits: () => () => {}, ref: value => ({ value }),
  useRoute: () => route, useRouter: () => ({ replace: async ({ query }) => { route.query = query } }),
  watch: (getter, callback) => { sceneChanged = callback }, onBeforeUnmount: () => {},
  ElMessageBox: { confirm: async () => {} }, ElMessage: { success: () => {} },
  request: { get: url => new Promise(resolve => pending.push({ url, resolve })), post: async () => ({}) }
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

pending.length = 0
props.sceneId = 'scene-a'
run("selected.value={id:'a',sceneId:'scene-a',published:false,description:'old'};editDescription.value='old'")
const refreshing = run('refresh()')
pending[0].resolve({ items: [{ id: 'a', sceneId: 'scene-a', published: true, description: 'live' }], total: 1, sceneLockVersion: 2, published: { id: 'a' } })
await new Promise(resolve => setImmediate(resolve))
pending[1].resolve({ id: 'a', sceneId: 'scene-a', published: true, description: 'live' })
await new Promise(resolve => setImmediate(resolve))
pending[2].resolve(response('kept.bin'))
await refreshing
assert.equal(run('selected.value.published'), true)
assert.equal(run('selected.value.description'), 'live')
assert.equal(run('published.value.id'), 'a')
assert.equal(run('files.value[0].fileName'), 'kept.bin')
console.log('PASS: selection order, file response order, draft response order, scene ownership, closed panel, refresh syncs published')

const tick = () => new Promise(resolve => setImmediate(resolve))
async function resolveNext(url, value) {
  await tick()
  const item = pending.shift()
  assert.equal(item?.url, url)
  item.resolve(value)
  await tick()
}
async function enter(published, restored) {
  pending.length = 0
  props.sceneId = 'scene-a'
  route.query = { draftScene: 'scene-a', ...(restored ? { draftId: restored } : {}) }
  const entering = sceneChanged('scene-a')
  assert.equal(run('selected.value'), null)
  assert.equal(run('files.value.length'), 0)
  await resolveNext('/api/v1/drafts/config', {})
  // Published draft need not be on the current list page.
  await resolveNext('/api/v1/scenes/scene-a/drafts', { items: [], total: 21, published })
  const id = restored || published?.id
  if (id) {
    await resolveNext(`/api/v1/drafts/${id}`, { ...draft(id), published: id === published?.id })
    await resolveNext(`/api/v1/drafts/${id}/files`, response(id + '.bin'))
  }
  await entering
}
await enter({ id: 'live' })
assert.equal(run('selected.value.id'), 'live')
assert.equal(run('selected.value.published'), true)
assert.equal(run('files.value[0].fileName'), 'live.bin')
await enter({ id: 'live' }, 'manual')
assert.equal(run('selected.value.id'), 'manual')
const manualRefresh = run('refresh()')
await resolveNext('/api/v1/scenes/scene-a/drafts', { items: [], total: 0, published: { id: 'live' } })
await resolveNext('/api/v1/drafts/manual', draft('manual'))
await resolveNext('/api/v1/drafts/manual/files', response('manual.bin'))
await manualRefresh
assert.equal(run('selected.value.id'), 'manual')
await enter(null)
assert.equal(run('selected.value'), null)
for (const id of ['first-live', 'replacement-live']) {
  const publishing = run(`publishDraft({id:'${id}'})`)
  await resolveNext('/api/v1/scenes/scene-a/drafts', { items: [], total: 1, published: { id } })
  await resolveNext(`/api/v1/drafts/${id}`, { ...draft(id), published: true })
  await resolveNext(`/api/v1/drafts/${id}/files`, response(id + '.bin'))
  await publishing
  assert.equal(run('selected.value.id'), id)
  assert.equal(run('selected.value.published'), true)
}
// Switching away and back must invalidate even a same-scene late response.
const stale = sceneChanged('scene-a')
const oldConfig = pending.shift()
props.sceneId = 'scene-b'
const nextScene = sceneChanged('scene-b')
assert.equal(run('files.value.length'), 0)
assert.equal(run('selected.value'), null)
await resolveNext('/api/v1/drafts/config', {})
await resolveNext('/api/v1/scenes/scene-b/drafts', { items: [], total: 0 })
await nextScene
oldConfig.resolve({})
await stale
assert.equal(pending.length, 0)
assert.equal(run('selected.value'), null)
console.log('PASS: default published selection, off-page publication, restore/manual refresh, unpublished scene, first/replacement publish, scene reset and stale initialization')
