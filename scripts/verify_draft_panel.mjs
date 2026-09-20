// Exercise the actual component's asynchronous loaders with deliberately reordered responses.
import assert from 'node:assert/strict'
import { Blob } from 'node:buffer'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('../frontend/src/views/demo/DraftPanel.vue', import.meta.url), 'utf8')
const script = source.split('<script setup>')[1].split('</script>')[0]
  .replace(/^import .*$/gm, '').replaceAll('import.meta.url', "'file:///hash.worker.js'")
  .replaceAll('import.meta.env.VITE_APP_BASE_API', "''").replaceAll('import.meta.env', '({VITE_APP_BASE_API:""})')
let sceneChanged
const route = { query: {} }
const pending = []
const zipPosts = []
const zipGets = []
const saved = []
const props = { sceneId: 'scene-a' }
const context = vm.createContext({
  defineProps: () => props, defineEmits: () => () => {}, ref: value => ({ value }),
  useRoute: () => route, useRouter: () => ({ replace: async ({ query }) => { route.query = query } }),
  watch: (getter, callback) => { sceneChanged = callback }, onBeforeUnmount: () => {},
  ElMessageBox: { confirm: async () => {} }, ElMessage: { success: () => {} },
  Blob, getToken: () => 'test-token', blobValidate: data => data.type !== 'application/json',
  saveAs: (blob, name) => saved.push({ blob, name }),
  axios: { get: (url, config) => new Promise((resolve, reject) => zipGets.push({ url, config, resolve, reject })) },
  request: {
    get: url => new Promise(resolve => pending.push({ url, resolve })),
    post: (url, body, config) => url.endsWith('/zip-exports')
      ? new Promise((resolve, reject) => zipPosts.push({ url, body, config, resolve, reject }))
      : Promise.resolve({})
  }
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
  assert.equal(run('sceneName.value'), '')
  await resolveNext('/api/v1/scenes/scene-a', { id: 'scene-a', name: '场景A' })
  assert.equal(run('sceneName.value'), '场景A')
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
props.sceneId = 'scene-b'
const nextScene = sceneChanged('scene-b')
assert.equal(run('files.value.length'), 0)
assert.equal(run('selected.value'), null)
assert.equal(run('sceneName.value'), '')
const oldScene = pending.shift()
const oldConfig = pending.shift()
assert.equal(oldScene.url, '/api/v1/scenes/scene-a')
assert.equal(oldConfig.url, '/api/v1/drafts/config')
await resolveNext('/api/v1/scenes/scene-b', { id: 'scene-b', name: '场景B' })
await resolveNext('/api/v1/drafts/config', {})
await resolveNext('/api/v1/scenes/scene-b/drafts', { items: [], total: 0 })
await nextScene
assert.equal(run('sceneName.value'), '场景B')
oldScene.resolve({ id: 'scene-a', name: '场景A' })
oldConfig.resolve({})
await stale
assert.equal(pending.length, 0)
assert.equal(run('selected.value'), null)
assert.equal(run('sceneName.value'), '场景B')
console.log('PASS: default published selection, off-page publication, restore/manual refresh, unpublished scene, first/replacement publish, scene name display, scene reset and stale initialization')

// A failed ZIP request must never be reported as a build failure: only a real backend answer can.
const zipTimeout = '请求等待超时，ZIP 构建结果尚未确认，后端可能仍在处理。请稍后重试。'
const zipPreparing = 'ZIP 正在准备，构建结果尚未确认。请稍后手动重试。'
const zipDownloadFailed = 'ZIP 下载失败，请重试'
const zipDraft = { id: 'zip-draft', sceneId: 'scene-a', published: false, currentCollectionId: 'collection-a', collectionGeneration: 3 }
const zipExportPath = '/api/v1/drafts/zip-draft/zip-exports/export-1/content'
const axiosError = (message, options = {}) => Object.assign(new Error(message), { isAxiosError: true, ...options })

async function beginZip() {
  zipPosts.length = 0
  zipGets.length = 0
  saved.length = 0
  run(`selected.value=${JSON.stringify(zipDraft)};error.value='';progressText.value='';zipPreparing.value=false`)
  const attempt = run('downloadZip()')
  await tick()
  assert.equal(zipPosts.length, 1)
  assert.equal(run('zipPreparing.value'), true)
  const post = zipPosts.shift()
  assert.equal(post.url, '/api/v1/drafts/zip-draft/zip-exports')
  // The body is built inside the VM context, so its prototype differs from a host object; compare fields.
  assert.deepEqual(Object.keys(post.body).sort(), ['collectionId', 'generation'])
  assert.equal(post.body.collectionId, 'collection-a')
  assert.equal(post.body.generation, 3)
  assert.equal(post.config.timeout, 0)
  return { attempt, post }
}

async function beginZipDownload() {
  const started = await beginZip()
  started.post.resolve({ downloadPath: zipExportPath })
  await tick()
  assert.equal(zipGets.length, 1)
  assert.equal(zipGets[0].url, zipExportPath)
  assert.equal(zipGets[0].config.responseType, 'blob')
  return { attempt: started.attempt, get: zipGets.shift() }
}

for (const [label, error] of [
  ['gateway timeout', axiosError('Request failed with status code 504', { response: { status: 504, data: '<html>504 Gateway Time-out</html>' } })],
  ['client timeout', axiosError('timeout of 0ms exceeded', { code: 'ECONNABORTED', request: {} })],
  ['interrupted connection', axiosError('Network Error', { code: 'ERR_NETWORK', request: {} })]
]) {
  const { attempt, post } = await beginZip()
  post.reject(error)
  await attempt
  assert.equal(run('error.value'), zipTimeout, label)
  assert.equal(run('progressText.value'), 'ZIP 准备结果未确认，可手动重试', label)
  assert.equal(run('zipPreparing.value'), false, label)
}

{
  const { attempt, post } = await beginZip()
  post.reject(axiosError('Request failed with status code 503', { response: { status: 503, data: { code: 'AR_503', message: 'ZIP 准备失败，请稍后重试' } } }))
  await attempt
  assert.equal(run('error.value'), 'ZIP 准备失败，请稍后重试')
  assert.equal(run('progressText.value'), 'ZIP 准备失败，可手动重试')
  assert.equal(run('zipPreparing.value'), false)
}

{
  const { attempt, post } = await beginZip()
  // The response interceptor rejects payload-level failures as plain errors, not axios errors.
  post.reject(new Error('ZIP 准备失败，请稍后重试'))
  await attempt
  assert.equal(run('error.value'), 'ZIP 准备失败，请稍后重试')
  assert.equal(run('zipPreparing.value'), false)
}

{
  const { attempt, get } = await beginZipDownload()
  get.reject(axiosError('Network Error', { code: 'ERR_NETWORK', request: {} }))
  await attempt
  assert.equal(run('error.value'), zipDownloadFailed)
  assert.equal(run('progressText.value'), 'ZIP 已准备好，下载未完成，可手动重试')
  assert.equal(run('zipPreparing.value'), false)
}

{
  const { attempt, get } = await beginZipDownload()
  get.resolve({ data: new Blob(['{"message":"ZIP 已失效，请重新准备下载"}'], { type: 'application/json' }), headers: {} })
  await attempt
  assert.equal(run('error.value'), zipDownloadFailed)
  assert.equal(run('zipPreparing.value'), false)
}

// A conflict that reports the package is still building must read as in progress, never as a failure.
{
  const { attempt, post } = await beginZip()
  post.reject(axiosError('Request failed with status code 409', { response: { status: 409, data: { code: 'AR_409', message: 'ZIP 正在准备，请稍后重试' } } }))
  await attempt
  assert.equal(run('error.value'), zipPreparing)
  assert.equal(run('progressText.value'), 'ZIP 正在准备，可稍后手动重试')
  assert.equal(run('error.value').includes('准备失败'), false)
  assert.equal(run('zipPreparing.value'), false)
}

// Other 409 conflicts, such as a changed collection, must keep their own error.
{
  const { attempt, post } = await beginZip()
  post.reject(axiosError('Request failed with status code 409', { response: { status: 409, data: { code: 'AR_409', message: '文件集合已变化，请重新获取清单' } } }))
  await attempt
  assert.equal(run('error.value'), '文件集合已变化，请重新获取清单')
  assert.notEqual(run('error.value'), zipPreparing)
  assert.equal(run('progressText.value'), 'ZIP 准备失败，可手动重试')
  assert.equal(run('zipPreparing.value'), false)
}

// Timeout, then still-building, then a completed build: the third manual retry downloads the reused ZIP.
{
  const first = await beginZip()
  first.post.reject(axiosError('Request failed with status code 504', { response: { status: 504, data: {} } }))
  await first.attempt
  assert.equal(run('error.value'), zipTimeout)
  assert.equal(run('zipPreparing.value'), false)
  const second = await beginZip()
  second.post.reject(axiosError('Request failed with status code 409', { response: { status: 409, data: { code: 'AR_409', message: 'ZIP 正在准备，请稍后重试' } } }))
  await second.attempt
  assert.equal(run('error.value'), zipPreparing)
  assert.equal(run('progressText.value'), 'ZIP 正在准备，可稍后手动重试')
  assert.equal(run('zipPreparing.value'), false)
  const third = await beginZip()
  third.post.resolve({ downloadPath: zipExportPath })
  await tick()
  assert.equal(zipGets.length, 1)
  zipGets.shift().resolve({ data: new Blob([new Uint8Array([4, 5, 6])]), headers: { 'content-disposition': 'attachment; filename=场景A.zip' } })
  await third.attempt
  assert.equal(run('error.value'), '')
  assert.equal(run('progressText.value'), 'ZIP 已开始下载')
  assert.equal(run('zipPreparing.value'), false)
  assert.deepEqual(saved.map(item => item.name), ['场景A.zip'])
}

// Manual retry after an unconfirmed result must reuse the prepared ZIP and download it.
{
  const { attempt, post } = await beginZip()
  post.reject(axiosError('Request failed with status code 504', { response: { status: 504, data: {} } }))
  await attempt
  assert.equal(run('error.value'), zipTimeout)
  const retry = await beginZip()
  retry.post.resolve({ downloadPath: zipExportPath })
  await tick()
  zipGets.shift().resolve({ data: new Blob([new Uint8Array([1, 2, 3])]), headers: { 'content-disposition': 'attachment; filename=场景A.zip' } })
  await retry.attempt
  assert.equal(run('error.value'), '')
  assert.equal(run('progressText.value'), 'ZIP 已开始下载')
  assert.equal(run('zipPreparing.value'), false)
  assert.deepEqual(saved.map(item => item.name), ['场景A.zip'])
}
console.log('PASS: ZIP prepare timeout/interruption stay unconfirmed, a still-building 409 stays in progress while other conflicts surface, backend failures surface, download failures are separate, the button recovers and retry reuses the prepared ZIP')
