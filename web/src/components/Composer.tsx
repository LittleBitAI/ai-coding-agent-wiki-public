import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

type Props = { busy: boolean; onSend: (text: string) => void }

export function Composer({ busy, onSend }: Props) {
  const [text, setText] = useState('')
  const box = useRef<HTMLTextAreaElement>(null)

  // Pasting several lines in is common. It grows with the content, up to a
  // limit — past that the composer would push the conversation off screen.
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [text])

  function send() {
    const value = text.trim()
    if (!value || busy) return
    onSend(value)
    setText('')
  }

  return (
    <div className="border-t border-border bg-card">
      <div className="mx-auto flex max-w-3xl items-end gap-2 px-6 py-3">
        <Textarea
          ref={box}
          rows={1}
          value={text}
          disabled={busy}
          placeholder={busy ? '답하는 중…' : '물어라. Enter 로 보내고 Shift+Enter 로 줄바꿈.'}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              send()
            }
          }}
          className="max-h-[200px] min-h-9 resize-none bg-background text-[13.5px]"
        />
        <Button onClick={send} disabled={busy || !text.trim()} className="h-9">
          보내
        </Button>
      </div>
    </div>
  )
}
