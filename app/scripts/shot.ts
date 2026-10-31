// Screenshots of the states worth looking at, into the folder given as the first argument.
import { chromium } from '@playwright/test'

const out = process.argv[2] ?? '.'
const base = `http://127.0.0.1:${process.env.APP_PORT ?? 5173}`

const browser = await chromium.launch({ channel: 'chromium' })

const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await desktop.emulateMedia({ reducedMotion: 'reduce' })
await desktop.goto(base)
await desktop.locator('.element').first().waitFor()
await desktop.waitForTimeout(200)
await desktop.screenshot({ path: `${out}/first.png` })

const rows = desktop.locator('.element')
for (let i = 0; i < (await rows.count()); i++) {
  await rows.nth(i).click()
  await desktop.waitForTimeout(150)
  await desktop.screenshot({ path: `${out}/row-${i}.png` })
}

await desktop.getByRole('button', { name: 'New idea' }).click()
await desktop
  .getByLabel('Describe your idea')
  .fill('A phone that hides which site you visit. It fetches the key from DNS before connecting.')
await desktop.waitForTimeout(150)
await desktop.screenshot({ path: `${out}/new-idea.png` })

const phone = await browser.newPage({ viewport: { width: 390, height: 844 } })
await phone.emulateMedia({ reducedMotion: 'reduce' })
await phone.goto(base)
await phone.locator('.element').first().waitFor()
await phone.waitForTimeout(200)
await phone.screenshot({ path: `${out}/phone.png`, fullPage: true })

await browser.close()
