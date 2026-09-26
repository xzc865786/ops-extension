// Apply the theme passed through Sub2API's bootstrap before Vue and CSS render.
const theme = document.cookie.match(/(?:^|;\s*)ops_theme=(light|dark)(?:;|$)/)?.[1]
document.documentElement.classList.toggle('dark', theme === 'dark')
