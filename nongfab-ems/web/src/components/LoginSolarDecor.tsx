import './LoginSolarDecor.css'

/** Purely decorative solar-system motif filling the empty left/right margins
 * on the login screen on a wide viewport - the user asked for something
 * here so the page didn't read as bare, but explicitly "ทำพอดีๆ" (tastefully,
 * not cluttered). Kept to a small sun + two orbiting dots per side, low
 * opacity, `aria-hidden` and `pointer-events: none` throughout since it
 * carries no information. Hidden below LoginSolarDecor.css's breakpoint -
 * there is no spare margin to decorate on a narrow/mobile screen, and this
 * must never be the thing that reintroduces the horizontal-overflow bug
 * fixed 2026-07-18 in App.css/index.css.
 */
export function LoginSolarDecor() {
  return (
    <div className="login-solar-decor" aria-hidden="true">
      <div className="login-solar-decor-side login-solar-decor-left">
        <div className="login-solar-decor-sun" />
        <div className="login-solar-decor-orbit login-solar-decor-orbit-1">
          <div className="login-solar-decor-planet login-solar-decor-planet-a" />
        </div>
        <div className="login-solar-decor-orbit login-solar-decor-orbit-2">
          <div className="login-solar-decor-planet login-solar-decor-planet-b" />
        </div>
        <span className="login-solar-decor-star login-solar-decor-star-1" />
        <span className="login-solar-decor-star login-solar-decor-star-2" />
        <span className="login-solar-decor-star login-solar-decor-star-3" />
      </div>
      <div className="login-solar-decor-side login-solar-decor-right">
        <div className="login-solar-decor-sun" />
        <div className="login-solar-decor-orbit login-solar-decor-orbit-1">
          <div className="login-solar-decor-planet login-solar-decor-planet-a" />
        </div>
        <div className="login-solar-decor-orbit login-solar-decor-orbit-2">
          <div className="login-solar-decor-planet login-solar-decor-planet-b" />
        </div>
        <span className="login-solar-decor-star login-solar-decor-star-1" />
        <span className="login-solar-decor-star login-solar-decor-star-2" />
        <span className="login-solar-decor-star login-solar-decor-star-3" />
      </div>
    </div>
  )
}
