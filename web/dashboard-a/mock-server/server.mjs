import { randomUUID } from 'node:crypto'
import { WebSocketServer } from 'ws'
import { makeCallEnded, makeRiskUpdate, makeSessionStart } from './messageFactory.mjs'
import { DEFAULT_SCENARIO, scenarios } from './scenarios.mjs'

function parseArgs(argv) {
  const args = { port: 8787, scenario: DEFAULT_SCENARIO, tickMs: 1000, dump: null }
  for (const arg of argv) {
    const [key, value] = arg.replace(/^--/, '').split('=')
    if (key === 'port') args.port = Number(value)
    if (key === 'scenario') args.scenario = value
    if (key === 'tick-ms') args.tickMs = Number(value)
    if (key === 'dump') args.dump = value
  }
  return args
}

const args = parseArgs(process.argv.slice(2))

if (args.dump) {
  const streamId = randomUUID()
  const callId = randomUUID()
  const samples = {
    session_start: makeSessionStart({ streamId, callId, protectedNumber: '+91XXXXXXXXXX' }),
    risk_update: makeRiskUpdate({
      streamId,
      callId,
      sequence: 1,
      score: 42,
      verdict: 'unknown',
      confidence: 0.5,
      reasons: ['insufficient_audio'],
      contributingChecks: ['machine_fingerprint'],
      degradedChecks: [],
    }),
    call_ended: makeCallEnded({
      streamId,
      callId,
      durationSeconds: 30,
      finalScore: 42,
      finalVerdict: 'unknown',
      reasons: [],
      raiseAlert: false,
    }),
  }
  const sample = samples[args.dump]
  if (!sample) {
    console.error(`Unknown --dump target "${args.dump}". Expected one of: ${Object.keys(samples).join(', ')}`)
    process.exit(1)
  }
  console.log(JSON.stringify(sample))
  process.exit(0)
}

const scenario = scenarios[args.scenario]
if (!scenario) {
  console.error(`Unknown scenario "${args.scenario}". Expected one of: ${Object.keys(scenarios).join(', ')}`)
  process.exit(1)
}

const wss = new WebSocketServer({ port: args.port })
console.log(`Mock SatyaCheck WebSocket server listening on ws://localhost:${args.port} (scenario: ${args.scenario})`)

wss.on('connection', (socket) => {
  const streamId = randomUUID()
  const callId = randomUUID()
  let sequence = 0
  console.log(`Client connected. stream_id=${streamId}`)

  socket.send(JSON.stringify(makeSessionStart({ streamId, callId, protectedNumber: '+91XXXXXXXXXX' })))

  const tickInterval = setInterval(() => {
    if (sequence >= scenario.ticks.length) {
      clearInterval(tickInterval)
      const durationSeconds = scenario.ticks.length * (args.tickMs / 1000)
      const lastTick = scenario.ticks[scenario.ticks.length - 1]
      socket.send(
        JSON.stringify(
          makeCallEnded({
            streamId,
            callId,
            durationSeconds,
            finalScore: scenario.finalScore,
            finalVerdict: scenario.finalVerdict,
            reasons: lastTick ? lastTick.reasons : [],
            raiseAlert: scenario.raiseAlert,
          }),
        ),
      )
      return
    }
    const t = scenario.ticks[sequence]
    sequence += 1
    socket.send(
      JSON.stringify(
        makeRiskUpdate({
          streamId,
          callId,
          sequence,
          score: t.score,
          verdict: t.verdict,
          confidence: t.confidence,
          reasons: t.reasons,
          contributingChecks: t.contributing,
          degradedChecks: t.degraded,
        }),
      ),
    )
  }, args.tickMs)

  socket.on('close', () => {
    clearInterval(tickInterval)
    console.log(`Client disconnected. stream_id=${streamId}`)
  })
})
