import { useState, type ReactElement } from 'react'
import { CloudFace } from './CloudFace'
import { MoonFace } from './MoonFace'
import { KnowledgeAssistantPanel } from './KnowledgeAssistantPanel'
import { CLOUD_PERSONA, MOON_PERSONA } from '../lib/moonCloudPersonas'
import { useMascotReaction } from '../lib/useMascotReaction'
import type { KnowledgePersona } from '../lib/knowledgeAssistant'
import type { MascotMood } from './MascotFace'
import './Solar3DAssistants.css'

const PLAY_REACTION_REVERT_MS = 5000

/** น้อง Moon + น้อง Cloud as page-local AI assistants on the 3D View page
 * only (per the user's 2026-07-19 request: bring these two login-screen
 * characters onto 3D View - NOT Forecast - each with voice + play + its own
 * knowledge set, like น้อง Solar). They float on the LEFT edge (น้อง Solar
 * already owns bottom-right site-wide), each a face-button that toggles its
 * own knowledge panel (KnowledgeAssistantPanel + moonCloudPersonas.ts). At
 * most one panel is open at a time - opening one closes the other - so the
 * two left-anchored panels never overlap. Play interactions drive each
 * character's own face/speech bubble via its own useMascotReaction, exactly
 * like น้อง Solar's floating mascot. */
export function Solar3DAssistants() {
  const [openId, setOpenId] = useState<string | null>(null)
  const moon = useMascotReaction()
  const cloud = useMascotReaction()

  const reactionFor = (persona: KnowledgePersona) => (persona.id === MOON_PERSONA.id ? moon : cloud)

  function toggle(id: string) {
    setOpenId((cur) => (cur === id ? null : id))
  }

  function renderLauncher(persona: KnowledgePersona, face: (mood: MascotMood) => ReactElement) {
    const reaction = reactionFor(persona)
    const isOpen = openId === persona.id
    return (
      <div className={`solar3d-assistant-launcher solar3d-assistant-launcher-${persona.id}`}>
        {reaction.speech && (
          <div className="solar3d-assistant-speech" role="status" aria-live="polite">
            {reaction.speech}
          </div>
        )}
        <button
          type="button"
          className="solar3d-assistant-button"
          onClick={() => toggle(persona.id)}
          aria-label={isOpen ? `ปิดผู้ช่วย ${persona.name}` : `เปิดผู้ช่วย ${persona.name} (${persona.emoji})`}
          aria-expanded={isOpen}
          title={persona.name}
        >
          {face(reaction.mood)}
        </button>
        <span className="solar3d-assistant-name">{persona.name}</span>
      </div>
    )
  }

  const openPersona = openId === MOON_PERSONA.id ? MOON_PERSONA : openId === CLOUD_PERSONA.id ? CLOUD_PERSONA : null

  return (
    <>
      <div className="solar3d-assistant-dock" aria-label="ผู้ช่วยประจำหน้า 3D View">
        <span className="solar3d-assistant-dock-label">ถามผู้ช่วยประจำหน้านี้ 👉</span>
        {renderLauncher(MOON_PERSONA, (mood) => <MoonFace mood={mood} />)}
        {renderLauncher(CLOUD_PERSONA, (mood) => <CloudFace mood={mood} />)}
      </div>
      {openPersona && (
        <KnowledgeAssistantPanel
          persona={openPersona}
          isOpen
          onClose={() => setOpenId(null)}
          onInteract={(interaction) => reactionFor(openPersona).trigger(interaction.mood, interaction.speech, PLAY_REACTION_REVERT_MS)}
        />
      )}
    </>
  )
}
