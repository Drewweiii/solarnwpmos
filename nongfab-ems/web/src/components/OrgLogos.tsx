import './OrgLogos.css'

interface LogoEntry {
  src: string
  alt: string
}

// Site's own mark first, then the 5 partner/sponsor organizations, in the
// order the user provided them.
const LOGOS: LogoEntry[] = [
  { src: '/logos/site-logo.svg', alt: 'PTT LNG Terminal 2 Nong Fab Solar Forecasting' },
  { src: '/logos/ptt-lng.png', alt: 'PTT LNG' },
  { src: '/logos/pe-lng.png', alt: 'PE LNG Co., Ltd.' },
  { src: '/logos/ee-chula.png', alt: 'Electrical Engineering, Chulalongkorn University' },
  { src: '/logos/chula-engineering.png', alt: 'Chula Engineering - Innovation toward Sustainability' },
  { src: '/logos/chula-university.png', alt: 'Chulalongkorn University' },
]

interface OrgLogosProps {
  /** 'login' (bigger, above the sign-in form) or 'footer' (smaller, sits
   * at the very bottom of every authenticated page - never fixed/floating,
   * so it can never cover other on-screen content). */
  variant: 'login' | 'footer'
}

export function OrgLogos({ variant }: OrgLogosProps) {
  return (
    <div className={`org-logos org-logos-${variant}`}>
      {LOGOS.map((logo) => (
        <img key={logo.src} src={logo.src} alt={logo.alt} className="org-logos-item" loading="lazy" />
      ))}
    </div>
  )
}
