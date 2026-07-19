import { describe, expect, it } from 'vitest'
import { findMascotInteraction, MASCOT_INTERACTIONS } from '../mascotInteractions'

describe('MASCOT_INTERACTIONS', () => {
  it('has a generous number of interactions, not just 2-3 token options', () => {
    expect(MASCOT_INTERACTIONS.length).toBeGreaterThanOrEqual(20) // expanded 2026-07-18, was 12
  })

  it('every label includes at least one emoji, matching the "เพิ่มอิโมจิ" request', () => {
    // eslint-disable-next-line no-misleading-character-class -- matching any emoji-ish codepoint, not a single grapheme
    const hasEmoji = /\p{Extended_Pictographic}/u
    for (const interaction of MASCOT_INTERACTIONS) {
      expect(hasEmoji.test(interaction.label), `${interaction.id} label should include an emoji`).toBe(true)
    }
  })

  it('every interaction has a unique id', () => {
    const ids = MASCOT_INTERACTIONS.map((i) => i.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every speech line is non-empty and speaks as the male character (never หนู/ค่ะ/คะ)', () => {
    for (const interaction of MASCOT_INTERACTIONS) {
      expect(interaction.speech.length, `${interaction.id} speech should not be empty`).toBeGreaterThan(0)
      expect(interaction.speech, `${interaction.id} should use ผม/ครับ, not หนู/ค่ะ/คะ`).not.toMatch(/หนู|ค่ะ|คะ/)
    }
  })

  it('every interaction uses a mood other than plain idle (there should always be a visible reaction)', () => {
    for (const interaction of MASCOT_INTERACTIONS) {
      expect(interaction.mood).not.toBe('idle')
    }
  })
})

describe('findMascotInteraction', () => {
  it('finds a real interaction by id', () => {
    expect(findMascotInteraction('pet_head')?.mood).toBe('blush')
  })

  it('returns null for an unknown id', () => {
    expect(findMascotInteraction('nonexistent')).toBeNull()
  })
})
