// Records the demo path at 1440x900 to demo/backup.webm and demo/backup.mp4, and the opening screen
// to demo/thumbnail.png. Starts on the lead idea, so the home page's design doesn't affect it.
// Needs `bun run dev` running, and ffmpeg.
import { mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { chromium } from '@playwright/test'

const base = `http://127.0.0.1:${process.env.APP_PORT ?? 5173}`
const { cases } = (await (await fetch(`${base}/api/cases`)).json()) as { cases: { id: string }[] }

const size = { width: 1440, height: 900 }
const browser = await chromium.launch({ channel: 'chromium' })
const context = await browser.newContext({ viewport: size, recordVideo: { dir: tmpdir(), size } })
const page = await context.newPage()

// The lead idea opens on its first part with highlighted words.
await page.goto(`${base}/#/idea/${cases[0]?.id}`)
await page.locator('mark').first().waitFor()
await page.waitForTimeout(500) // The date label has landed.
mkdirSync('demo', { recursive: true })
await page.screenshot({ path: 'demo/thumbnail.png' })
await page.waitForTimeout(8500)

await page.locator('.element', { has: page.locator('.element-date') }).nth(2).click()
await page.waitForTimeout(6000)

await page.locator('.element', { hasText: /Not found$/ }).first().click()
await page.waitForTimeout(5000)

// The next idea, to show an email as well as a patent.
await page.goto(`${base}/#/idea/${cases[1]?.id}`)
await page.mouse.move(1000, 5) // Off the rail, so no row shows its hover color.
await page.locator('mark').first().waitFor()
await page.waitForTimeout(6500)

const video = page.video()
await context.close()
const raw = `${tmpdir()}/fusion-raw.webm`
await video?.saveAs(raw)
await browser.close()

// Playwright's video is BT.601 with no color tags, so a browser guesses BT.709 for HD and the
// red plays too bright. Convert and tag it. The mp4 is for players that can't open a webm.
const color = [
  '-vf',
  'scale=in_color_matrix=bt601:out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709',
  '-an',
]
const encode = (codec: string[], out: string) =>
  Bun.spawnSync(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw, ...color, ...codec, out], {
    stdout: 'inherit',
    stderr: 'inherit',
  })
encode(['-c:v', 'libvpx-vp9', '-crf', '28', '-b:v', '0', '-row-mt', '1', '-cpu-used', '4'], 'demo/backup.webm')
encode(['-c:v', 'libx264', '-crf', '20', '-movflags', '+faststart'], 'demo/backup.mp4')
console.log('Saved demo/backup.webm and demo/backup.mp4')
