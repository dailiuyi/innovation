// 对应 SceneService / DraftService 写入 ar_audit 的动作；仅转换展示文案。
const auditActionLabels = Object.freeze({
  CREATE: '创建场景',
  UPDATE: '编辑场景',
  DELETE: '删除场景',
  SET_ENABLED: '设置场景启用状态',
  DRAFT_CREATE: '创建草稿',
  DRAFT_EDIT: '编辑草稿说明',
  DRAFT_DELETE_REQUEST: '请求删除草稿',
  DRAFT_DELETE: '删除草稿',
  DRAFT_PUBLISH: '发布草稿',
  FILE_REGISTER: '登记文件',
  FILE_UPLOAD_START: '开始上传文件',
  FILE_AVAILABLE: '文件可用',
  FILE_FAILED: '文件入库失败',
  FILE_RECONCILE: '文件启动对账',
  FILE_DELETE_REQUEST: '请求删除文件',
  FILE_DELETE_RETRY: '重试删除文件',
  FILE_DELETE_FAILED: '文件删除失败',
  FILE_DELETE: '删除文件',
  COLLECTION_REPLACE_START: '开始替换文件集合',
  COLLECTION_REPLACE_CANCEL: '取消替换文件集合',
  COLLECTION_REPLACE_SWITCH: '文件集合替换生效'
})

export function auditActionLabel(action) {
  return Object.prototype.hasOwnProperty.call(auditActionLabels, action)
    ? auditActionLabels[action]
    : action
}
