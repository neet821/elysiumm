const PARTICLES = Array.from({ length: 18 }, (_, index) => ({
  delay: `${-(index % 7) * 0.9}s`,
  drift: `${18 + ((index * 17) % 54)}px`,
  duration: `${7 + (index % 6) * 1.35}s`,
  left: `${5 + ((index * 29) % 90)}%`,
  size: `${2 + (index % 4)}px`,
  top: `${8 + ((index * 37) % 84)}%`,
}))

export default function PlayerParticles({ isPlaying }) {
  return (
    <div
      className={`player-particles ${isPlaying ? 'is-playing' : 'is-paused'}`}
      role="img"
      aria-label="播放器粒子效果"
    >
      {PARTICLES.map((particle, index) => (
        <span
          key={index}
          className="player-particle"
          style={{
            '--particle-delay': particle.delay,
            '--particle-drift': particle.drift,
            '--particle-duration': particle.duration,
            '--particle-left': particle.left,
            '--particle-size': particle.size,
            '--particle-top': particle.top,
          }}
        />
      ))}
    </div>
  )
}
