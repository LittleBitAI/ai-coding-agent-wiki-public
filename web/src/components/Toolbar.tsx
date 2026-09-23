import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Channel, Options } from '@/lib/api'
import { useState } from 'react'

type Props = {
  channel: Channel
  options: Options | null
  busy: boolean
  projectBusy: boolean
  korean: boolean
  onKorean: (on: boolean) => void
  onChange: (next: { repo: string; model: string; effort: string }) => void
}

// A Radix Select cannot use the empty string as a value. "default" — meaning
// no flag is passed — is carried on screen by this token and turned back into
// an empty string on the way to the server. Pressing the selected item again
// deselects it and yields `null`, which counts as "default" too.
const NONE = '__default__'
const CUSTOM = '__custom__'
const out = (v: string | null) => (!v || v === NONE ? '' : v)
const inn = (v: string) => v || NONE

type Item = { value: string; label: string; note?: string }

export function Toolbar({
  channel, options, busy, projectBusy, korean, onKorean, onChange,
}: Props) {
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
  // The list only holds aliases, which already follow the newest model. A
  // name that is not on it — a new family, a pinned version — is typed in,
  // and shown as an item of its own once chosen.
  const [typing, setTyping] = useState(false)
  const listed = options?.models.some((m) => m.id === channel.model) ?? true
  const models: Item[] = [
    ...(options?.models.map((m) => ({ value: inn(m.id), label: m.label, note: m.note })) ?? []),
    ...(!listed ? [{ value: channel.model, label: channel.model, note: '직접 입력' }] : []),
    ...(options ? [{ value: CUSTOM, label: '직접 입력…' }] : []),
  ]
  const efforts: Item[] =
    (options?.models.find((m) => m.id === channel.model)?.efforts ?? options?.efforts)?.map((e) => ({ value: inn(e.id), label: e.label, note: e.note })) ??
    []

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Picker
        label="공통 프로젝트"
        width="w-56"
        mono
        items={projects}
        value={channel.repo}
        disabled={projectBusy || !options}
        onPick={(repo) => repo && pick({ repo })}
      />
      <Picker
        label="모델"
        width="w-44"
        items={models}
        value={inn(channel.model)}
        disabled={busy || !options}
        onPick={(v) => {
          if (v === CUSTOM) return setTyping(true)
          const model = out(v)
          const supported = options?.models.find((m) => m.id === model)?.efforts ?? options?.efforts
          pick({ model, effort: supported?.some((e) => e.id === channel.effort) ? channel.effort : '' })
        }}
      />
      {typing && (
        <input
          autoFocus
          aria-label="모델 이름"
          placeholder="claude-opus-5-5"
          className="w-40 rounded-md border border-border bg-card px-2 py-1 font-mono text-[12px]"
          onKeyDown={(e) => {
            if (e.key === 'Escape') setTyping(false)
            if (e.key !== 'Enter') return
            const model = e.currentTarget.value.trim()
            setTyping(false)
            if (model) pick({ model, effort: '' })
          }}
          onBlur={() => setTyping(false)}
        />
      )}
      <Picker
        label="추론 강도"
        width="w-36"
        items={efforts}
        value={inn(channel.effort)}
        disabled={busy || !options}
        onPick={(v) => pick({ effort: out(v) })}
      />
      <div
        role="group"
        aria-label="답변 언어"
        className="inline-flex gap-0.5 rounded-lg border border-border p-0.5"
      >
        {[
          { on: true, label: '한국어' },
          { on: false, label: 'English' },
        ].map((option) => (
          <button
            key={option.label}
            type="button"
            aria-pressed={korean === option.on}
            onClick={() => onKorean(option.on)}
            className={
              'rounded-md px-2 py-1 text-[11.5px] ' +
              (korean === option.on
                ? 'bg-secondary font-medium'
                : 'text-muted-foreground hover:bg-secondary/60')
            }
          >
            {option.label}
          </button>
        ))}
      </div>
      {options?.codex_error && <p role="status" className="w-full text-xs text-destructive">{options.codex_error}</p>}
    </div>
  )
}

/** One picker.
 *
 *  The label is handed to `SelectValue` directly. The list comes from the
 *  server, and on a render before it arrives Radix cannot find an item
 *  matching the selected value and shows the raw value instead —
 *  `__default__` appeared on screen. Holding the label ourselves stops that. */
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
