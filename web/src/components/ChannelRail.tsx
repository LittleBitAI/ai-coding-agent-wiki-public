import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import type { Channel } from '@/lib/api'
import { MAP, MIRROR } from '@/App'

type Props = {
  channels: Channel[]
  active: string
  busy: boolean
  onPick: (id: string) => void
  onReset: () => void
}

export function ChannelRail({ channels, active, busy, onPick, onReset }: Props) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="px-4 pt-4 pb-3">
        <div className="font-heading text-[15px] font-semibold leading-tight">
          위키에 묻는다
        </div>
        <div className="mt-0.5 text-[11.5px] text-faint">
          프로젝트는 함께, 대화는 채널별로
        </div>
      </div>

      <Separator className="bg-sidebar-border" />

      <nav className="flex-1 overflow-y-auto p-2">
        {channels.map((c) => (
          <button
            key={c.id}
            onClick={() => onPick(c.id)}
            className={cn(
              'mb-0.5 w-full rounded-md px-2.5 py-2 text-left transition-colors',
              'hover:bg-sidebar-accent',
              c.id === active && 'bg-sidebar-accent',
            )}
          >
            <div className="flex items-center gap-1.5">
              <span
                className={cn(
                  'size-1.5 shrink-0 rounded-full',
                  c.live ? 'bg-primary' : 'bg-border',
                )}
                title={c.live ? '프로세스가 살아 있다' : '아직 안 띄웠다'}
              />
              <span className="font-heading text-[13.5px] font-semibold">
                #{c.label}
              </span>
            </div>
            <div className="mt-0.5 pl-3 text-[11.5px] leading-snug text-muted-foreground">
              {c.blurb}
            </div>
          </button>
        ))}
      </nav>

      <Separator className="bg-sidebar-border" />

      <button
        onClick={() => onPick(MAP)}
        className={cn(
          'mx-2 my-2 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-sidebar-accent',
          active === MAP && 'bg-sidebar-accent',
        )}
      >
        <div className="font-heading text-[13.5px] font-semibold">위키 지도</div>
        <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
          페이지·주입 비용·공동 주입을 그림으로
        </div>
      </button>

      <button
        onClick={() => onPick(MIRROR)}
        className={cn(
          'mx-2 mb-2 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-sidebar-accent',
          active === MIRROR && 'bg-sidebar-accent',
        )}
      >
        <div className="font-heading text-[13.5px] font-semibold">한국어 미러</div>
        <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
          저장소를 골라 그 세션을 한국어로
        </div>
      </button>

      <Separator className="bg-sidebar-border" />

      <div className="p-3">
        <button
          onClick={onReset}
          disabled={busy}
          className="w-full rounded-md border border-sidebar-border px-2 py-1.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-sidebar-accent disabled:opacity-40"
        >
          이 채널 문맥 비우기
        </button>
      </div>
    </aside>
  )
}
