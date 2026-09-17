import { useCallback, useEffect, useRef, useState } from 'react'
import { ChannelRail } from '@/components/ChannelRail'
import { Composer } from '@/components/Composer'
import { Handoff } from '@/components/Handoff'
import { Peek } from '@/components/Peek'
import { Stream } from '@/components/Stream'
import { Toolbar } from '@/components/Toolbar'
import { WikiMap } from '@/components/WikiMap'
import * as api from '@/lib/api'
import type { Channel, Kind, Options, Peek as PeekData, Tokens } from '@/lib/api'

export type Msg = {
  role: 'user' | 'assistant'
  text: string
  tools: string[]
  hits?: string[]
  source?: string
  ms?: number
  cost?: number
  tokens?: Tokens
  model?: string
  sessionId?: string
  marked?: Kind
  error?: string
  pending?: boolean
  simpleText?: string
  simpleError?: string
  simplePending?: boolean
  simpleMs?: number
  simpleCost?: number
}

export const MAP = '__map__' // 채널이 아니라 위키 지도 탭

export default function App() {
  const [channels, setChannels] = useState<Channel[]>([])
  const [options, setOptions] = useState<Options | null>(null)
  const [active, setActive] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [legacy, setLegacy] = useState<api.Turn[]>([])
  const [configuring, setConfiguring] = useState(false)
  const selectedRepo = channels[0]?.repo ?? ''
  // 답하는 중인 채널. 전역 불리언이면 한 채널이 답하는 동안 다른 채널도
  // 막힌다 — 채널이 독립이라는 약속이 깨진다. 실제로 #위키 입력창이 막혔다.
  const [busyOn, setBusyOn] = useState<string[]>([])
  const activeRef = useRef('')
  const inFlight = useRef(new Map<string, Msg>())
  activeRef.current = active
  const [fault, setFault] = useState('')
  const [note, setNote] = useState('')
  const [handoff, setHandoff] = useState('')
  const [peek, setPeek] = useState<{ data: PeekData | null; error?: string } | null>(null)

  useEffect(() => {
    Promise.all([api.getChannels(), api.getOptions()])
      .then(([list, opts]) => {
        setChannels(list)
        setOptions(opts)
        setActive((prev) => prev || list[0]?.id || '')
      })
      .catch(() => setFault('서버가 안 뜬 것 같다 — tool\\chat.cmd'))
  }, [])

  // 채널을 바꾸면 그 채널의 기록을 되살린다. 프로세스는 서버가 들고 있으므로
  // 화면이 기억할 것은 없다.
  //
  // 두 겹으로 막는다. 채널을 또 바꿨으면 버리고(`stale`), 기록이 오는 사이에
  // 사용자가 이미 뭔가 쳤으면 덮지 않는다. 채널을 바꾸자마자 보내면 방금 친
  // 말이 빈 기록에 지워졌다 — 실제로 한 번 사라졌다.
  useEffect(() => {
    if (!active || active === MAP) return
    let stale = false
    setMessages([])
    setLegacy([])
    setNote('')
    setHandoff('')
    setPeek(null)
    api
      .getLog(active)
      .then((rows) => {
        if (stale) return
        const restored: Msg[] = rows.map((r) => ({ role: r.role, text: r.text, tools: [], source: r.source, error: r.error,
          ms: r.ms, cost: r.cost_usd, model: r.model, sessionId: r.session_id, tokens: r.tokens,
          simpleText: r.simple_text, simpleError: r.simple_error,
          simpleMs: r.simple_meta?.ms, simpleCost: r.simple_meta?.cost_usd }))
        const live = inFlight.current.get(active)
        if (live && restored.at(-1)?.role === 'user') restored.push(live)
        setMessages((prev) =>
          prev.length
            ? prev
            : restored,
        )
      })
      .catch(() => !stale && setFault('기록을 못 읽었다'))
    api.getLog(active, true).then((rows) => !stale && setLegacy(rows))
      .catch(() => !stale && setFault('이전 기록을 못 읽었다'))
    return () => {
      stale = true
    }
  }, [active, selectedRepo])

  const send = useCallback(
    async (text: string) => {
      const cid = active
      const placeholder: Msg = { role: 'assistant', text: '', tools: [], pending: true }
      inFlight.current.set(cid, placeholder)
      setBusyOn((prev) => [...prev, cid])
      setFault('')
      setMessages((prev) => [
        ...prev,
        { role: 'user', text, tools: [] },
        placeholder,
      ])

      // 스트림 중에 채널을 바꾸면 화면의 목록은 다른 채널 것이다. 그 위에 토막을
      // 붙이면 남의 대화가 망가진다. 서버가 기록하니 돌아오면 되살아난다.
      const patch = (fn: (m: Msg) => Msg) => {
        const previous = inFlight.current.get(cid)!
        const nextMessage = fn(previous)
        inFlight.current.set(cid, nextMessage)
        setMessages((prev) => {
          if (activeRef.current !== cid || prev.at(-1) !== previous) return prev
          const next = [...prev]
          next[next.length - 1] = nextMessage
          return next
        })
      }

      try {
        await api.say(cid, text, (ev) => {
          if (ev.kind === 'hits') {
            patch((m) => ({ ...m, hits: ev.pages ?? [] }))
          } else if (ev.kind === 'delta') {
            patch((m) => ({ ...m, text: m.text + ev.text }))
          } else if (ev.kind === 'tool') {
            patch((m) => ({ ...m, tools: [...m.tools, ev.text] }))
          } else if (ev.kind === 'done') {
            // 마지막 본문은 서버가 든 것을 쓴다. 토막을 놓쳤어도 여기서 맞는다.
            patch((m) => ({
              ...m,
              text: ev.text || m.text,
              ms: ev.ms,
              cost: ev.cost_usd,
              tokens: ev.tokens,
              model: ev.model,
              sessionId: ev.session_id,
              pending: false,
            }))
          } else if (ev.kind === 'error') {
            patch((m) => ({ ...m, error: ev.text, pending: false }))
          } else if (ev.kind === 'simple_start') {
            patch((m) => ({ ...m, simpleText: '', simplePending: true }))
          } else if (ev.kind === 'simple_delta') {
            patch((m) => ({ ...m, simpleText: (m.simpleText ?? '') + ev.text }))
          } else if (ev.kind === 'simple_done') {
            patch((m) => ({ ...m, simpleText: ev.text, simplePending: false, simpleMs: ev.ms, simpleCost: ev.cost_usd }))
          } else if (ev.kind === 'simple_error') {
            patch((m) => ({ ...m, simpleText: '', simpleError: ev.text, simplePending: false }))
          }
        })
      } catch (err) {
        patch((m) => m.simplePending
          ? ({ ...m, simpleText: '', simpleError: String(err), simplePending: false })
          : ({ ...m, error: String(err), pending: false }))
      } finally {
        inFlight.current.delete(cid)
        setBusyOn((prev) => prev.filter((id) => id !== cid))
        api.getChannels().then(setChannels).catch(() => {})
      }
    },
    [active],
  )

  // 프로젝트를 바꾸면 해당 프로젝트의 기록과 문맥을 다시 선택한다.
  const apply = useCallback(
    async (cfg: { repo: string; model: string; effort: string }) => {
      setFault('')
      setConfiguring(true)
      try {
        const { kept, switched } = await api.setConfig(active, cfg)
        setChannels(await api.getChannels())
        if (switched) {
          setMessages([])
        } else if (!kept) {
          setMessages([])
          setNote('Claude/Codex를 바꿔 새 대화를 시작했다. 지난 기록은 그대로 남아 있다.')
        } else {
          setNote('다음 발화부터 적용된다. 지금까지 한 대화는 이어진다.')
        }
      } catch (err) {
        setFault(String(err))
      } finally {
        setConfiguring(false)
      }
    },
    [active],
  )

  const wipe = useCallback(async () => {
    await api.reset(active)
    setMessages([])
    setNote('')
    api.getChannels().then(setChannels).catch(() => {})
  }, [active])

  // 어긋났다 — 그 답의 바로 앞 발화와 함께 census 형식으로 쌓는다.
  const markTurn = useCallback(
    async (index: number, kind: Kind) => {
      const answer = messages[index]
      const question = [...messages.slice(0, index)].reverse().find((m) => m.role === 'user')
      await api.mark(active, {
        kind,
        user_text: question?.text ?? '',
        assistant_text: answer?.text ?? '',
        session_id: answer?.sessionId,
      })
      setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, marked: kind } : m)))
    },
    [active, messages],
  )

  const askHandoff = useCallback(async () => {
    setFault('')
    try {
      setHandoff((await api.handoff(active)).text)
    } catch (err) {
      setFault(String(err))
    }
  }, [active])

  const here = channels.find((c) => c.id === active)
  const busy = busyOn.includes(active) || configuring

  const showPeek = useCallback(
    async (path: string, line: number) => {
      if (!here) return
      setPeek({ data: null })
      try {
        setPeek({ data: await api.peek(here.repo, path, line) })
      } catch (err) {
        setPeek({ data: null, error: String(err) })
      }
    },
    [here],
  )

  const decideOne = useCallback(
    async (candidate: string, target: 'wiki' | 'claude_md' | 'drop') => {
      const r = await api.decide(active, candidate, target)
      const changed = r.changed?.trim() ? `\n\n바뀐 것:\n${r.changed.trim()}` : ''
      const cost = r.cost_usd != null ? `\n\n$${r.cost_usd.toFixed(3)}` : ''
      return (r.error ? '실패 — ' : '') + r.text + changed + cost
    },
    [active],
  )

  return (
    <div className="flex h-screen">
      <ChannelRail
        channels={channels}
        active={active}
        busy={busy}
        onPick={setActive}
        onReset={wipe}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {active === MAP ? (
          /* 오래 `/wiki.html` 을 iframe 으로 띄웠다. 이제 같은 그래프를 여기서
             직접 그린다 — 파이썬이 HTML 을 만들고 그것을 다시 감싸던 겹이 빠진다. */
          <div className="h-full overflow-auto"><WikiMap /></div>
        ) : (
          <>
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-3">
              <div>
                <h1 className="font-heading text-[16px] font-semibold leading-tight">
                  #{here?.label ?? '…'}
                </h1>
                <p className="text-[12px] text-muted-foreground">
                  {here?.blurb ?? ''}
                  {here?.model_name && (
                    <span className="ml-2 font-mono text-[10.5px] text-faint">
                      {here.model_name.replace('claude-', '')}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {here && (
                  <Toolbar channel={here} options={options} busy={busy}
                    projectBusy={busyOn.length > 0 || configuring} onChange={apply} />
                )}
                <button
                  type="button"
                  onClick={askHandoff}
                  disabled={!here}
                  className="rounded-md border border-border bg-background px-2.5 py-1 text-[12px] hover:bg-secondary disabled:opacity-40"
                  title="다음 세션에 붙일 프롬프트를 만든다"
                >
                  인계
                </button>
              </div>
            </header>

            {fault && (
              <div className="border-b border-destructive/30 bg-destructive/10 px-6 py-2 text-[12.5px] text-destructive">
                {fault}
              </div>
            )}
            {note && (
              <div className="border-b border-border bg-secondary px-6 py-2 text-[12.5px] text-muted-foreground">
                {note}
              </div>
            )}
            {handoff && <Handoff text={handoff} onClose={() => setHandoff('')} />}
            {legacy.length > 0 && (
              <details key={active} className="max-h-64 overflow-auto border-b border-border px-6 py-2 text-xs">
                <summary className="cursor-pointer">프로젝트 미분류 이전 기록 ({legacy.length}개)</summary>
                <p className="my-2 text-muted-foreground">예전 기록에는 프로젝트가 저장되지 않았습니다. 현재 프로젝트의 기록으로 간주하지 않습니다.</p>
                {legacy.map((row, i) => <pre key={i} className="my-3 whitespace-pre-wrap">{row.role === 'user' ? '나' : '답'}: {row.text}</pre>)}
              </details>
            )}

            <div className="flex min-h-0 flex-1">
              <div className="flex min-w-0 flex-1 flex-col">
                <Stream
                  messages={messages}
                  remote={here?.remote ?? ''}
                  onPeek={showPeek}
                  onDecide={active === 'retro' ? decideOne : undefined}
                  onMark={markTurn}
                />
                <Composer busy={busy} onSend={send} />
              </div>
              {peek && (
                <Peek data={peek.data} error={peek.error} onClose={() => setPeek(null)} />
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
