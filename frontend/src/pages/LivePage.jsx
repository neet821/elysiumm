import { Clock3, LogIn, RefreshCw, ShieldCheck } from 'lucide-react'

import LiveMessageBoard from '../features/live/LiveMessageBoard'
import LivePlayer from '../features/live/LivePlayer'
import useLiveSession from '../features/live/useLiveSession'


const stateMessages = {
  waiting: {
    title: '等待开播',
    description: '主播上线后，画面会自动出现在这里。',
  },
  ended: {
    title: '直播已结束',
    description: '感谢观看，下一次开播时这里会出现新的画面。',
  },
  invite_invalid: {
    title: '邀请链接已失效',
    description: '请向直播间管理员获取新的邀请链接。',
  },
  login_required: {
    title: '登录后即可观看',
    description: '这个直播间只向指定用户开放。',
  },
  forbidden: {
    title: '你没有观看权限',
    description: '当前直播间没有向这个账号开放。',
  },
  service_unavailable: {
    title: '直播服务暂时不可用',
    description: '连接没有建立，请稍后再试。',
  },
}


function StatePanel({ state, retry }) {
  const message = stateMessages[state]
  if (!message) return null
  const isWaiting = state === 'waiting'
  const isEnded = state === 'ended'
  const isLogin = state === 'login_required'
  return (
    <section className="live-state" role={isWaiting || isEnded ? 'status' : 'alert'}>
      <span className="live-state__icon" aria-hidden="true">
        {isWaiting ? <Clock3 /> : <ShieldCheck />}
      </span>
      <p className="live-state__eyebrow">直播</p>
      <h2>{message.title}</h2>
      <p>{message.description}</p>
      {isEnded ? null : isLogin ? (
        <a className="live-state__action" href={`/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`}>
          <LogIn aria-hidden="true" />
          前往登录
        </a>
      ) : (
        <button className="live-state__action" type="button" onClick={retry}>
          <RefreshCw aria-hidden="true" />
          {isWaiting ? '立即检查' : '重新连接'}
        </button>
      )}
    </section>
  )
}


function MinimalWatchPage({ isLoading, isLive, liveSessionId, mediaUrl, retry, showMessages, state, status }) {
  if (isLoading) {
    return <main className="live-watch-page"><div className="live-watch-page__status" role="status">正在连接直播间…</div></main>
  }

  if (!isLive && !['waiting', 'ended'].includes(state)) {
    return <main className="live-watch-page"><StatePanel state={state} retry={retry} /></main>
  }

  if (isLive) {
    return (
      <main className="live-watch-page">
        {status?.title && <h1 className="live-watch-page__title">{status.title}</h1>}
        <LivePlayer mediaUrl={mediaUrl} minimal onRefresh={retry} />
        {showMessages && <LiveMessageBoard liveSessionId={liveSessionId} />}
      </main>
    )
  }

  return (
    <main className="live-watch-page">
      <p className="live-watch-page__empty-prompt" role="status">未开播</p>
      <LivePlayer mediaUrl="" minimal onRefresh={retry} />
    </main>
  )
}

function PublicLivePage({ showMessages = true }) {
  const { liveSessionId, mediaUrl, retry, state, status } = useLiveSession()
  const isLoading = state === 'loading' || state === 'authorizing'
  const isLive = state === 'live' && mediaUrl
  return <MinimalWatchPage isLoading={isLoading} isLive={isLive} liveSessionId={liveSessionId} mediaUrl={mediaUrl} retry={retry} showMessages={showMessages} state={state} status={status} />
}

export default function LivePage() {
  const isWatchPage = new URLSearchParams(window.location.search).get('watch') === '1'
  return <PublicLivePage showMessages={!isWatchPage} />
}
