import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function createAbcPlan(page: Page) {
  await page.goto('/')
  await page.getByTestId('roll-length').fill('1000')
  await page.getByTestId('kerf-width').fill('10')
  await page.getByTestId('segment-id-0').fill('A')
  await page.getByTestId('segment-length-0').fill('600')
  await page.getByTestId('segment-id-1').fill('B')
  await page.getByTestId('segment-length-1').fill('590')
  await page.getByTestId('segment-id-2').fill('C')
  await page.getByTestId('segment-length-2').fill('400')
  await page.getByTestId('submit-plan').click()
  await expect(page).toHaveURL(/\/plans\/\d+$/)
}

test.describe('roll cutting planner', () => {
  test('creates a plan and shows per-roll cutting order, kerfs and leftover', async ({
    page,
  }) => {
    await page.goto('/')
    await page.getByTestId('roll-length').fill('1000')
    await page.getByTestId('kerf-width').fill('10')
    await page.getByTestId('segment-id-0').fill('A')
    await page.getByTestId('segment-length-0').fill('600')
    await page.getByTestId('segment-id-1').fill('B')
    await page.getByTestId('segment-length-1').fill('590')
    await page.getByTestId('segment-id-2').fill('C')
    await page.getByTestId('segment-length-2').fill('400')
    await page.getByTestId('submit-plan').click()

    // redirected to the persisted detail page
    await expect(page).toHaveURL(/\/plans\/\d+$/)
    await expect(page.getByText('第 1 卷')).toBeVisible()
    await expect(page.getByText('第 2 卷')).toBeVisible()
    // canonical order lives on the cutting-order line (the progress list also
    // repeats each id/length, so scope to the order line)
    const orderLines = page.locator('.cutting-order')
    await expect(orderLines.filter({ hasText: 'A（交付 600 mm + 余量 0 mm = 下料 600 mm）' })).toBeVisible()
    await expect(
      orderLines.filter({ hasText: /B（交付 590 mm \+ 余量 0 mm = 下料 590 mm） → C（交付 400 mm \+ 余量 0 mm = 下料 400 mm）/ }),
    ).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /锯口 1 次/ })).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /余料 0 mm/ })).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /余料 400 mm/ })).toBeVisible()
    // a fresh plan starts with no recorded progress
    await expect(page.getByTestId('overall-progress')).toHaveText('0 / 3 段')

    // the plan is listed on the history page
    await page.goto('/plans')
    await expect(page.getByRole('link', { name: '查看' }).first()).toBeVisible()
  })

  test('records two cuts, persists across refresh, then continues on another roll', async ({
    page,
  }) => {
    await createAbcPlan(page)
    // canonical solution: roll 1 = [A], roll 2 = [B, C]
    await expect(page.getByTestId('overall-progress')).toHaveText('0 / 3 段')

    // complete the first cut of roll 2 (B)
    await page.getByTestId('complete-roll-2').click()
    await expect(page.getByTestId('overall-progress')).toHaveText('1 / 3 段')
    await expect(page.getByTestId('roll-progress-2')).toHaveText('已完成 1 / 2 段')
    await expect(page.getByTestId('cut-2-1')).toHaveClass(/cut-status-done/)
    await expect(page.getByTestId('cut-2-2')).toHaveClass(/cut-status-next/)

    // complete the next cut (C)
    await page.getByTestId('complete-roll-2').click()
    await expect(page.getByTestId('overall-progress')).toHaveText('2 / 3 段')
    await expect(page.getByTestId('roll-progress-2')).toHaveText('已完成 2 / 2 段')
    await expect(page.getByTestId('complete-roll-2')).toBeDisabled()
    await expect(page.getByTestId('complete-roll-2')).toHaveText('本卷已全部完成')

    // progress survives a full page reload
    await page.reload()
    await expect(page.getByTestId('overall-progress')).toHaveText('2 / 3 段')
    await expect(page.getByTestId('cut-2-1')).toHaveClass(/cut-status-done/)
    await expect(page.getByTestId('cut-2-2')).toHaveClass(/cut-status-done/)

    // continue on roll 1 after the refresh until everything is finished
    await page.getByTestId('complete-roll-1').click()
    await expect(page.getByTestId('overall-progress')).toHaveText('3 / 3 段（全部完成）')
    await expect(page.getByTestId('complete-roll-1')).toBeDisabled()

    // a mistaken tap can only undo that roll's last completed cut (A)
    await page.getByTestId('undo-roll-1').click()
    await expect(page.getByTestId('overall-progress')).toHaveText('2 / 3 段')
    await expect(page.getByTestId('cut-1-1')).toHaveClass(/cut-status-next/)

    // original cutting order, kerfs and leftovers stay on display throughout
    await expect(page.getByText(/B（交付 590 mm \+ 余量 0 mm = 下料 590 mm） → C（交付 400 mm \+ 余量 0 mm = 下料 400 mm）/)).toBeVisible()
    await expect(page.getByText(/锯口 1 次/)).toBeVisible()
    await expect(page.getByText(/余料 400 mm/)).toBeVisible()
    await expect(page.getByText(/余料 0 mm/)).toBeVisible()
  })

  test('an older plan opened from history loads with empty progress and the original order, kerfs and leftovers', async ({
    page,
  }) => {
    await createAbcPlan(page)
    const newerUrl = page.url()

    // create a second plan; the first one now plays the role of the "old" plan
    await page.goto('/')
    await page.getByTestId('roll-length').fill('100')
    await page.getByTestId('kerf-width').fill('5')
    await page.getByTestId('segment-id-0').fill('A')
    await page.getByTestId('segment-length-0').fill('40')
    await page.getByTestId('segment-id-1').fill('B')
    await page.getByTestId('segment-length-1').fill('40')
    await page.getByTestId('add-segment').click()
    await page.getByTestId('segment-id-2').fill('C')
    await page.getByTestId('segment-length-2').fill('40')
    await page.getByTestId('segment-id-3').fill('D')
    await page.getByTestId('segment-length-3').fill('40')
    await page.getByTestId('submit-plan').click()
    await expect(page).toHaveURL(/\/plans\/\d+$/)

    // back in history, open the older plan directly
    await page.goto('/plans')
    const olderPath = new URL(newerUrl).pathname
    await page.locator(`a[href="${olderPath}"]`).click()
    await expect(page).toHaveURL(newerUrl)

    // no recorded progress and the original canonical solution is unchanged
    await expect(page.getByTestId('overall-progress')).toHaveText('0 / 3 段')
    await expect(
      page.locator('.cutting-order').filter({ hasText: 'A（交付 600 mm + 余量 0 mm = 下料 600 mm）' }),
    ).toBeVisible()
    await expect(
      page.locator('.cutting-order').filter({ hasText: /B（交付 590 mm \+ 余量 0 mm = 下料 590 mm） → C（交付 400 mm \+ 余量 0 mm = 下料 400 mm）/ }),
    ).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /锯口 1 次/ })).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /余料 400 mm/ })).toBeVisible()
    await expect(page.locator('.roll-math').filter({ hasText: /余料 0 mm/ })).toBeVisible()
    await expect(page.getByTestId('cut-2-1')).toHaveClass(/cut-status-next/)
  })

  test('a stale page gets a conflict and re-syncs to the real server progress', async ({
    browser,
  }) => {
    const ctx = await browser.newContext()
    const pageA = await ctx.newPage()
    const pageB = await ctx.newPage()

    await createAbcPlan(pageA)
    const detailUrl = pageA.url()
    // both tabs hold the same initial (0/3) view
    await pageB.goto(detailUrl)
    await expect(pageB.getByTestId('overall-progress')).toHaveText('0 / 3 段')

    // tab B advances roll 2 first...
    await pageB.getByTestId('complete-roll-2').click()
    await expect(pageB.getByTestId('overall-progress')).toHaveText('1 / 3 段')

    // ...tab A is stale and still offers position 1; its tap is rejected
    await pageA.getByTestId('complete-roll-2').click()
    await expect(pageA.getByTestId('conflict-banner')).toBeVisible()
    // recovery re-pulls the detail: tab A now shows the server truth
    await expect(pageA.getByTestId('overall-progress')).toHaveText('1 / 3 段')
    await expect(pageA.getByTestId('cut-2-1')).toHaveClass(/cut-status-done/)
    await expect(pageA.getByTestId('cut-2-2')).toHaveClass(/cut-status-next/)
    // the other roll was not affected by the rejected action
    await expect(pageA.getByTestId('cut-1-1')).toHaveClass(/cut-status-next/)
    await ctx.close()
  })

  test('422 errors are located on the form and the input is preserved', async ({
    page,
  }) => {
    await page.goto('/')
    // duplicate the id of the first row into the third row
    await page.getByTestId('segment-id-2').fill('S1')
    await page.getByTestId('submit-plan').click()

    await expect(page.getByRole('alert').first()).toBeVisible()
    await expect(page.getByText(/duplicate segment id/)).toBeVisible()
    // still on the form, original input preserved
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByTestId('segment-id-0')).toHaveValue('S1')
    await expect(page.getByTestId('segment-id-2')).toHaveValue('S1')
    await expect(page.getByTestId('segment-length-1')).toHaveValue('590')
  })

  test('segment longer than the roll is rejected with a located error', async ({
    page,
  }) => {
    await page.goto('/')
    await page.getByTestId('roll-length').fill('500')
    await page.getByTestId('segment-length-0').fill('600')
    await page.getByTestId('submit-plan').click()

    await expect(
      page.getByText('segment length 600 exceeds usable roll length 500'),
    ).toBeVisible()
    await expect(page.getByTestId('segment-length-0')).toHaveValue('600')
  })

  test.describe('adjusting from an existing plan', () => {
    async function createOriginal(page: Page) {
      await page.goto('/')
      await page.getByTestId('roll-length').fill('1000')
      await page.getByTestId('kerf-width').fill('10')
      await page.getByTestId('segment-id-0').fill('A')
      await page.getByTestId('segment-length-0').fill('600')
      await page.getByTestId('segment-id-1').fill('B')
      await page.getByTestId('segment-length-1').fill('590')
      await page.getByTestId('segment-id-2').fill('C')
      await page.getByTestId('segment-length-2').fill('400')
      await page.getByTestId('submit-plan').click()
      await expect(page).toHaveURL(/\/plans\/\d+$/)
      const id = Number(page.url().split('/').pop())
      return id
    }

    test('carries inputs into a new editable plan, keeps the original intact, and links both ways', async ({
      page,
    }) => {
      const originalId = await createOriginal(page)

      // start the adjustment from the read-only detail
      await page.getByTestId('adjust-from-plan').click()
      await expect(page).toHaveURL(`/?from=${originalId}`)
      await expect(page.getByTestId('source-banner')).toBeVisible()
      await expect(page.getByTestId('roll-length')).toHaveValue('1000')
      await expect(page.getByTestId('kerf-width')).toHaveValue('10')
      await expect(page.getByTestId('segment-id-0')).toHaveValue('A')
      await expect(page.getByTestId('segment-length-2')).toHaveValue('400')

      // change one segment length and re-solve under the existing rules
      await page.getByTestId('segment-length-1').fill('380')
      await page.getByTestId('submit-plan').click()
      await expect(page).toHaveURL(/\/plans\/\d+$/)
      const adjustedId = Number(page.url().split('/').pop())
      expect(adjustedId).not.toBe(originalId)

      // the new plan shows the "源自方案" link and the edited result
      const sourceLine = page.getByTestId('source-line')
      await expect(sourceLine).toBeVisible()
      await expect(sourceLine.getByRole('link', { name: `#${originalId}` })).toHaveAttribute(
        'href',
        `/plans/${originalId}`,
      )
      // roll 2 now holds 380+400+10 = 790, leftover 210; total leftover 610
      await expect(page.getByText(/余料 210 mm/)).toBeVisible()
      await expect(page.getByText(/余料 400 mm/)).toBeVisible()

      // follow the source link back: the original plan is untouched/read-only
      await sourceLine.getByRole('link').click()
      await expect(page).toHaveURL(`/plans/${originalId}`)
      await expect(page.getByText(/B（交付 590 mm \+ 余量 0 mm = 下料 590 mm） → C（交付 400 mm \+ 余量 0 mm = 下料 400 mm）/)).toBeVisible()
      await expect(page.getByText(/余料 0 mm/)).toBeVisible()
      await expect(page.getByTestId('source-line')).toHaveCount(0)

      // history list carries provenance for the adjustment only
      await page.goto('/plans')
      await expect(page.getByTestId(`source-link-${adjustedId}`)).toHaveAttribute(
        'href',
        `/plans/${originalId}`,
      )
      await expect(page.getByTestId(`source-link-${originalId}`)).toHaveCount(0)
    })

    test('ordinary creation shows no provenance banner', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByTestId('source-banner')).toHaveCount(0)
    })

    test('an invalid source id on load reports the failure without trapping the user', async ({
      page,
    }) => {
      await page.goto('/?from=999999')
      await expect(page.getByTestId('from-load-error')).toBeVisible()
      await expect(page.getByRole('link', { name: '返回历史方案重新选择' })).toHaveAttribute(
        'href',
        '/plans',
      )
    })

    test('a rejected source on submit preserves every edit and lets the foreman re-pick the source', async ({
      page,
    }) => {
      const originalId = await createOriginal(page)
      await page.goto(`/?from=${originalId}`)
      await expect(page.getByTestId('source-banner')).toBeVisible()

      // the foreman edits before submitting; simulate the server rejecting
      // the provenance link once (e.g. source deleted between load and save)
      let rejectedOnce = false
      await page.route('**/api/plans', async (route) => {
        if (route.request().method() === 'POST' && !rejectedOnce) {
          rejectedOnce = true
          await route.fulfill({
            status: 422,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: [
                {
                  loc: ['source_plan_id'],
                  msg: `source plan ${originalId} not found`,
                  type: 'value_error',
                },
              ],
            }),
          })
          return
        }
        await route.continue()
      })

      await page.getByTestId('segment-length-0').fill('650')
      await page.getByTestId('submit-plan').click()

      // error shown, all edits preserved, no new plan created
      await expect(page.getByTestId('source-error')).toBeVisible()
      await expect(page).toHaveURL(`/?from=${originalId}`)
      await expect(page.getByTestId('segment-length-0')).toHaveValue('650')
      await expect(page.getByTestId('segment-length-1')).toHaveValue('590')
      await expect(page.getByTestId('roll-length')).toHaveValue('1000')

      // re-pick the source; the retry succeeds with the edits intact
      await page.getByTestId('source-plan-input').fill(String(originalId))
      await page.getByTestId('source-plan-confirm').click()
      await expect(page.getByTestId('source-error')).toHaveCount(0)
      await page.getByTestId('submit-plan').click()
      await expect(page).toHaveURL(/\/plans\/\d+$/)
      const adjustedId = Number(page.url().split('/').pop())
      expect(adjustedId).not.toBe(originalId)
      await expect(
        page.locator('.cutting-order').filter({ hasText: /A（交付 650 mm \+ 余量 0 mm = 下料 650 mm）/ }),
      ).toBeVisible()
    })
  })

  test('allowance changes the packing and the detail survives a reload', async ({
    page,
  }) => {
    await page.goto('/')
    await page.getByTestId('roll-length').fill('1000')
    await page.getByTestId('kerf-width').fill('10')
    await page.getByTestId('segment-id-0').fill('A')
    await page.getByTestId('segment-length-0').fill('600')
    await page.getByTestId('segment-id-1').fill('B')
    await page.getByTestId('segment-length-1').fill('590')
    await page.getByTestId('segment-id-2').fill('C')
    await page.getByTestId('segment-length-2').fill('400')
    // C's allowance pushes its cut length to 450, so B + C no longer fit
    // one roll: the plan grows from 2 rolls to 3.
    await page.getByTestId('segment-allowance-2').fill('50')
    await page.getByTestId('submit-plan').click()

    await expect(page).toHaveURL(/\/plans\/\d+$/)
    await expect(page.getByText('第 1 卷')).toBeVisible()
    await expect(page.getByText('第 2 卷')).toBeVisible()
    await expect(page.getByText('第 3 卷')).toBeVisible()
    // delivery length, allowance and cut length are all shown
    await expect(
      page.locator('.cutting-order').filter({
        hasText: /C（交付 400 mm \+ 余量 50 mm = 下料 450 mm）/,
      }),
    ).toBeVisible()
    await expect(
      page.locator('.cutting-order').filter({ hasText: /A（交付 600 mm \+ 余量 0 mm = 下料 600 mm）/ }),
    ).toBeVisible()
    // leftover recomputed from the cut lengths
    await expect(page.getByText(/余料 550 mm/)).toBeVisible()
    await expect(page.getByText(/余料 410 mm/)).toBeVisible()
    await expect(page.getByText(/余料 400 mm/)).toBeVisible()

    // reload: the persisted plan shows the identical roll order and numbers
    await page.reload()
    await expect(page.getByText('第 1 卷')).toBeVisible()
    await expect(page.getByText('第 3 卷')).toBeVisible()
    await expect(
      page.locator('.cutting-order').filter({
        hasText: /C（交付 400 mm \+ 余量 50 mm = 下料 450 mm）/,
      }),
    ).toBeVisible()
    await expect(page.getByText(/余料 550 mm/)).toBeVisible()
    await expect(page.getByText(/余料 410 mm/)).toBeVisible()
    await expect(page.getByText(/余料 400 mm/)).toBeVisible()
  })

  test('length + allowance beyond the roll is located on the allowance input', async ({
    page,
  }) => {
    await page.goto('/')
    await page.getByTestId('roll-length').fill('500')
    await page.getByTestId('segment-length-0').fill('400')
    await page.getByTestId('segment-allowance-0').fill('150')
    // keep the other rows valid so only the allowance error fires
    await page.getByTestId('segment-length-1').fill('300')
    await page.getByTestId('segment-length-2').fill('200')
    await page.getByTestId('submit-plan').click()

    // server-side 422 mapped back onto the allowance input of the same row
    await expect(
      page.getByText('segment length 400 + allowance 150 exceeds usable roll length 500'),
    ).toBeVisible()
    // the whole form is preserved
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByTestId('segment-length-0')).toHaveValue('400')
    await expect(page.getByTestId('segment-allowance-0')).toHaveValue('150')
    await expect(page.getByTestId('segment-length-1')).toHaveValue('300')
    await expect(page.getByTestId('segment-length-2')).toHaveValue('200')
  })
})
