import { useCallback, useEffect, useRef, useState } from 'react'

import { API_ENDPOINTS } from '../../config'
import apiClient from '../../utils/request'


const accessErrorState = (error) => {
  const detail = error?.response?.data?.detail || ''
  if (detail.includes('邀请')) return 'invite_invalid'
  if (detail.includes('登录')) return 'login_required'
  if (detail.includes('权限') || detail.includes('暂停')) return 'forbidden'
  if (error?.response?.status === 409) return 'waiting'
  return 'service_unavailable'
}

const removeInviteFromAddress = () => {
  const cleanUrl = new URL(window.location.href)
  cleanUrl.searchParams.delete('invite')
  window.history.replaceState(
    {},
    '',
    `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`,
  )
}

export default function useLiveSession() {
  const [state, setState] = useState('loading')
  const [status, setStatus] = useState(null)
  const [liveSessionId, setLiveSessionId] = useState(null)
  const [mediaUrl, setMediaUrl] = useState('')
  const [attempt, setAttempt] = useState(0)
  const mountedRef = useRef(false)
  const sessionActiveRef = useRef(false)

  const retry = useCallback(() => {
    setState('loading')
    setAttempt((value) => value + 1)
  }, [])

  useEffect(() => {
    mountedRef.current = true
    let cancelled = false
    let waitingTimer

    const connect = async () => {
      setState('loading')
      try {
        const statusResponse = await apiClient.get(API_ENDPOINTS.LIVE_STATUS, { skipAuthRedirect: true })
        if (cancelled) return
        setStatus(statusResponse.data)
        if (statusResponse.data.status !== 'live') {
          setMediaUrl('')
          setLiveSessionId(null)
          setState(statusResponse.data.status === 'ended' ? 'ended' : 'waiting')
          if (statusResponse.data.status !== 'ended') {
            waitingTimer = window.setTimeout(connect, 10_000)
          }
          return
        }

        setState('authorizing')
        const inviteToken = new URL(window.location.href).searchParams.get('invite')
        const sessionResponse = await apiClient.post(
          API_ENDPOINTS.LIVE_SESSION,
          { invite_token: inviteToken || null },
          { skipAuthRedirect: true },
        )
        if (cancelled) return
        if (inviteToken) removeInviteFromAddress()
        sessionActiveRef.current = true
        setLiveSessionId(sessionResponse.data.live_session_id ?? null)
        setMediaUrl(sessionResponse.data.media_url)
        setState('live')
      } catch (error) {
        if (!cancelled) {
          setMediaUrl('')
          setState(accessErrorState(error))
        }
      }
    }

    connect()
    return () => {
      cancelled = true
      mountedRef.current = false
      window.clearTimeout(waitingTimer)
    }
  }, [attempt])

  useEffect(() => {
    if (state !== 'live') return undefined
    const heartbeat = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        await apiClient.post(API_ENDPOINTS.LIVE_HEARTBEAT, undefined, { skipAuthRedirect: true })
      } catch (error) {
        if (!mountedRef.current) return
        const nextState = accessErrorState(error)
        if (nextState === 'service_unavailable') return
        sessionActiveRef.current = false
        setMediaUrl('')
        setLiveSessionId(null)
        setState(nextState)
      }
    }
    const timer = window.setInterval(heartbeat, 15_000)
    return () => window.clearInterval(timer)
  }, [state])

  useEffect(() => () => {
    if (!sessionActiveRef.current) return
    sessionActiveRef.current = false
    if (typeof navigator.sendBeacon === 'function') {
      navigator.sendBeacon(API_ENDPOINTS.LIVE_SESSION_END)
      return
    }
    fetch(API_ENDPOINTS.LIVE_SESSION_END, {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
    }).catch(() => {})
  }, [])

  return {
    mediaUrl,
    liveSessionId,
    retry,
    state,
    status,
  }
}
