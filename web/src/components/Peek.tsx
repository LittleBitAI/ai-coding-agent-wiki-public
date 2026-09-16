import type { Peek as PeekData } from '@/lib/api'

type Props = { data: PeekData | null; error?: string; onClose: () => void }

/** 인용된 자리를 옆 서랍에서 본다. 대화는 그대로 두고. */
export function Peek({ data, error, onClose }: Props) {
  if (!data && !error) return null
  return (
    <aside className="flex w-[34rem] shrink-0 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0 truncate font-mono text-[12px]">
          {data ? `${data.path}:${data.line}` : '…'}
          {data && <span className="ml-2 text-faint">{data.total}줄</span>}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 py-0.5 text-[12px] text-muted-foreground hover:bg-secondary"
        >
          닫기
        </button>
      </div>
      <div className="flex-1 overflow-auto">
        {error && <p className="p-3 text-[12.5px] text-destructive">{error}</p>}
        {data && (
          <pre className="p-3 font-mono text-[12px] leading-[1.55]">
            {data.lines.map((l, i) => {
              const n = data.start + i
              const hit = n === data.line
              return (
                <div
                  key={n}
                  className={hit ? '-mx-3 bg-primary/10 px-3' : undefined}
                >
                  <span className="mr-3 inline-block w-8 select-none text-right text-faint">
                    {n}
                  </span>
                  {l || ' '}
                </div>
              )
            })}
          </pre>
        )}
      </div>
    </aside>
  )
}
