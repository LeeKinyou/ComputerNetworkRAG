const fs = require('node:fs')
const { chromium } = require('playwright-core')

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = 'http://127.0.0.1:5173'

const routes = [
  ['/', 'overview'],
  ['/graph', 'graph'],
  ['/path', 'path'],
  ['/chat', 'chat'],
  ['/chat?mode=rag', 'chat-rag'],
  ['/documents', 'documents'],
  ['/progress', 'progress'],
  ['/insights', 'insights'],
  ['/profile', 'profile'],
  ['/screen', 'screen'],
]

;(async () => {
  fs.mkdirSync('shots', { recursive: true })
  const browser = await chromium.launch({ executablePath: CHROME, headless: true })

  for (const mode of [
    { suffix: '', dark: false },
    { suffix: '-dark', dark: true },
  ]) {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
    })
    if (mode.dark) {
      await page.addInitScript(() => localStorage.setItem('cnrag-theme', 'dark'))
    }
    for (const [path, name] of routes) {
      await page.goto(BASE + path, { waitUntil: 'networkidle' })
      await page.waitForTimeout(1200)
      await page.screenshot({ path: `shots/${name}${mode.suffix}.png` })
      console.log('shot:', name + mode.suffix)
    }
    await page.close()
  }

  await browser.close()
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
