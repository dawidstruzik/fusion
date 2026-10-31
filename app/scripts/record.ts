// Records the demo path at 1440x900 to demo/backup.webm. Needs `bun run dev` running.
import { mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { chromium } from '@playwright/test'

const size = { width: 1440, height: 900 }
const browser = await chromium.launch({ channel: 'chromium' })
const context = await browser.newContext({ viewport: size, recordVideo: { dir: tmpdir(), size } })
const page = await context.newPage()

await page.goto(`http://127.0.0.1:${process.env.APP_PORT ?? 5173}`)
await page.locator('mark').first().waitFor()
await page.waitForTimeout(7000)

await page.locator('li:has(.element[aria-current="true"]) + li .element').click()
await page.waitForTimeout(6000)

await page.locator('.element', { hasText: /Not found$/ }).first().click()
await page.waitForTimeout(5000)

await page.getByRole('button', { name: 'New idea' }).click()
await page
  .getByLabel('Describe your idea')
  .pressSequentially('A phone that hides which site you visit. It fetches the key from DNS before connecting.', { delay: 25 })
await page.waitForTimeout(4000)

const video = page.video()
await context.close()
mkdirSync('demo', { recursive: true })
await video?.saveAs('demo/backup.webm')
await browser.close()
console.log('Saved demo/backup.webm')
