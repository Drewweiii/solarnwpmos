import './SiteCredit.css'

/** Left intentionally blank - the user will supply the real "site built by
 * ..." credit text in a future session (2026-07-18: Claude Code credit was
 * running low, so this was scaffolded without inventing placeholder names).
 * Once CREDIT_TEXT is filled in it appears automatically for viewer/operator
 * in the nav slot where admin instead sees "Feedback" - see Layout.tsx.
 */
const CREDIT_TEXT = ''

interface SiteCreditProps {
  text?: string
}

export function SiteCredit({ text = CREDIT_TEXT }: SiteCreditProps) {
  if (!text) return null
  return <span className="site-credit">{text}</span>
}
