import { Clock3, LogIn, Radio, RefreshCw, ShieldCheck } from 'lucide-react'

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
      <p className="live-state__eyebrow">Blue Album Live</p>
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


export default function LivePage() {
  const { mediaUrl, retry, state, status } = useLiveSession()
  const isLoading = state === 'loading' || state === 'authorizing'
  const isLive = state === 'live' && mediaUrl
  const latencyText = (
    status?.latency_mode === 'ultra_low'
      ? '画面延迟目标约 2–4 秒，网络波动时可能短暂增加。'
      : status?.latency_mode === 'low'
        ? '画面延迟目标约 4–8 秒，取决于当前网络。'
        : '画面延迟约 5–10 秒，取决于当前网络。'
  )

  return (
    <div className="live-page">
      <header
        className="live-hero"
        style={status?.cover_url ? { '--live-cover': `url("${status.cover_url}")` } : undefined}
      >
        <div>
          <p className="live-hero__eyebrow">
            <Radio aria-hidden="true" />
            {isLive ? '正在直播' : 'Blue Album Live'}
          </p>
          <h1>{status?.title || 'Blue Album 直播'}</h1>
          {status?.description ? <p>{status.description}</p> : null}
        </div>
      </header>

      <div className="live-page__content">
        {isLoading && (
          <section className="live-state" role="status" aria-live="polite">
            <span className="live-state__pulse" aria-hidden="true" />
            <p>正在连接直播间…</p>
          </section>
        )}
        {isLive && (
          <>
            <LivePlayer mediaUrl={mediaUrl} />
            <div className="live-presence">
              <span><span aria-hidden="true" />直播中</span>
              <p>{latencyText}</p>
            </div>
            <LiveMessageBoard />
          </>
        )}
        {!isLoading && !isLive && <StatePanel state={state} retry={retry} />}
      </div>
    </div>
  )
}
