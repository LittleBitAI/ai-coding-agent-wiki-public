import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Channel, Options } from '@/lib/api'

type Props = {
  channel: Channel
  options: Options | null
  busy: boolean
  onChange: (next: { repo: string; model: string; effort: string }) => void
}

// Radix Select 는 빈 문자열을 값으로 못 쓴다. "기본"(플래그를 안 붙임)을
// 화면에서는 이 표로 들고, 서버로 보낼 때 다시 빈 문자열로 돌린다.
// 고른 것을 다시 눌러 해제하면 `null` 이 오므로 그것도 "기본" 으로 친다.
const NONE = '__default__'
const out = (v: string | null) => (!v || v === NONE ? '' : v)
const inn = (v: string) => v || NONE

type Item = { value: string; label: string; note?: string }

export function Toolbar({ channel, options, busy, onChange }: Props) {
  const pick = (patch: Partial<Channel>) =>
    onChange({
      repo: channel.repo,
      model: channel.model,
      effort: channel.effort,
      ...patch,
    })

  const projects: Item[] =
    options?.projects.map((p) => ({
      value: p.id,
      label: p.id,
      note: p.wired ? '위키 붙음' : undefined,
    })) ?? []
  const models: Item[] =
    options?.models.map((m) => ({ value: inn(m.id), label: m.label, note: m.note })) ??
    []
  const efforts: Item[] =
    (options?.models.find((m) => m.id === channel.model)?.efforts ?? options?.efforts)?.map((e) => ({ value: inn(e.id), label: e.label, note: e.note })) ??
    []

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Picker
        label="프로젝트"
        width="w-56"
        mono
        items={projects}
        value={channel.repo}
        disabled={busy || !options}
        onPick={(repo) => repo && pick({ repo })}
      />
      <Picker
        label="모델"
        width="w-44"
        items={models}
        value={inn(channel.model)}
        disabled={busy || !options}
        onPick={(v) => {
          const model = out(v)
          const supported = options?.models.find((m) => m.id === model)?.efforts ?? options?.efforts
          pick({ model, effort: supported?.some((e) => e.id === channel.effort) ? channel.effort : '' })
        }}
      />
      <Picker
        label="추론 강도"
        width="w-36"
        items={efforts}
        value={inn(channel.effort)}
        disabled={busy || !options}
        onPick={(v) => pick({ effort: out(v) })}
      />
      {options?.codex_error && <p role="status" className="w-full text-xs text-destructive">{options.codex_error}</p>}
    </div>
  )
}

/** 고르는 칸 하나.
 *
 *  `SelectValue` 에 표시를 직접 넘긴다. 목록이 서버에서 오는데, 그 전에 한 번
 *  그려지면 Radix 가 고른 값에 맞는 항목을 못 찾아 값 자체를 그대로 띄운다 —
 *  화면에 `__default__` 가 떴다. 라벨을 우리가 들면 그 일이 없다. */
function Picker({
  label,
  width,
  items,
  value,
  disabled,
  mono,
  onPick,
}: {
  label: string
  width: string
  items: Item[]
  value: string
  disabled: boolean
  mono?: boolean
  onPick: (v: string | null) => void
}) {
  const here = items.find((i) => i.value === value)
  return (
    <label className="flex items-center gap-1.5">
      <span className="font-heading text-[11px] text-faint">{label}</span>
      <Select value={value} disabled={disabled} onValueChange={onPick}>
        <SelectTrigger size="sm" className={`${width} bg-card text-[12.5px]`}>
          <SelectValue>
            <span className={mono ? 'font-mono text-[12px]' : undefined}>
              {here?.label ?? '…'}
            </span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {items.map((i) => (
            <SelectItem key={i.value} value={i.value}>
              <span className={mono ? 'font-mono text-[12px]' : undefined}>
                {i.label}
              </span>
              {i.note && (
                <span className="ml-1.5 text-[10.5px] text-faint">{i.note}</span>
              )}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}
