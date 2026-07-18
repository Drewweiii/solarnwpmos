import { useState } from 'react'
import { AssistantPanel } from './AssistantPanel'
import { Mascot } from './Mascot'

/** Owns the open/closed state shared between the mascot (the toggle button)
 * and the chat panel it opens - mounted once in Layout.tsx so it floats
 * over every authenticated page. */
export function AIAssistant() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <AssistantPanel isOpen={isOpen} onClose={() => setIsOpen(false)} />
      <Mascot isOpen={isOpen} onToggle={() => setIsOpen((v) => !v)} />
    </>
  )
}
