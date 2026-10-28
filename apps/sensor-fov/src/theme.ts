// Three.js needs resolved colors rather than CSS variable expressions.
export function sceneTheme() {
  const style = getComputedStyle(document.documentElement)
  const color = (token: string) =>
    style.getPropertyValue(`--sm-${token}`).trim()
  return {
    background: color('bg'),
    surface: color('surface'),
    border: color('border'),
    text: color('text'),
    muted: color('muted'),
    accent: color('accent'),
    info: color('info'),
    warning: color('warning'),
    danger: color('danger'),
  }
}
