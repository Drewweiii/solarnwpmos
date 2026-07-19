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
 * two left-anchored panels never overlap.
 *
 * When a persona is active it also floats as a buddy right next to น้อง Solar
 * (bottom-right), per the user's 2026-07-19 request - tapping a launcher
 * "summons" that character beside น้อง Solar, and tapping the other swaps it
 * in immediately (only one Moon/Cloud buddy at a time). Play interactions
 * drive that buddy's own face/speech bubble via its own useMascotReaction,
 * exactly like น้อง Solar's floating mascot. */
function faceFor(persona: KnowledgePersona, mood: MascotMood): ReactElement {
  return persona.id === MOON_PERSONA.id ? <MoonFace mood={mood} /> : <CloudFace mood={mood} />
}

export function Solar3DAssistants() {
  const [openId, setOpenId] = useState<string | null>(null)
  const moon = useMascotReaction()
  const cloud = useMascotReaction()

  const reactionFor = (persona: KnowledgePersona) => (persona.id === MOON_PERSONA.id ? moon : cloud)

  function toggle(id: string) {
    setOpenId((cur) => (cur === id ? null : id))
  }

  function renderLauncher(persona: KnowledgePersona) {
    const isOpen = openId === persona.id
    return (
      <div className={`solar3d-assistant-launcher solar3d-assistant-launcher-${persona.id}`}>
        <button
          type="button"
          className="solar3d-assistant-button"
          onClick={() => toggle(persona.id)}
          aria-label={isOpen ? `ปิดผู้ช่วย ${persona.name}` : `เปิดผู้ช่วย ${persona.name} (${persona.emoji})`}
          aria-expanded={isOpen}
          title={persona.name}
        >
          {faceFor(persona, 'idle')}
        </button>
        <span className="solar3d-assistant-name">{persona.name}</span>
      </div>
    )
  }

  const openPersona = openId === MOON_PERSONA.id ? MOON_PERSONA : openId === CLOUD_PERSONA.id ? CLOUD_PERSONA : null
  const buddyReaction = openPersona ? reactionFor(openPersona) : null

  return (
    <>
      <div className="solar3d-assistant-dock" aria-label="ผู้ช่วยประจำหน้า 3D View">
        <span className="solar3d-assistant-dock-label">ถามผู้ช่วยประจำหน้านี้ 👉</span>
        {renderLauncher(MOON_PERSONA)}
        {renderLauncher(CLOUD_PERSONA)}
      </div>

      {/* Buddy floating next to น้อง Solar while its panel is open - swaps to
          whichever of Moon/Cloud is currently active. */}
      {openPersona && buddyReaction && (
        <div
          key={openPersona.id}
          className={`solar3d-assistant-buddy solar3d-assistant-buddy-${openPersona.id}${
            buddyReaction.mood !== 'idle' ? ' solar3d-assistant-buddy-reacting' : ''
          }`}
          aria-hidden="true"
        >
          {buddyReaction.speech && <div className="solar3d-assistant-buddy-speech">{buddyReaction.speech}</div>}
          <div className="solar3d-assistant-buddy-face">{faceFor(openPersona, buddyReaction.mood)}</div>
          <span className="solar3d-assistant-buddy-name">{openPersona.name}</span>
        </div>
      )}

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
