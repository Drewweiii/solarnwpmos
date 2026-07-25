import { describe, expect, it } from 'vitest'
import { TOPIC_ANSWERS } from '../assistantContent'
import {
  ALL_TOPIC_GROUPS,
  findCategoryById,
  findClarifyGroup,
  findGroupById,
  findGroupBySubQuestionId,
  groupsForRole,
  TOPIC_CATEGORIES,
} from '../assistantTopics'

// A guard against the exact failure mode this content is expected to grow
// into over many future sessions: adding a sub-question to assistantTopics.ts
// but forgetting its answer in assistantContent.ts (or vice versa).
describe('assistantTopics/assistantContent consistency', () => {
  it('every sub-question across every category has a matching answer, and every answer has a sub-question', () => {
    const subQuestionIds = ALL_TOPIC_GROUPS.flatMap((g) => g.subQuestions.map((sq) => sq.id))
    const answerIds = Object.keys(TOPIC_ANSWERS)

    for (const id of subQuestionIds) {
      expect(answerIds).toContain(id)
    }
    for (const id of answerIds) {
      expect(subQuestionIds).toContain(id)
    }
  })

  it('sub-question ids are globally unique', () => {
    const ids = ALL_TOPIC_GROUPS.flatMap((g) => g.subQuestions.map((sq) => sq.id))
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every answer is non-empty and speaks as the male character (never หนู/ค่ะ/คะ)', () => {
    for (const [id, text] of Object.entries(TOPIC_ANSWERS)) {
      expect(text.length, `answer for ${id} should not be empty`).toBeGreaterThan(0)
      expect(text, `answer for ${id} should use ผม/ครับ, not หนู/ค่ะ/คะ`).not.toMatch(/หนู|ค่ะ|คะ/)
    }
  })
})

describe('the data-provenance group added 2026-07-25', () => {
  // The site labels where every displayed number came from; these answers are
  // the assistant's version of the same promise. They exist to be honest about
  // limits, so the test guards the admissions rather than the marketing.

  it('admits there is no on-site sensor instead of implying measured data', () => {
    expect(TOPIC_ANSWERS.data_no_sensor).toMatch(/ไม่มีสถานีตรวจอากาศ|SCADA/)
  })

  it('separates the values GFS supplies from the ones this system computes', () => {
    const answer = TOPIC_ANSWERS.data_table_source
    expect(answer).toContain('GFS')
    expect(answer).toContain('pvlib')
  })

  it('names the published rate and emission factor rather than stating bare numbers', () => {
    const answer = TOPIC_ANSWERS.data_official
    // Must match api/green_savings.py's real constants.
    expect(answer).toContain('4.1025')
    expect(answer).toContain('0.4758')
    expect(answer).toMatch(/กกพ/)
  })

  it('still says CAPEX and WACC are estimates on the Financial page answer', () => {
    // These two are the only figures left un-sourced; the page must not read
    // as fully confirmed just because the tariff and BOI now are.
    expect(TOPIC_ANSWERS.page_financial).toMatch(/WACC/)
    expect(TOPIC_ANSWERS.page_financial).toMatch(/ค่าประมาณ/)
  })

  it('is reachable from a bare keyword a visitor would actually type', () => {
    expect(findClarifyGroup('ข้อมูลมาจากไหน')?.id).toBe('data_provenance')
    expect(findClarifyGroup('เชื่อได้ไหม')?.id).toBe('data_provenance')
  })
})

describe('findClarifyGroup', () => {
  it('finds the Inverter group from a bare keyword, in Thai or English', () => {
    expect(findClarifyGroup('inverter')?.id).toBe('inverter')
    expect(findClarifyGroup('อยากรู้เรื่องอินเวอร์เตอร์')?.id).toBe('inverter')
  })

  it('returns null for a question that names no known group', () => {
    expect(findClarifyGroup('อยากรู้เรื่องดวงจันทร์')).toBeNull()
  })
})

describe('lookup helpers', () => {
  it('findGroupBySubQuestionId finds the owning group', () => {
    expect(findGroupBySubQuestionId('inv_what')?.id).toBe('inverter')
    expect(findGroupBySubQuestionId('nonexistent-id')).toBeNull()
  })

  it('findCategoryById / findGroupById resolve real ids from TOPIC_CATEGORIES', () => {
    expect(findCategoryById('system')?.title).toBeTruthy()
    expect(findCategoryById('nope')).toBeNull()
    expect(findGroupById('inverter')?.title).toBe('Inverter')
    expect(findGroupById('nope')).toBeNull()
  })

  it('every category has at least one group, every group at least one sub-question', () => {
    for (const category of TOPIC_CATEGORIES) {
      expect(category.groups.length).toBeGreaterThan(0)
      for (const group of category.groups) {
        expect(group.subQuestions.length).toBeGreaterThan(0)
      }
    }
  })
})

describe('groupsForRole', () => {
  const websiteCategory = findCategoryById('website')!

  it('drops Simulation/Financial for a viewer', () => {
    const groups = groupsForRole(websiteCategory, 'viewer')
    expect(groups.find((g) => g.id === 'page_simulation')).toBeUndefined()
    expect(groups.find((g) => g.id === 'page_financial')).toBeUndefined()
    // Everything else stays.
    expect(groups.find((g) => g.id === 'page_forecast')).toBeDefined()
    expect(groups.length).toBe(websiteCategory.groups.length - 2)
  })

  it('keeps every group for operator/admin/unknown roles', () => {
    for (const role of ['operator', 'admin', null, undefined]) {
      expect(groupsForRole(websiteCategory, role)).toEqual(websiteCategory.groups)
    }
  })
})
