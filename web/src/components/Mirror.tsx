import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import * as api from '@/lib/api'
import type { Frame, Mirrors, Part } from '@/lib/api'
import { cn } from '@/lib/utils'

/* What the person reads while the agent writes English.
 *
 * Two panes, because prose and code want opposite widths: Korean prose is
 * unreadable without a measure, commands and patches are unreadable once they
 * wrap. One column loses both ways. The left one is bounded, the right is not.
 *
 * The values live in `DESIGN.md` at the repo root. */

const SELF = '▶'
const DID = '·'
const CODE = '$'
const SEEN = '──'

export function Mirror() {
  const [where, setWhere] = useState<Mirrors | null>(null)
  const [here, setHere] = useState({ host: 'claude', project: '' })
  const [parts, setParts] = useState<Part[]>([])
  const [live, setLive] = useState(false)
  const [fault, setFault] = useState('')
  // The generation this screen is showing. A different number from the server
  // means the repository changed, and everything held here belongs to the old
  // one.
  const gen = useRef(-1)
  // The last index taken. A dropped connection is reconnected below, and the
  // server starts every connection replaying from the top of the feed, so
  // without this the whole visible session arrives a second time — and again
  // on every reconnect after that. The index is the server's own absolute
  // one, which is why `Feed` carries it.
  const mark = useRef(-1)

  useEffect(() => {
    api.getMirrors().then(setWhere).catch(() => setFault('저장소 목록을 못 읽었다'))
  }, [])

  useEffect(() => {
    const stop = new AbortController()
    let alive = true
    const run = async () => {
      while (alive) {
        try {
          setFault('')
          await api.mirrorStream((frame) => {
            setLive(true)
            take(frame)
          }, stop.signal)
        } catch {
          if (!alive) return
          setLive(false)
        }
        if (!alive) return
        // Reconnect. A quiet mirror and a dead one are different things, and a
        // screen that needs a manual refresh to come back is a screen nobody
        // keeps open.
        await new Promise((go) => setTimeout(go, 1000))
      }
    }

    const take = (frame: Frame) => {
      if (frame.gen !== gen.current) {
        gen.current = frame.gen
        mark.current = -1
        setParts([])
      }
      setHere({ host: frame.host, project: frame.project })
      const fresh = frame.parts.filter((part) => part.i > mark.current)
      if (fresh.length) {
        mark.current = fresh[fresh.length - 1].i
        setParts((prev) => prev.concat(fresh))
      }
    }

    void run()
    return () => {
      alive = false
      stop.abort()
    }
  }, [])

  const [said, ran] = useMemo(() => {
    const left: Part[] = []
    const right: Part[] = []
    for (const part of parts) (part.mark === CODE ? right : left).push(part)
    return [left, right]
  }, [parts])

  // A new line never drags the screen. The one case that moves it is a reader
  // already at that pane's bottom, which is why there is no follow toggle and
  // no jump pill: the same question is already answered.
  const flow = useStick(said.length)
  const code = useStick(ran.length)

  const repos = where?.hosts[here.host] ?? []

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-card px-6 py-2.5">
        <Select
          value={here.host}
          onValueChange={(host) => host && switchTo(host, firstOf(where, host), setFault)}
        >
          <SelectTrigger size="sm" className="w-28 bg-background text-[12.5px]">
            <SelectValue>{here.host}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.keys(where?.hosts ?? {}).map((host) => (
              <SelectItem key={host} value={host}>
                {host}
                <span className="ml-1.5 text-[10.5px] text-faint">
                  저장소 {where?.hosts[host].length ?? 0}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={here.project}
          onValueChange={(path) => path && switchTo(here.host, path, setFault)}
        >
          <SelectTrigger size="sm" className="w-80 bg-background text-[12.5px]">
            <SelectValue>
              <span className="font-mono text-[12px]">
                {repos.find((r) => r.path === here.project)?.name ?? '…'}
              </span>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {repos.map((repo) => (
              <SelectItem key={repo.path} value={repo.path}>
                <span className="font-mono text-[12px]">{repo.name}</span>
                <span className="ml-1.5 text-[10.5px] text-faint">{repo.path}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <span className={cn('size-1.5 rounded-full', live ? 'bg-primary' : 'bg-border')} />
          {live ? '연결됨' : '끊김 · 다시 붙는 중'}
        </span>

        {fault && <span role="status" className="text-[11.5px] text-destructive">{fault}</span>}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(22rem,40rem)_minmax(0,1fr)]">
        <div ref={flow} className="min-h-0 min-w-0 overflow-y-auto px-5 pt-4 pb-16">
          <Tag>대화</Tag>
          {said.length === 0 ? (
            <Empty title="아직 아무 말도 없다.">
              작업 셀에서 한 번 말을 걸면 여기 한국어로 뜬다.
            </Empty>
          ) : (
            said.map((part, n) => <Row key={part.i} part={part} before={said[n - 1]} />)
          )}
        </div>

        <div
          ref={code}
          className="min-h-0 min-w-0 overflow-y-auto border-t border-border bg-secondary/40 px-5 pt-4 pb-16 lg:border-t-0 lg:border-l"
        >
          <Tag>명령과 수정</Tag>
          {ran.length === 0 ? (
            <Empty title="아직 실행한 것이 없다.">
              명령과 패치는 번역 없이 그대로 여기 쌓인다.
            </Empty>
          ) : (
            ran.map((part, n) => <Block key={part.i} part={part} before={ran[n - 1]} />)
          )}
        </div>
      </div>
    </div>
  )
}

/** Pin a pane to its bottom, but only if it was already there.
 *
 *  It returns the ref rather than taking one. Taking one makes the hook write
 *  through a value its caller owns and may swap at any time. */
function useStick(count: number) {
  const pane = useRef<HTMLDivElement>(null)
  const bottomed = useRef(true)
  useEffect(() => {
    const el = pane.current
    if (!el) return
    const watch = () => {
      bottomed.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 48
    }
    el.addEventListener('scroll', watch, { passive: true })
    return () => el.removeEventListener('scroll', watch)
  }, [])
  useEffect(() => {
    const el = pane.current
    if (el && bottomed.current) el.scrollTop = el.scrollHeight
  }, [count])
  return pane
}

const firstOf = (where: Mirrors | null, host: string) =>
  where?.hosts[host]?.[0]?.path ?? ''

function switchTo(host: string, project: string, onFault: (text: string) => void) {
  if (!project) {
    onFault(`${host} 로 연 세션이 아직 없다`)
    return
  }
  api.pointMirror(host, project).catch(() => onFault('저장소를 못 바꿨다'))
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="sticky -top-4 z-10 -mx-5 mb-3 border-b border-border bg-inherit px-5 py-2 font-heading text-[11px] font-semibold tracking-wider text-faint">
      {children}
    </h2>
  )
}

function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <p className="mt-24 text-center text-[13.5px] text-faint">
      <b className="block font-medium text-muted-foreground">{title}</b>
      {children}
    </p>
  )
}

/** The clock prints only when the minute changes. Twenty of the same is noise. */
const when = (part: Part, before?: Part) =>
  part.at && part.at !== before?.at ? part.at : ''

/** One row of the conversation pane. The two left columns are fixed width, so
 *  nothing shifts however many lines the body runs to. */
function Row({ part, before }: { part: Part; before?: Part }) {
  if (part.mark === SEEN) {
    return (
      <div className="my-6 flex items-center gap-3 font-mono text-[11px] text-faint">
        <span className="h-px flex-1 bg-border" />
        {part.text}
        <span className="h-px flex-1 bg-border" />
      </div>
    )
  }

  const self = part.mark === SELF
  const did = part.mark === DID
  return (
    <div className={cn('grid grid-cols-[3.25rem_1.5rem_minmax(0,1fr)] gap-x-2.5', did ? 'py-px' : 'py-0.5')}>
      <time className="pt-1.5 text-right font-mono text-[11px] leading-relaxed text-faint">
        {when(part, before)}
      </time>
      <span className="relative pt-1.5 text-[11px] font-semibold leading-relaxed tracking-wide text-primary">
        {self ? '나' : null}
        {/* The rail draws where a turn starts and ends. A person's row stands
            a word there instead, so the turn breaks at that line. */}
        {!self && <span className="absolute inset-y-[-2px] left-0.5 w-0.5 rounded-full bg-border" />}
      </span>
      <div
        className={cn(
          'min-w-0 break-words',
          did && 'pl-3.5 -indent-3.5 text-[13px] leading-relaxed text-faint',
          self && 'font-medium',
          !did && !self && 'text-[16px]',
        )}
      >
        {did ? `· ${part.text}` : <Prose text={part.text} />}
      </div>
    </div>
  )
}

/** One block of the command pane. Nothing here went through the translator. */
function Block({ part, before }: { part: Part; before?: Part }) {
  const lines = part.text.split('\n')
  const isDiff = lines.some((l) => l.startsWith('+') || l.startsWith('-'))
  return (
    <div className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-2.5 pb-3">
      <time className="pt-1 text-right font-mono text-[11px] leading-relaxed text-faint">
        {when(part, before)}
      </time>
      <div className="min-w-0">
        {part.name && (
          <span className="mb-1 inline-block rounded-sm bg-secondary px-1.5 py-px font-mono text-[11px] text-muted-foreground">
            {part.name}
          </span>
        )}
        <pre className="max-h-[60vh] overflow-auto rounded-md border border-border bg-card px-3.5 py-2.5 font-mono text-[13px] leading-relaxed text-muted-foreground">
          {isDiff
            ? lines.map((line, n) => (
                <span
                  key={n}
                  className={cn(
                    line.startsWith('+') && 'text-added',
                    line.startsWith('-') && 'text-destructive',
                  )}
                >
                  {line + '\n'}
                </span>
              ))
            : part.text}
        </pre>
      </div>
    </div>
  )
}

/* The agent writes Markdown. Printed raw, the `**` and the fences arrive as
   characters and the page reads as a log dump. Only what shows up is carried. */
const FENCE = /^```/
const TABLE = /^\s*\|/
const HEAD = /^#{1,6}\s/
const ITEM = /^\s*[-*]\s/

function Prose({ text }: { text: string }) {
  const blocks = useMemo(() => chop(text), [text])
  return (
    <>
      {blocks.map((block, n) => {
        if (block.kind === 'pre') {
          return (
            <pre
              key={n}
              className="mt-3 overflow-x-auto rounded-md bg-secondary px-3.5 py-2.5 font-mono text-[13px] leading-relaxed text-muted-foreground"
            >
              {block.body}
            </pre>
          )
        }
        if (block.kind === 'head') {
          return (
            <h3 key={n} className="mt-5 font-heading text-[15px] font-semibold first:mt-0">
              <Inline text={block.body} />
            </h3>
          )
        }
        if (block.kind === 'list') {
          return (
            <ul key={n} className="mt-2.5 list-disc pl-5">
              {block.body.split('\n').map((item, k) => (
                <li key={k} className="mt-0.5">
                  <Inline text={item} />
                </li>
              ))}
            </ul>
          )
        }
        return (
          <p key={n} className="mt-3 whitespace-pre-wrap first:mt-0">
            <Inline text={block.body} />
          </p>
        )
      })}
    </>
  )
}

type Block = { kind: 'p' | 'pre' | 'head' | 'list'; body: string }

function chop(text: string): Block[] {
  const lines = text.split('\n')
  const out: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (FENCE.test(line)) {
      const body: string[] = []
      i += 1
      while (i < lines.length && !FENCE.test(lines[i])) body.push(lines[i++])
      i += 1
      out.push({ kind: 'pre', body: body.join('\n') })
    } else if (TABLE.test(line)) {
      // In a table the alignment is the meaning. Leaving it monospaced keeps
      // more of it than rebuilding it as a real table would.
      const body: string[] = []
      while (i < lines.length && TABLE.test(lines[i])) body.push(lines[i++])
      out.push({ kind: 'pre', body: body.join('\n') })
    } else if (HEAD.test(line)) {
      out.push({ kind: 'head', body: line.replace(HEAD, '') })
      i += 1
    } else if (ITEM.test(line)) {
      const body: string[] = []
      while (i < lines.length && ITEM.test(lines[i])) body.push(lines[i++].replace(ITEM, ''))
      out.push({ kind: 'list', body: body.join('\n') })
    } else if (!line.trim()) {
      i += 1
    } else {
      const body: string[] = []
      while (
        i < lines.length &&
        lines[i].trim() &&
        !FENCE.test(lines[i]) &&
        !TABLE.test(lines[i]) &&
        !HEAD.test(lines[i])
      )
        body.push(lines[i++])
      out.push({ kind: 'p', body: body.join('\n') })
    }
  }
  return out
}

/** Backticks and bold only, emitted as nodes so no `dangerouslySetInnerHTML`. */
function Inline({ text }: { text: string }) {
  const bits = useMemo(() => text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g), [text])
  return (
    <>
      {bits.map((bit, n) => {
        if (bit.startsWith('`') && bit.endsWith('`') && bit.length > 2) {
          return (
            <code key={n} className="rounded-sm bg-secondary px-1 py-px font-mono text-[0.875em]">
              {bit.slice(1, -1)}
            </code>
          )
        }
        if (bit.startsWith('**') && bit.endsWith('**') && bit.length > 4) {
          return (
            <strong key={n} className="font-semibold">
              {bit.slice(2, -2)}
            </strong>
          )
        }
        return <span key={n}>{bit}</span>
      })}
    </>
  )
}
