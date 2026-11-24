const fs = require('node:fs')
const { chromium } = require('playwright-core')

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = 'http://127.0.0.1:8000'

const routes = [
  ['/', 'overview'],
  ['/chat', 'chat'],
  ['/assignments', 'assignments'],
  ['/practice', 'practice'],
  ['/wrongbook', 'wrongbook'],
  ['/graph', 'graph'],
  ['/path', 'path'],
  ['/documents', 'documents'],
  ['/progress', 'progress'],
  ['/profile', 'profile'],
  ['/insights', 'insights'],
  ['/screen', 'screen'],
]

/** 找出把页面撑出横向滚动条的元素，方便定位固定宽度 */
function overflowProbe() {
  const viewport = document.documentElement.clientWidth
  const scroller = document.scrollingElement
  const pageOverflow = scroller ? scroller.scrollWidth - viewport : 0
  const offenders = []
  for (const node of document.querySelectorAll('body *')) {
    const style = window.getComputedStyle(node)
    if (style.display === 'none' || style.visibility === 'hidden' || style.position === 'fixed') continue
    const rect = node.getBoundingClientRect()
    if (rect.width <= 0) continue
    if (rect.right > viewport + 1.5) {
      offenders.push({
        tag: node.tagName.toLowerCase(),
        cls: String(node.className).slice(0, 110),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      })
    }
  }
  return { viewport, pageOverflow, offenders: offenders.slice(0, 8) }
}

;(async () => {
  fs.mkdirSync('shots/mobile', { recursive: true })
  const browser = await chromium.launch({ executablePath: CHROME, headless: true })
  const report = []

  for (const mode of [
    { suffix: 'phone', width: 390, height: 844, dpr: 3 },
    { suffix: 'tablet', width: 768, height: 1024, dpr: 2 },
  ]) {
    const page = await browser.newPage({
      viewport: { width: mode.width, height: mode.height },
      deviceScaleFactor: mode.dpr,
      isMobile: true,
      hasTouch: true,
    })

    // 登录：先取 /auth/me，未登录则走表单
    await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
    await page.screenshot({ path: `shots/mobile/login-${mode.suffix}.png` })
    if (await page.locator('#login-username').count()) {
      await page.fill('#login-username', 'demo_user')
      await page.fill('#login-password', 'demo2026')
      await page.click('button[type=submit]')
      await page.waitForTimeout(1600)
    }

    for (const [path, name] of routes) {
      await page.goto(BASE + path, { waitUntil: 'networkidle' })
      await page.waitForTimeout(1400)
      await page.screenshot({ path: `shots/mobile/${name}-${mode.suffix}.png` })
      const probe = await page.evaluate(overflowProbe)
      report.push({ mode: mode.suffix, name, ...probe })
      console.log(`shot ${mode.suffix}: ${name}`, probe.pageOverflow ? `OVERFLOW ${probe.pageOverflow}px` : 'ok')
    }

    // 问答页的移动端抽屉：任务列表 / 计划产物来源
    await page.goto(BASE + '/chat', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)
    const tasksBtn = page.getByRole('button', { name: /^\s*任务/ }).first()
    if (await tasksBtn.count()) {
      await tasksBtn.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: `shots/mobile/chat-tasks-${mode.suffix}.png` })
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
    }
    const artifactBtn = page.getByRole('button', { name: /^\s*产物/ }).first()
    if (await artifactBtn.count()) {
      await artifactBtn.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: `shots/mobile/chat-detail-${mode.suffix}.png` })
    }
    // 全站导航抽屉
    await page.goto(BASE + '/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
    await page.click('button[aria-label="打开导航"]')
    await page.waitForTimeout(400)
    await page.screenshot({ path: `shots/mobile/nav-drawer-${mode.suffix}.png` })

    await page.close()
  }

  await browser.close()
  fs.writeFileSync('shots/mobile/report.json', JSON.stringify(report, null, 2))
  const bad = report.filter((row) => row.pageOverflow > 0 || row.offenders.length)
  console.log('\n=== 溢出检查 ===')
  for (const row of bad) {
    console.log(`\n[${row.mode}] ${row.name} pageOverflow=${row.pageOverflow}`)
    for (const item of row.offenders) console.log(`  ${item.tag} w=${item.width} right=${item.right} :: ${item.cls}`)
  }
  if (!bad.length) console.log('没有横向溢出')
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
