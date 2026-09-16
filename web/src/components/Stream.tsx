import { useEffect, useRef, useState } from 'react'
import { Answer } from '@/components/Answer'
import type { AnswerProps } from '@/components/Answer'
import { KINDS } from '@/lib/api'
import type { Kind } from '@/lib/api'
import type { Msg } from '@/App'

type Props = {
  messages: Msg[]
  remote: string
  onPeek: AnswerProps['onPeek']
  onDecide: AnswerProps['onDecide']
  onMark: (index: number, kind: Kind) => Promise<void>
}

export function Stream({ messages, remote, onPeek, onDecide, onMark }: Props) {
  const end = useRef<HTMLDivElement>(null)

  // 답이 토막으로 자라므로 길이가 바뀔 때마다 따라 내려간다.
  const grown = messages.length + (messages.at(-1)?.text.length ?? 0) + (messages.at(-1)?.simpleText?.length ?? 0)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [grown])

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        {messages.length === 0 && (
          <p className="text-[13px] text-faint">
            프로젝트와 모델을 고르고 질문하세요. 답변의 근거를 확인하거나,
            같은 내용을 쉬운 설명으로 바꿔 볼 수 있습니다.
          </p>
        )}

        <div className="space-y-6">
          {messages.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] rounded-lg rounded-br-sm bg-secondary px-3.5 py-2 text-[13.5px] leading-relaxed whitespace-pre-wrap">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={i} className="space-y-2">
                {m.source && (
                  <span className="inline-block rounded bg-secondary px-1.5 py-0.5 font-heading text-[10.5px] text-muted-foreground">
                    {m.source === 'standup' ? '아침 브리핑' : m.source === 'retro' ? '금요 회고' : m.source}
                  </span>
                )}
                {m.hits && m.hits.length > 0 && (
                  <div className="font-mono text-[10.5px] leading-snug text-primary/80">
                    관련 규칙 · {m.hits.join(' · ')}
                  </div>
                )}
                {m.tools.length > 0 && (
                  <ul className="space-y-0.5">
                    {m.tools.map((t, j) => (
                      <li key={j} className="font-mono text-[11px] leading-snug text-faint">
                        · {t}
                      </li>
                    ))}
                  </ul>
                )}
                {m.text ? (
                  <AnswerVersions m={m} remote={remote} onPeek={onPeek} onDecide={onDecide} />
                ) : (
                  m.pending && <Blink />
                )}
                {m.error && <p className="text-[12px] text-destructive">{m.error}</p>}
                {!m.pending && (m.ms != null || m.marked) && (
                  <Foot m={m} onMark={(k) => onMark(i, k)} />
                )}
              </div>
            ),
          )}
        </div>
        <div ref={end} />
      </div>
    </div>
  )
}

function AnswerVersions({ m, ...props }: { m: Msg } & Omit<AnswerProps, 'text'>) {
  const [simple, setSimple] = useState(false)
  const available = m.simpleText !== undefined || m.simplePending || Boolean(m.simpleError)
  return (
    <div className="space-y-3">
      {available && (
        <div role="group" aria-label="답변 보기" className="inline-flex gap-1 rounded-lg border border-border p-1">
          {[{ value: false, label: '1. 정확한 답변' }, { value: true, label: '2. 쉬운 설명' }].map((option) => (
            <button key={option.label} type="button" aria-pressed={simple === option.value}
              onClick={() => setSimple(option.value)}
              className={`min-h-9 rounded-md px-3 text-[12.5px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${simple === option.value ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary/50'}`}>
              {option.label}
            </button>
          ))}
        </div>
      )}
      {simple ? (
        <div className="space-y-2">
          <p className="text-[12px] text-muted-foreground">같은 내용을 쉽게 풀었습니다. 근거와 조건은 원문에서 함께 확인할 수 있습니다.</p>
          {m.simpleText && <Answer text={m.simpleText} {...props} onDecide={undefined} />}
          {m.simplePending && <p role="status" className="text-[12px] text-muted-foreground">의미와 조건을 유지하며 쉽게 풀어 쓰는 중…</p>}
          {m.simpleError && <p role="alert" className="text-[12px] text-destructive">쉬운 설명을 만들지 못했습니다. ‘정확한 답변’에서 원문을 볼 수 있습니다. {m.simpleError}</p>}
        </div>
      ) : <Answer text={m.text} {...props} />}
      {!simple && m.simplePending && <p role="status" className="text-[12px] text-muted-foreground">원문을 읽는 동안 쉬운 설명을 준비하고 있습니다.</p>}
    </div>
  )
}

/** 답 밑의 한 줄 — 걸린 시간 · 비용 · 모델, 그리고 "어긋났다". */
function Foot({ m, onMark }: { m: Msg; onMark: (k: Kind) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const bits: string[] = []
  if (m.ms != null) bits.push(`원문 ${(m.ms / 1000).toFixed(1)}s`)
  if (m.cost != null) bits.push(`$${m.cost.toFixed(3)}`)
  if (m.tokens) {
    const t = m.tokens
    const io = `${fmt(t.in)}→${fmt(t.out)}`
    const cache = t.cache_read ? ` · 캐시 ${fmt(t.cache_read)}` : ''
    bits.push(io + cache)
  }
  if (m.model) bits.push(m.model.replace('claude-', ''))
  if (m.simpleMs != null) bits.push(`쉬운 설명 ${(m.simpleMs / 1000).toFixed(1)}s`)
  if (m.simpleCost != null) bits.push(`설명 $${m.simpleCost.toFixed(3)}`)

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10.5px] text-faint">
      <span>{bits.join(' · ')}</span>
      {m.marked ? (
        <span className="text-destructive">어긋남 · {m.marked}</span>
      ) : open ? (
        <span className="flex items-center gap-1">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  await onMark(k)
                } finally {
                  setBusy(false)
                  setOpen(false)
                }
              }}
              className="rounded border border-border px-1.5 py-[1px] hover:bg-secondary disabled:opacity-40"
            >
              {k}
            </button>
          ))}
          <button type="button" onClick={() => setOpen(false)} className="px-1 hover:text-foreground">
            취소
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded px-1 hover:bg-secondary hover:text-foreground"
          title="틀린 그 순간에 부류를 찍는다. census 형식으로 쌓인다."
        >
          어긋났다
        </button>
      )}
    </div>
  )
}

function fmt(n?: number) {
  if (n == null) return '?'
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

function Blink() {
  return (
    <span className="inline-block h-3.5 w-1.5 animate-pulse rounded-[1px] bg-faint align-middle" />
  )
}
