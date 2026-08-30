import { TRANSFER_PUBLIC_BASE_URL } from '../config.js'

export const TRANSFER_CURRENT_TOKEN_KEY = 'transfer_current_token'

export const transferPublicUrl = (token) => `${TRANSFER_PUBLIC_BASE_URL}/${token}`

export const formatTransferDate = (value) => value
  ? new Date(value).toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })
  : ''
